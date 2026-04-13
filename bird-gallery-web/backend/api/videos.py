"""
视频 API — Phase 3

- 上传视频
- 视频详情/流
- 帧分析（异步任务）
- 时间轴/精彩帧
- 导出片段
"""

import os
import uuid
import json
import logging
import shutil

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, BackgroundTasks, Body
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from models.database import get_db, get_db_connection
from services.video_processor import get_video_info, transcode_video, extract_frames, generate_thumbnail
from api.auth import require_admin
from app_config_pkg import config as app_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["videos"])

_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
_MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB

# 视频分析质量阈值
_MIN_CONFIDENCE = 0.3       # 单帧最低置信度，低于此值视为未检测到
_MIN_FRAME_COUNT = 3        # 同一鸟种至少出现帧数，少于此值在聚合阶段过滤


def _delete_video(db, video_id: str) -> int:
    """删除单个视频的数据库记录和磁盘文件。返回 1 表示成功，0 表示未找到。"""
    row = db.execute("SELECT original_path FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        return 0

    # 删除关联数据
    db.execute("DELETE FROM video_bird_segments WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM video_frames WHERE video_id = ?", (video_id,))
    db.execute("DELETE FROM videos WHERE id = ?", (video_id,))

    # 删除磁盘文件
    original = row["original_path"]
    if original and os.path.exists(original):
        try:
            os.unlink(original)
        except OSError as e:
            logger.warning("Failed to delete original video %s: %s", original, e)

    transcoded = os.path.join(app_config.videos_transcoded_dir(), f"{video_id}.mp4")
    if os.path.exists(transcoded):
        try:
            os.unlink(transcoded)
        except OSError as e:
            logger.warning("Failed to delete transcoded video %s: %s", transcoded, e)

    # 删除帧目录
    vid_frames_dir = app_config.frames_dir(video_id)
    if os.path.isdir(vid_frames_dir):
        try:
            shutil.rmtree(vid_frames_dir)
        except OSError as e:
            logger.warning("Failed to delete frames dir %s: %s", vid_frames_dir, e)

    # 删除缩略图
    thumb_path = os.path.join(app_config.videos_thumbnails_dir(), f"{video_id}.jpg")
    if os.path.exists(thumb_path):
        try:
            os.unlink(thumb_path)
        except OSError as e:
            logger.warning("Failed to delete thumbnail %s: %s", thumb_path, e)

    return 1


@router.post("/videos/generate-thumbnails")
async def generate_missing_thumbnails(db=Depends(get_db)):
    """为所有缺少缩略图的视频补生成预览图。"""
    rows = db.execute("SELECT id, original_path FROM videos").fetchall()
    thumb_dir = app_config.videos_thumbnails_dir()

    generated = 0
    failed = 0
    for row in rows:
        thumb_path = os.path.join(thumb_dir, f"{row['id']}.jpg")
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            continue
        src = row["original_path"]
        if not src or not os.path.exists(src):
            failed += 1
            continue
        ok = await run_in_threadpool(generate_thumbnail, src, thumb_path)
        if ok:
            generated += 1
        else:
            failed += 1

    return {"generated": generated, "failed": failed, "total": len(rows)}


@router.get("/videos")
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """视频列表（分页）。"""
    total = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    offset = (page - 1) * page_size
    rows = db.execute(
        """
        SELECT * FROM videos
        ORDER BY imported_at DESC
        LIMIT ? OFFSET ?
        """,
        (page_size, offset),
    ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


@router.post("/videos/upload")
async def upload_video(
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """上传视频文件。"""
    if not file.filename:
        raise HTTPException(400, "Missing filename")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format. Allowed: {_VIDEO_EXTENSIONS}")

    video_id = str(uuid.uuid4())
    upload_dir = app_config.videos_original_dir()
    dest_path = os.path.join(upload_dir, f"{video_id}{ext}")

    total_size = 0
    with open(dest_path, 'wb') as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > _MAX_FILE_SIZE:
                f.close()
                os.unlink(dest_path)
                raise HTTPException(413, "File too large (max 10GB)")
            f.write(chunk)

    # 获取视频信息
    info = await run_in_threadpool(get_video_info, dest_path)

    # 生成缩略图
    thumb_dir = app_config.videos_thumbnails_dir()
    thumb_path = os.path.join(thumb_dir, f"{video_id}.jpg")
    await run_in_threadpool(generate_thumbnail, dest_path, thumb_path)

    db.execute(
        """INSERT INTO videos (id, original_path, filename, duration, fps, frame_count, status)
           VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
        (video_id, dest_path, file.filename,
         info.get("duration") if info else None,
         info.get("fps") if info else None,
         info.get("frame_count") if info else None),
    )
    db.commit()

    return {
        "id": video_id,
        "video_id": video_id,
        "filename": file.filename,
        "size": total_size,
        "info": info,
    }


@router.post("/videos/batch-delete", dependencies=[Depends(require_admin)])
async def batch_delete_videos(
    ids: list[str] = Body(..., embed=True),
    db=Depends(get_db),
):
    """批量删除视频及相关数据和文件。"""
    if not ids or len(ids) > 500:
        raise HTTPException(400, "ids must be 1-500")
    deleted = 0
    for vid in ids:
        deleted += _delete_video(db, vid)
    db.commit()
    return {"deleted": deleted}


@router.post("/videos/batch-analyze")
async def batch_analyze_videos(
    strategy: str = Query("interval", pattern="^(keyframe|interval|scene|all)$"),
    interval: int = Query(10, ge=1, le=300),
    background_tasks: BackgroundTasks = None,
    db=Depends(get_db),
):
    """一键分析所有未分析的视频（异步任务）。"""
    rows = db.execute(
        "SELECT id FROM videos WHERE status NOT IN ('analyzing', 'transcoding')"
    ).fetchall()
    video_ids = [r["id"] for r in rows]
    if not video_ids:
        return {"task_id": None, "total": 0, "message": "没有可分析的视频"}

    task_id = str(uuid.uuid4())
    config_json = json.dumps({
        "strategy": strategy,
        "interval": interval,
        "total": len(video_ids),
        "video_ids": video_ids,
    })
    db.execute(
        "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'batch-analyze', 'pending', ?)",
        (task_id, config_json),
    )
    db.commit()

    background_tasks.add_task(_batch_analyze_task, task_id, video_ids, strategy, interval)
    return {"task_id": task_id, "total": len(video_ids)}


@router.get("/videos/{video_id}")
async def get_video(video_id: str, db=Depends(get_db)):
    """视频详情。"""
    row = db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Video not found")
    return dict(row)


@router.get("/videos/{video_id}/thumbnail")
async def get_video_thumbnail(video_id: str):
    """返回视频缩略图。"""
    thumb_path = os.path.join(app_config.videos_thumbnails_dir(), f"{video_id}.jpg")
    if not os.path.exists(thumb_path):
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(thumb_path, media_type="image/jpeg")


@router.get("/videos/{video_id}/stream")
async def stream_video(video_id: str, db=Depends(get_db)):
    """视频流（返回文件，靠 nginx Range 请求实现分段播放）。"""
    row = db.execute("SELECT original_path FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Video not found")

    # 优先使用转码后的文件
    transcoded = os.path.join(app_config.videos_transcoded_dir(), f"{video_id}.mp4")
    path = transcoded if os.path.exists(transcoded) else row["original_path"]

    if not os.path.exists(path):
        raise HTTPException(404, "Video file not found")

    return FileResponse(path, media_type="video/mp4")


@router.post("/videos/{video_id}/analyze")
async def analyze_video(
    video_id: str,
    strategy: str = Query("interval", pattern="^(keyframe|interval|scene|all)$"),
    interval: int = Query(10, ge=1, le=300),
    background_tasks: BackgroundTasks = None,
    db=Depends(get_db),
):
    """发起视频分析（异步任务）。"""
    row = db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Video not found")

    # 防止重复分析
    if row["status"] in ("analyzing", "transcoding"):
        raise HTTPException(409, "该视频正在分析中，请等待完成")

    task_id = str(uuid.uuid4())
    config_json = json.dumps({
        "video_id": row["id"],
        "filename": row["filename"],
        "strategy": strategy,
        "interval": interval,
    })
    db.execute(
        "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'analyze', 'pending', ?)",
        (task_id, config_json),
    )
    db.commit()

    background_tasks.add_task(_analyze_task, task_id, video_id, strategy, interval)
    return {"id": task_id, "task_id": task_id}


def _analyze_task(task_id: str, video_id: str, strategy: str, interval: int):
    """后台视频分析任务。"""
    db = get_db_connection()

    def _is_cancelled() -> bool:
        row = db.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return bool(row and row["status"] == "cancelled")

    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        video = db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()

        if _is_cancelled():
            db.execute("UPDATE videos SET status = 'ready', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (video_id,))
            db.commit()
            return

        # 1. 转码（如果需要）
        db.execute(
            "UPDATE videos SET status = 'transcoding', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (video_id,),
        )
        db.commit()

        transcoded_path = os.path.join(app_config.videos_transcoded_dir(), f"{video_id}.mp4")
        # 如果原始视频已是 H.264，直接使用原始文件跳过转码
        from services.video_processor import get_video_info as _gvi
        _vinfo = _gvi(video["original_path"])
        if _vinfo and _vinfo.get("codec") == "h264":
            transcoded_path = video["original_path"]
        elif not os.path.exists(transcoded_path):
            def update_transcode_progress(pct):
                db.execute(
                    "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (min(pct // 3, 30), task_id),  # 转码占 0-30%
                )
                db.commit()

            success = transcode_video(video["original_path"], transcoded_path, update_transcode_progress)
            if not success:
                raise RuntimeError("Transcode failed")

        # 2. 帧提取
        db.execute(
            "UPDATE videos SET status = 'analyzing' WHERE id = ?", (video_id,),
        )
        db.execute(
            "UPDATE tasks SET progress = 30, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        if _is_cancelled():
            db.execute("UPDATE videos SET status = 'ready', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (video_id,))
            db.commit()
            return

        vid_frames_dir = app_config.frames_dir(video_id)
        frames = extract_frames(transcoded_path, vid_frames_dir, strategy, interval)

        # 3. 逐帧识别
        total_frames = len(frames)
        from main import inference_thread_lock
        for i, frame in enumerate(frames):
            if _is_cancelled():
                logger.info("Analyze task %s cancelled at frame %d/%d", task_id, i, total_frames)
                db.execute("UPDATE videos SET status = 'ready', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (video_id,))
                db.commit()
                return
            try:
                from birdid import identify_bird
                with inference_thread_lock:
                    result = identify_bird(frame["path"], use_yolo=True, top_k=5)

                detected = False
                species_cn = None
                species_en = None
                confidence = None
                detection_box = None

                if result and result.get("success") and result.get("results"):
                    top = result["results"][0]
                    conf = top.get("confidence") or 0
                    # 置信度阈值过滤
                    if conf >= _MIN_CONFIDENCE:
                        detected = True
                        # 兼容 birdid 返回键：cn_name / en_name
                        species_cn = top.get("species_cn") or top.get("cn_name")
                        species_en = top.get("species_en") or top.get("en_name")
                        confidence = conf
                        yolo_info = result.get("yolo_info") or {}
                        if isinstance(yolo_info, str):
                            yolo_info = {}
                        if yolo_info.get("box"):
                            detection_box = json.dumps(yolo_info["box"])
                    else:
                        logger.debug("Frame %d: confidence %.3f below threshold %.2f, skipped",
                                     frame["frame_number"], conf, _MIN_CONFIDENCE)

                db.execute(
                    """INSERT INTO video_frames
                       (video_id, frame_number, timestamp, bird_detected,
                        species_cn, species_en, confidence, detection_box, frame_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (video_id, frame["frame_number"], frame["timestamp"],
                     1 if detected else 0,
                     species_cn, species_en, confidence, detection_box, frame["path"]),
                )
            except Exception as e:
                logger.warning("Frame analysis failed for frame %d: %s", frame["frame_number"], e)

            progress = 30 + int((i + 1) / max(total_frames, 1) * 60)  # 30-90%
            if i % 5 == 0:
                db.execute(
                    "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (progress, task_id),
                )
                db.commit()

        db.commit()

        # 4. 聚合鸟种出现时段
        _aggregate_bird_segments(db, video_id)

        db.execute("UPDATE videos SET status = 'done' WHERE id = ?", (video_id,))
        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

    except Exception as e:
        logger.error("Analyze task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE videos SET status = 'error' WHERE id = ?", (video_id,),
        )
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()


def _aggregate_bird_segments(db, video_id: str):
    """从 video_frames 聚合鸟种出现时段到 video_bird_segments。

    多帧验证：同一鸟种必须在至少 _MIN_FRAME_COUNT 帧中被检测到才记录，
    减少单帧误检导致的误报。
    断段阈值自适应：根据实际帧间隔动态计算，避免采样间隔大时所有段被拆散。
    """
    db.execute("DELETE FROM video_bird_segments WHERE video_id = ?", (video_id,))

    # 计算自适应断段阈值：取检测帧的中位间隔 × 2.5，最少 2 秒
    all_ts = db.execute("""
        SELECT timestamp FROM video_frames
        WHERE video_id = ? AND bird_detected = 1
        ORDER BY timestamp
    """, (video_id,)).fetchall()
    gap_threshold = 2.0
    if len(all_ts) >= 2:
        diffs = [all_ts[i+1]["timestamp"] - all_ts[i]["timestamp"]
                 for i in range(len(all_ts) - 1) if all_ts[i+1]["timestamp"] > all_ts[i]["timestamp"]]
        if diffs:
            diffs.sort()
            median_gap = diffs[len(diffs) // 2]
            gap_threshold = max(2.0, median_gap * 2.5)

    species_rows = db.execute("""
        SELECT species_cn, species_en, COUNT(*) as frame_cnt
        FROM video_frames
        WHERE video_id = ? AND bird_detected = 1 AND species_cn IS NOT NULL
        GROUP BY species_cn, species_en
        HAVING frame_cnt >= ?
    """, (video_id, _MIN_FRAME_COUNT)).fetchall()

    for sp in species_rows:
        frames = db.execute("""
            SELECT frame_number, timestamp, confidence, frame_path
            FROM video_frames
            WHERE video_id = ? AND species_cn = ? AND bird_detected = 1
            ORDER BY frame_number
        """, (video_id, sp["species_cn"])).fetchall()

        if not frames:
            continue

        # 合并连续时段（间隔 > gap_threshold 算新段）
        segments = []
        seg_start = frames[0]["timestamp"]
        seg_end = frames[0]["timestamp"]
        best_conf = frames[0]["confidence"] or 0
        best_frame = frames[0]["frame_number"]
        best_path = frames[0]["frame_path"]

        for f in frames[1:]:
            if f["timestamp"] - seg_end > gap_threshold:
                segments.append((seg_start, seg_end, best_conf, best_frame, best_path))
                seg_start = f["timestamp"]
                best_conf = f["confidence"] or 0
                best_frame = f["frame_number"]
                best_path = f["frame_path"]
            else:
                if (f["confidence"] or 0) > best_conf:
                    best_conf = f["confidence"] or 0
                    best_frame = f["frame_number"]
                    best_path = f["frame_path"]
            seg_end = f["timestamp"]

        segments.append((seg_start, seg_end, best_conf, best_frame, best_path))

        for start, end, conf, bf, bp in segments:
            db.execute(
                """INSERT INTO video_bird_segments
                   (video_id, species_cn, species_en, start_time, end_time,
                    max_confidence, best_frame_number, best_frame_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (video_id, sp["species_cn"], sp["species_en"],
                 start, end, conf, bf, bp),
            )

    db.commit()


def _batch_analyze_task(task_id: str, video_ids: list[str], strategy: str, interval: int):
    """批量视频分析任务：逐个分析所有视频。"""
    db = get_db_connection()

    def _is_cancelled() -> bool:
        row = db.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return bool(row and row["status"] == "cancelled")

    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        total = len(video_ids)
        completed = 0
        failed = 0
        results = []

        for i, vid in enumerate(video_ids):
            if _is_cancelled():
                logger.info("Batch analyze task %s cancelled at %d/%d", task_id, i, total)
                break

            sub_task_id = str(uuid.uuid4())
            try:
                video_row = db.execute("SELECT filename FROM videos WHERE id = ?", (vid,)).fetchone()
                config_json = json.dumps({
                    "video_id": vid,
                    "filename": video_row["filename"] if video_row else None,
                    "strategy": strategy,
                    "interval": interval,
                })
                db.execute(
                    "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'analyze', 'pending', ?)",
                    (sub_task_id, config_json),
                )
                db.commit()
                _analyze_task(sub_task_id, vid, strategy, interval)
                completed += 1
                results.append({"video_id": vid, "status": "done"})
            except Exception as e:
                failed += 1
                results.append({"video_id": vid, "status": "error", "error": str(e)})
                logger.warning("Batch analyze video %s failed: %s", vid, e)

            overall_progress = int((i + 1) / total * 100)
            db.execute(
                "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (overall_progress, task_id),
            )
            db.commit()

        if not _is_cancelled():
            db.execute(
                "UPDATE tasks SET status = 'done', progress = 100, "
                "error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps({"completed": completed, "failed": failed, "total": total}), task_id),
            )
            db.commit()

    except Exception as e:
        logger.error("Batch analyze task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()


@router.get("/videos/{video_id}/frames")
async def get_video_frames(
    video_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db=Depends(get_db),
):
    """获取帧分析结果列表。"""
    total = db.execute(
        "SELECT COUNT(*) FROM video_frames WHERE video_id = ?", (video_id,)
    ).fetchone()[0]

    offset = (page - 1) * page_size
    rows = db.execute("""
        SELECT * FROM video_frames
        WHERE video_id = ?
        ORDER BY frame_number
        LIMIT ? OFFSET ?
    """, (video_id, page_size, offset)).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "frames": [dict(r) for r in rows],
    }


@router.get("/videos/{video_id}/timeline")
async def get_timeline(video_id: str, db=Depends(get_db)):
    """获取鸟种出现时间轴数据。"""
    rows = db.execute("""
        SELECT id, video_id, species_cn, species_en,
               start_time AS start_seconds,
               end_time   AS end_seconds,
               max_confidence
        FROM video_bird_segments
        WHERE video_id = ?
        ORDER BY start_time
    """, (video_id,)).fetchall()

    return {"video_id": video_id, "segments": [dict(r) for r in rows]}


@router.get("/videos/{video_id}/highlights")
async def get_highlights(video_id: str, db=Depends(get_db)):
    """获取精彩帧截图列表（每种鸟 Top 3）。"""
    rows = db.execute("""
        SELECT species_cn, species_en, frame_number, timestamp,
               confidence, detection_box, frame_path
        FROM video_frames
        WHERE video_id = ? AND bird_detected = 1 AND species_cn IS NOT NULL
        ORDER BY confidence DESC
    """, (video_id,)).fetchall()

    # 按鸟种分组取 Top 3
    highlights = {}
    for r in rows:
        sp = r["species_cn"]
        if sp not in highlights:
            highlights[sp] = []
        if len(highlights[sp]) < 3:
            highlights[sp].append(dict(r))

    return {"video_id": video_id, "highlights": highlights}


@router.delete("/videos/{video_id}", dependencies=[Depends(require_admin)])
async def delete_video(video_id: str, db=Depends(get_db)):
    """删除单个视频及相关数据和文件。"""
    deleted = _delete_video(db, video_id)
    if not deleted:
        raise HTTPException(404, "Video not found")
    db.commit()
    return {"deleted": 1}


@router.post("/videos/{video_id}/export-clip")
async def export_clip(
    video_id: str,
    start_time: float = Query(..., ge=0),
    end_time: float = Query(..., ge=0),
    db=Depends(get_db),
):
    """导出指定时间段的视频片段。"""
    row = db.execute("SELECT original_path FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Video not found")

    transcoded = os.path.join(app_config.videos_transcoded_dir(), f"{video_id}.mp4")
    source = transcoded if os.path.exists(transcoded) else row["original_path"]

    clip_dir = app_config.videos_clips_dir()
    clip_id = str(uuid.uuid4())
    clip_path = os.path.join(clip_dir, f"{clip_id}.mp4")

    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-i", source,
        "-ss", str(start_time),
        "-to", str(end_time),
        "-c", "copy",
        clip_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise HTTPException(500, "Clip export failed")

    return FileResponse(clip_path, media_type="video/mp4", filename=f"clip_{clip_id}.mp4")
