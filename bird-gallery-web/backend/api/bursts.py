"""
连拍检测与合成视频 API — Phase 5

- 检测连拍组
- 连拍组 CRUD
- 批量识别
- 合成视频
"""

import os
import uuid
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from models.database import get_db, get_db_connection
from services.video_processor import synthesize_burst_video
from app_config_pkg import config as app_config
from api.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bursts"])


class SynthesizeRequest(BaseModel):
    framerate: int = 20          # 等效帧率（1-30）
    resolution: str = "1920x1080"  # 分辨率


@router.post("/photos/detect-bursts")
async def detect_bursts(
    background_tasks: BackgroundTasks,
    burst_time_threshold: float = Query(2.0, ge=0.05, le=60.0),
    burst_min_count: int = Query(3, ge=2, le=100),
    db=Depends(get_db),
):
    """检测连拍组（异步任务）。"""
    task_id = str(uuid.uuid4())
    config_json = json.dumps({
        "burst_time_threshold": burst_time_threshold,
        "burst_min_count": burst_min_count,
    }, ensure_ascii=False)
    db.execute(
        "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'detect_bursts', 'pending', ?)",
        (task_id, config_json),
    )
    db.commit()

    background_tasks.add_task(_detect_bursts_task, task_id, burst_time_threshold, burst_min_count)
    return {"id": task_id, "task_id": task_id}


