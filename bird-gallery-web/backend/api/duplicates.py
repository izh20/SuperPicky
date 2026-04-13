"""
去重检测 API

- 查找重复/相似照片
- 去重组操作
"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from models.database import get_db
from services.duplicate_detector import find_duplicates
from api.photos import _delete_photo_files
from api.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["duplicates"])


@router.post("/photos/find-duplicates")
async def detect_duplicates(background_tasks: BackgroundTasks, db=Depends(get_db)):
    """触发重复/相似照片检测（异步后台任务）。

    返回 task id。前端可通过 tasks 接口查询状态或结果。
    """
    # 如果已有正在运行的重复检测任务，返回该任务 id
    existing = db.execute(
        "SELECT id, progress FROM tasks WHERE type = 'find_duplicates' AND status = 'running'"
    ).fetchone()
    if existing:
        return {"id": existing["id"], "task_id": existing["id"]}

    task_id = str(uuid.uuid4())
    db.execute("INSERT INTO tasks (id, type, status) VALUES (?, 'find_duplicates', 'pending')", (task_id,))
    db.commit()

    # 启动后台任务（在独立线程中运行）
    from services.duplicate_detector import run_find_duplicates_task
    background_tasks.add_task(run_find_duplicates_task, task_id)

    return {"id": task_id, "task_id": task_id}


@router.get("/photos/groups/{group_id}")
async def get_duplicate_group(group_id: str, db=Depends(get_db)):
    """查看去重组详情。"""
    rows = db.execute("""
        SELECT dg.photo_id, dg.hash_type, dg.similarity,
               p.filename, p.original_path, p.file_size,
               ps.rating
        FROM duplicate_groups dg
        JOIN photos p ON p.id = dg.photo_id
        LEFT JOIN photo_scores ps ON p.id = ps.photo_id
        WHERE dg.group_id = ?
        ORDER BY COALESCE(ps.rating, 0) DESC, dg.similarity DESC
    """, (group_id,)).fetchall()

    if not rows:
        raise HTTPException(404, "Duplicate group not found")

    return {
        "group_id": group_id,
        "photos": [dict(r) for r in rows],
    }


@router.post("/photos/groups/{group_id}/keep/{photo_id}")
async def keep_photo(group_id: str, photo_id: str, db=Depends(get_db)):
    """保留指定照片，标记组内其他为冗余。"""
    rows = db.execute(
        "SELECT photo_id FROM duplicate_groups WHERE group_id = ?",
        (group_id,),
    ).fetchall()

    if not rows:
        raise HTTPException(404, "Group not found")

    photo_ids = [r["photo_id"] for r in rows]
    if photo_id not in photo_ids:
        raise HTTPException(400, "Photo not in this group")

    others = [pid for pid in photo_ids if pid != photo_id]

    # 将其他照片评分标记为 -1（冗余）
    for pid in others:
        existing = db.execute(
            "SELECT photo_id FROM photo_scores WHERE photo_id = ?", (pid,)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE photo_scores SET rating = -1 WHERE photo_id = ?", (pid,)
            )
        else:
            db.execute(
                "INSERT INTO photo_scores (photo_id, rating) VALUES (?, -1)", (pid,)
            )

    # 从去重组中移除已处理的记录
    db.execute(
        "DELETE FROM duplicate_groups WHERE group_id = ?", (group_id,)
    )
    db.commit()

    return {
        "kept": photo_id,
        "group_id": group_id,
        "others": others,
    }


@router.delete("/photos/groups/{group_id}/photo/{photo_id}", dependencies=[Depends(require_admin)])
async def delete_duplicate_photo(group_id: str, photo_id: str, db=Depends(get_db)):
    """从重复组中删除指定照片，同时删除磁盘文件。"""
    row = db.execute(
        "SELECT dg.photo_id, p.original_path "
        "FROM duplicate_groups dg JOIN photos p ON p.id = dg.photo_id "
        "WHERE dg.group_id = ? AND dg.photo_id = ?",
        (group_id, photo_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Photo not in this group")

    original_path = row["original_path"]

    # 删除照片关联数据
    db.execute("DELETE FROM photo_metadata WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photo_scores WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photo_birds WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photo_tags WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM burst_group_photos WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM duplicate_groups WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))

    # 如果组内只剩 0 或 1 张，自动清除该组
    remaining = db.execute(
        "SELECT COUNT(*) AS cnt FROM duplicate_groups WHERE group_id = ?",
        (group_id,),
    ).fetchone()["cnt"]
    if remaining <= 1:
        db.execute("DELETE FROM duplicate_groups WHERE group_id = ?", (group_id,))

    db.commit()

    _delete_photo_files(photo_id, original_path)

    return {"deleted": photo_id, "group_id": group_id, "remaining": remaining}
