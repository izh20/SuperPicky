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
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'detect_bursts', 'pending')",
        (task_id,),
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

            if same_camera and 0 < delta <= threshold:
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
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """列出所有连拍组。"""
    total = db.execute("SELECT COUNT(*) FROM burst_groups").fetchone()[0]
    offset = (page - 1) * page_size

    rows = db.execute("""
        SELECT bg.*, COUNT(bgp.photo_id) as actual_count
        FROM burst_groups bg
        LEFT JOIN burst_group_photos bgp ON bg.id = bgp.group_id
        GROUP BY bg.id
        ORDER BY bg.created_at DESC
        LIMIT ? OFFSET ?
    """, (page_size, offset)).fetchall()

    return {"total": total, "page": page, "groups": [dict(r) for r in rows]}


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
    """批量识别连拍照片。"""
    photos = db.execute(
        "SELECT photo_id FROM burst_group_photos WHERE group_id = ?",
        (group_id,),
    ).fetchall()
    if not photos:
        raise HTTPException(404, "Burst group not found or empty")

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

    return {"id": task_id, "task_id": task_id}


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
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

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

        output_path = os.path.join(app_config.burst_video_dir(), f"burst_{group_id}.mp4")

        success = synthesize_burst_video(image_paths, output_path, framerate, resolution)
        if not success:
            raise RuntimeError("FFmpeg synthesis failed")

        db.execute(
            "UPDATE burst_groups SET video_path = ? WHERE id = ?",
            (output_path, group_id),
        )
        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

    except Exception as e:
        logger.error("Synthesize task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
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

    return FileResponse(group["video_path"], media_type="video/mp4")