def _detect_bursts_task(task_id: str, threshold: float, min_count: int):
    """后台连拍检测任务。"""
    db = get_db_connection()
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        # 清理旧的连拍组数据（重新检测）
        db.execute("DELETE FROM burst_group_photos")
        db.execute("DELETE FROM burst_groups")
        db.commit()

        # 获取所有照片的拍摄时间（按时间排序）
        photos = db.execute("""
            SELECT p.id, p.original_path, p.filename,
                   pm.date_taken, pm.camera_model
            FROM photos p
            LEFT JOIN photo_metadata pm ON p.id = pm.photo_id
            WHERE pm.date_taken IS NOT NULL
            ORDER BY pm.camera_model, pm.date_taken
        """).fetchall()

        if not photos:
            db.execute(
                "UPDATE tasks SET status = 'done', progress = 100, result_json = '{\"groups\": 0}', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id,),
            )
            db.commit()
            db.close()
            return

        # 按相机分组检测连拍
        from datetime import datetime
        groups_created = 0
        current_group = [photos[0]]

        for i in range(1, len(photos)):
            prev = photos[i - 1]
            curr = photos[i]

            # 不同相机断开
            same_camera = (prev["camera_model"] or "") == (curr["camera_model"] or "")

            try:
                dt_prev = str(prev["date_taken"]).replace("Z", "+00:00")
                dt_curr = str(curr["date_taken"]).replace("Z", "+00:00")
                # EXIF 日期格式 "2025:12:27 15:58:22" → ISO "2025-12-27 15:58:22"
                if len(dt_prev) >= 10 and dt_prev[4] == ':':
                    dt_prev = dt_prev[:10].replace(':', '-') + dt_prev[10:]
                if len(dt_curr) >= 10 and dt_curr[4] == ':':
                    dt_curr = dt_curr[:10].replace(':', '-') + dt_curr[10:]
                t_prev = datetime.fromisoformat(dt_prev)
                t_curr = datetime.fromisoformat(dt_curr)
                delta = (t_curr - t_prev).total_seconds()
            except Exception as exc:
                logger.warning("Burst date parse error: prev=%s curr=%s err=%s", prev["date_taken"], curr["date_taken"], exc)
                delta = 999

            if same_camera and 0 <= delta <= threshold:
                current_group.append(curr)
            else:
                if len(current_group) >= min_count:
                    _create_burst_group(db, current_group)
                    groups_created += 1
                current_group = [curr]

            progress = int((i + 1) / len(photos) * 100)
            if i % 100 == 0:
                db.execute(
                    "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (progress, task_id),
                )
                db.commit()

        # 最后一组
        if len(current_group) >= min_count:
            _create_burst_group(db, current_group)
            groups_created += 1

        result = f'{{"groups": {groups_created}}}'
        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, result_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (result, task_id),
        )
        db.commit()

    except Exception as e:
        logger.error("Burst detection task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()


def _create_burst_group(db, photos: list):
    """创建连拍组并关联照片。"""
    group_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO burst_groups (id, photo_count, created_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)""",
        (group_id, len(photos)),
    )

    for pos, photo in enumerate(photos):
        db.execute(
            "INSERT OR IGNORE INTO burst_group_photos (group_id, photo_id, position) VALUES (?, ?, ?)",
            (group_id, photo["id"], pos),
        )

    db.commit()


@router.get("/bursts")
async def list_bursts(
    page: int = Query(1, ge=1),
    page_size: int = Query(1000, ge=1, le=10000),
    species: str | None = None,
    camera: str | None = None,
    rating_min: int | None = None,
    min_photos: int = Query(1, ge=1),
    has_flying: bool = False,
    flying_min_count: int = Query(1, ge=1),
    db=Depends(get_db),
):
    """列出所有连拍组（支持筛选）。"""
    where_clauses = []
    params: list = []

    if min_photos > 1:
        where_clauses.append("actual_count >= ?")
        params.append(min_photos)
    if species:
        where_clauses.append("""bg.id IN (
            SELECT bgp_s.group_id FROM burst_group_photos bgp_s
            JOIN photo_birds pb_s ON pb_s.photo_id = bgp_s.photo_id AND pb_s.rank = 1
            WHERE pb_s.species_cn = ? AND pb_s.confidence >= 70
        )""")
        params.append(species)
    if camera:
        where_clauses.append("""bg.id IN (
            SELECT bgp_c.group_id FROM burst_group_photos bgp_c
            JOIN photo_metadata pm_c ON pm_c.photo_id = bgp_c.photo_id
            WHERE pm_c.camera_model = ?
        )""")
        params.append(camera)
    if rating_min is not None:
        where_clauses.append("""bg.id IN (
            SELECT bgp_r.group_id FROM burst_group_photos bgp_r
            JOIN photo_scores ps_r ON ps_r.photo_id = bgp_r.photo_id
            WHERE ps_r.rating >= ?
        )""")
        params.append(rating_min)
    if has_flying:
        where_clauses.append("""bg.id IN (
            SELECT bgp_f.group_id FROM burst_group_photos bgp_f
            JOIN photo_scores ps_f ON ps_f.photo_id = bgp_f.photo_id
            WHERE ps_f.is_flying = 1
            GROUP BY bgp_f.group_id
            HAVING COUNT(*) >= ?
        )""")
        params.append(flying_min_count)

    # 子查询先计算 actual_count，外层再 HAVING 过滤
    having = f"HAVING actual_count >= {min_photos}" if min_photos > 1 else ""
    # 移除 min_photos 的 where（在 HAVING 中处理）
    where_sql = ""
    filter_params: list = []
    for i, clause in enumerate(where_clauses):
        if "actual_count" not in clause:
            if where_sql:
                where_sql += " AND "
            where_sql += clause
            filter_params.append(params[i])

    where_prefix = f"WHERE {where_sql}" if where_sql else ""

    # 计算总数
    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT bg.id, COUNT(bgp.photo_id) as actual_count
            FROM burst_groups bg
            LEFT JOIN burst_group_photos bgp ON bg.id = bgp.group_id
            {where_prefix}
            GROUP BY bg.id
            {having}
        )
    """
    total = db.execute(count_sql, filter_params).fetchone()[0]
    offset = (page - 1) * page_size

    query_params = list(filter_params)
    rows = db.execute(f"""
        SELECT bg.*, COUNT(bgp.photo_id) as actual_count,
               COALESCE(bg.best_photo_id,
                 (SELECT bgp2.photo_id FROM burst_group_photos bgp2
                  WHERE bgp2.group_id = bg.id LIMIT 1)
               ) as cover_photo_id,
               (SELECT pb.species_cn FROM burst_group_photos bgp3
                JOIN photo_birds pb ON pb.photo_id = bgp3.photo_id AND pb.rank = 1
                WHERE bgp3.group_id = bg.id
                GROUP BY pb.species_cn ORDER BY COUNT(*) DESC LIMIT 1
               ) as top_species_cn
        FROM burst_groups bg
        LEFT JOIN burst_group_photos bgp ON bg.id = bgp.group_id
        {where_prefix}
        GROUP BY bg.id
        {having}
        ORDER BY bg.created_at DESC
        LIMIT ? OFFSET ?
    """, query_params + [page_size, offset]).fetchall()

    groups = []
    for r in rows:
        d = dict(r)
        if not d.get("best_photo_id"):
            d["best_photo_id"] = d.get("cover_photo_id")
        d.pop("cover_photo_id", None)
        # 用动态查询的鸟种覆盖空的 species_cn
        if not d.get("species_cn") and d.get("top_species_cn"):
            d["species_cn"] = d["top_species_cn"]
        d.pop("top_species_cn", None)
        groups.append(d)

    return {"total": total, "page": page, "groups": groups}


@router.get("/bursts/filter-options")
async def burst_filter_options(
    confidence_min: float = Query(70.0, ge=0, le=100),
    db=Depends(get_db),
):
    """返回连拍组可用的筛选项（按置信度过滤鸟种）。"""
    species_rows = db.execute("""
        SELECT DISTINCT pb.species_cn FROM burst_group_photos bgp
        JOIN photo_birds pb ON pb.photo_id = bgp.photo_id AND pb.rank = 1
        WHERE pb.species_cn IS NOT NULL AND pb.confidence >= ?
        ORDER BY pb.species_cn
    """, (confidence_min,)).fetchall()

    camera_rows = db.execute("""
        SELECT DISTINCT pm.camera_model FROM burst_group_photos bgp
        JOIN photo_metadata pm ON pm.photo_id = bgp.photo_id
        WHERE pm.camera_model IS NOT NULL AND pm.camera_model != ''
        ORDER BY pm.camera_model
    """).fetchall()

    return {
        "species": [r["species_cn"] for r in species_rows],
        "cameras": [r["camera_model"] for r in camera_rows],
    }


class BurstBatchDeleteRequest(BaseModel):
    group_ids: list[str]


@router.post("/bursts/batch-delete", dependencies=[Depends(require_admin)])
async def batch_delete_bursts(req: BurstBatchDeleteRequest, db=Depends(get_db)):
    """批量删除连拍组及其所有照片（包括磁盘文件）。"""
    from api.photos import _delete_photo_files

    deleted_groups = 0
    deleted_photos = 0
    file_map: dict[str, str] = {}

    for gid in req.group_ids:
        photos = db.execute(
            "SELECT p.id, p.original_path FROM burst_group_photos bgp JOIN photos p ON p.id = bgp.photo_id WHERE bgp.group_id = ?",
            (gid,),
        ).fetchall()

        for photo in photos:
            pid = photo["id"]
            file_map[pid] = photo["original_path"]
            db.execute("DELETE FROM photo_metadata WHERE photo_id = ?", (pid,))
            db.execute("DELETE FROM photo_scores WHERE photo_id = ?", (pid,))
            db.execute("DELETE FROM photo_birds WHERE photo_id = ?", (pid,))
            db.execute("DELETE FROM photo_tags WHERE photo_id = ?", (pid,))
            db.execute("DELETE FROM duplicate_groups WHERE photo_id = ?", (pid,))
            db.execute("DELETE FROM burst_group_photos WHERE photo_id = ?", (pid,))
            db.execute("DELETE FROM photos WHERE id = ?", (pid,))
            deleted_photos += 1

        db.execute("DELETE FROM burst_groups WHERE id = ?", (gid,))
        deleted_groups += 1

    db.commit()

    for pid, path in file_map.items():
        _delete_photo_files(pid, path)

    return {"deleted_groups": deleted_groups, "deleted_photos": deleted_photos}


@router.get("/bursts/{group_id}")
async def get_burst(group_id: str, db=Depends(get_db)):
    """连拍组详情。"""
    group = db.execute("SELECT * FROM burst_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise HTTPException(404, "Burst group not found")

    photos = db.execute("""
        SELECT p.id, p.filename, p.original_path, bgp.position,
               ps.rating, ps.nima_score, ps.head_sharp,
               pb.species_cn, pb.species_en, pb.confidence
        FROM burst_group_photos bgp
        JOIN photos p ON p.id = bgp.photo_id
        LEFT JOIN photo_scores ps ON p.id = ps.photo_id
        LEFT JOIN (
            SELECT photo_id, species_cn, species_en, confidence
            FROM photo_birds WHERE rank = 1
        ) pb ON p.id = pb.photo_id
        WHERE bgp.group_id = ?
        ORDER BY bgp.position
    """, (group_id,)).fetchall()

    return {
        **dict(group),
        "photos": [dict(p) for p in photos],
    }


@router.get("/bursts/{group_id}/best")
async def get_burst_best(group_id: str, db=Depends(get_db)):
    """获取组内最佳照片。"""
    group = db.execute("SELECT best_photo_id FROM burst_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise HTTPException(404, "Burst group not found")

    if group["best_photo_id"]:
        photo = db.execute("SELECT * FROM photos WHERE id = ?", (group["best_photo_id"],)).fetchone()
        if photo:
            return dict(photo)

    # 回退：按评分取最佳
    best = db.execute("""
        SELECT p.* FROM burst_group_photos bgp
        JOIN photos p ON p.id = bgp.photo_id
        LEFT JOIN photo_scores ps ON p.id = ps.photo_id
        WHERE bgp.group_id = ?
        ORDER BY COALESCE(ps.rating, 0) DESC, COALESCE(ps.nima_score, 0) DESC
        LIMIT 1
    """, (group_id,)).fetchone()

    if not best:
        raise HTTPException(404, "No photos in group")
    return dict(best)


@router.post("/bursts/{group_id}/recognize")
async def recognize_burst(
    group_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """批量识别连拍组中未识别的照片。"""
    photos = db.execute(
        """SELECT bgp.photo_id FROM burst_group_photos bgp
           LEFT JOIN photo_birds pb ON pb.photo_id = bgp.photo_id
           WHERE bgp.group_id = ? AND pb.id IS NULL""",
        (group_id,),
    ).fetchall()
    if not photos:
        # 检查组是否存在
        grp = db.execute("SELECT id FROM burst_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(404, "Burst group not found")
        return {"id": None, "task_id": None, "total": 0}

    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'recognize', 'pending')",
        (task_id,),
    )
    db.commit()

    photo_ids = [r["photo_id"] for r in photos]

    # 复用 photos.py 的批量识别逻辑
    from api.photos import _batch_recognize_task
    background_tasks.add_task(_batch_recognize_task, task_id, photo_ids)

    return {"id": task_id, "task_id": task_id, "total": len(photo_ids)}


@router.post("/bursts/recognize-all")
async def recognize_all_bursts(
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """一键识别所有连拍组中未识别的照片。"""
    # 防止重复
    existing = db.execute(
        "SELECT id FROM tasks WHERE type = 'recognize_all_bursts' AND status = 'running'"
    ).fetchone()
    if existing:
        total = db.execute(
            """SELECT COUNT(*) FROM burst_group_photos bgp
               LEFT JOIN photo_birds pb ON pb.photo_id = bgp.photo_id
               WHERE pb.id IS NULL"""
        ).fetchone()[0]
        return {"id": existing["id"], "task_id": existing["id"], "total": total}

    rows = db.execute(
        """SELECT DISTINCT bgp.photo_id FROM burst_group_photos bgp
           LEFT JOIN photo_birds pb ON pb.photo_id = bgp.photo_id
           WHERE pb.id IS NULL"""
    ).fetchall()
    photo_ids = [r["photo_id"] for r in rows]

    if not photo_ids:
        task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status, progress) VALUES (?, 'recognize_all_bursts', 'done', 100)",
            (task_id,),
        )
        db.commit()
        return {"id": task_id, "task_id": task_id, "total": 0}

    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'recognize_all_bursts', 'pending')",
        (task_id,),
    )
    db.commit()

    from api.photos import _batch_recognize_task
    background_tasks.add_task(_batch_recognize_task, task_id, photo_ids)

    return {"id": task_id, "task_id": task_id, "total": len(photo_ids)}


@router.post("/bursts/{group_id}/synthesize")
async def synthesize_burst(
    group_id: str,
    req: SynthesizeRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """合成连拍视频（异步任务）。"""
    group = db.execute("SELECT * FROM burst_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise HTTPException(404, "Burst group not found")

    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'synthesize', 'pending')",
        (task_id,),
    )
    db.commit()

    background_tasks.add_task(
        _synthesize_task, task_id, group_id, req.framerate, req.resolution,
    )
    return {"id": task_id, "task_id": task_id}


def _synthesize_task(task_id: str, group_id: str, framerate: int, resolution: str):
    """后台合成连拍视频。"""
    db = get_db_connection()

    def _update_task(progress: int, *, phase: str | None = None, detail: str | None = None,
                     processed: int | None = None, total: int | None = None,
                     status: str | None = None, error_msg: str | None = None):
        payload = {}
        if phase:
            payload["phase"] = phase
        if detail:
            payload["detail"] = detail
        if processed is not None:
            payload["processed"] = processed
        if total is not None:
            payload["total"] = total

        fields = ["progress = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list = [progress]
        if payload:
            fields.append("result_json = ?")
            params.append(json.dumps(payload, ensure_ascii=False))
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if error_msg is not None:
            fields.append("error_msg = ?")
            params.append(error_msg)
        params.append(task_id)

        db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", tuple(params))
        db.commit()

    try:
        _update_task(2, status="running", phase="loading_frames", detail="正在收集连拍照片")

        photos = db.execute("""
            SELECT p.original_path
            FROM burst_group_photos bgp
            JOIN photos p ON p.id = bgp.photo_id
            WHERE bgp.group_id = ?
            ORDER BY bgp.position
        """, (group_id,)).fetchall()

        image_paths = [r["original_path"] for r in photos if os.path.exists(r["original_path"])]
        if not image_paths:
            raise RuntimeError("No valid images for synthesis")

        _update_task(
            8,
            phase="loading_frames",
            detail=f"已收集 {len(image_paths)} 张照片，准备开始合成",
            processed=len(image_paths),
            total=len(image_paths),
        )

        output_path = os.path.join(app_config.burst_video_dir(), f"burst_{group_id}.mp4")

        def _on_progress(progress: int, payload: dict | None = None):
            payload = payload or {}
            _update_task(
                progress,
                phase=payload.get("phase"),
                detail=payload.get("detail"),
                processed=payload.get("processed"),
                total=payload.get("total"),
            )

        success = synthesize_burst_video(
            image_paths,
            output_path,
            framerate,
            resolution,
            progress_callback=_on_progress,
        )
        if not success:
            raise RuntimeError("FFmpeg synthesis failed")

        db.execute(
            "UPDATE burst_groups SET video_path = ? WHERE id = ?",
            (output_path, group_id),
        )
        _update_task(
            100,
            status="done",
            phase="done",
            detail="视频合成完成",
            processed=len(image_paths),
            total=len(image_paths),
        )
        db.commit()

    except Exception as e:
        logger.error("Synthesize task %s failed: %s", task_id, e)
        _update_task(
            0,
            status="error",
            phase="error",
            detail="视频合成失败",
            error_msg=str(e),
        )
    finally:
        db.close()


@router.get("/bursts/{group_id}/video")
async def get_burst_video(group_id: str, db=Depends(get_db)):
    """获取合成后的视频。"""
    group = db.execute("SELECT video_path FROM burst_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise HTTPException(404, "Burst group not found")
    if not group["video_path"] or not os.path.exists(group["video_path"]):
        raise HTTPException(404, "Video not yet synthesized")

    return FileResponse(
        group["video_path"],
        media_type="video/mp4",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
