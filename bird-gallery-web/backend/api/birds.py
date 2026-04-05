"""
鸟种 API

- 列出所有已识别鸟种
- 某鸟种的照片
- 鸟种统计
- 重建符号链接目录（异步）
"""

import os
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from models.database import get_db, get_db_connection
from api.auth import require_admin
from app_config_pkg import config as app_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["birds"])


@router.get("/birds")
async def list_birds(db=Depends(get_db)):
    """列出所有已识别鸟种。"""
    rows = db.execute("""
        SELECT species_cn, species_en, scientific_name,
               COUNT(DISTINCT photo_id) as photo_count,
               MAX(confidence) as max_confidence
        FROM photo_birds
        WHERE species_cn IS NOT NULL AND rank = 1
        GROUP BY species_cn, species_en, scientific_name
        ORDER BY photo_count DESC
    """).fetchall()

    return [dict(r) for r in rows]


@router.get("/birds/{species}/photos")
async def bird_photos(
    species: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """某鸟种的所有照片。"""
    offset = (page - 1) * page_size

    total = db.execute(
        """SELECT COUNT(DISTINCT pb.photo_id) FROM photo_birds pb
           WHERE pb.species_cn = ? OR pb.species_en = ?""",
        (species, species),
    ).fetchone()[0]

    rows = db.execute("""
        SELECT DISTINCT p.id, p.filename, p.imported_at,
               ps.rating, pb.confidence
        FROM photo_birds pb
        JOIN photos p ON p.id = pb.photo_id
        LEFT JOIN photo_scores ps ON p.id = ps.photo_id
        WHERE pb.species_cn = ? OR pb.species_en = ?
        ORDER BY pb.confidence DESC
        LIMIT ? OFFSET ?
    """, (species, species, page_size, offset)).fetchall()

    return {
        "species": species,
        "total": total,
        "page": page,
        "page_size": page_size,
        "photos": [dict(r) for r in rows],
    }


@router.get("/birds/stats")
async def bird_stats(db=Depends(get_db)):
    """鸟种统计。"""
    total_species = db.execute(
        "SELECT COUNT(DISTINCT species_cn) FROM photo_birds WHERE species_cn IS NOT NULL"
    ).fetchone()[0]

    top_species = db.execute("""
        SELECT species_cn, species_en, COUNT(DISTINCT photo_id) as count
        FROM photo_birds
        WHERE species_cn IS NOT NULL
        GROUP BY species_cn, species_en
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()

    total_identified = db.execute(
        "SELECT COUNT(DISTINCT photo_id) FROM photo_birds"
    ).fetchone()[0]

    return {
        "total_species": total_species,
        "total_identified_photos": total_identified,
        "top_species": [dict(r) for r in top_species],
    }


@router.post("/birds/organize", dependencies=[Depends(require_admin)])
async def organize_birds(
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """重建鸟种符号链接目录（异步任务）。"""
    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'organize', 'pending')",
        (task_id,),
    )
    db.commit()
    background_tasks.add_task(_organize_task, task_id)
    return {"id": task_id, "task_id": task_id}


def _organize_task(task_id: str):
    """后台构建鸟种符号链接目录。"""
    db = get_db_connection()
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        # 清理旧链接
        by_bird_dir = app_config.gallery_by_bird_dir()
        if os.path.exists(by_bird_dir):
            import shutil
            shutil.rmtree(by_bird_dir)
        os.makedirs(by_bird_dir, exist_ok=True)

        # 按鸟种分组
        rows = db.execute("""
            SELECT pb.species_cn, pb.species_en, pb.scientific_name,
                   p.original_path, p.filename
            FROM photo_birds pb
            JOIN photos p ON p.id = pb.photo_id
            WHERE pb.rank = 1 AND pb.species_cn IS NOT NULL
        """).fetchall()

        total = len(rows)
        created = 0

        for i, row in enumerate(rows):
            try:
                # 目录名: 中文名_英文名_学名
                cn = row["species_cn"] or "未识别"
                en = (row["species_en"] or "").replace(" ", "_")
                sci = (row["scientific_name"] or "").replace(" ", "_")
                dir_name = f"{cn}_{en}_{sci}".rstrip("_")

                # 清洗目录名
                for ch in ('/', '\\', '\x00'):
                    dir_name = dir_name.replace(ch, '_')

                species_dir = os.path.join(by_bird_dir, dir_name)
                os.makedirs(species_dir, exist_ok=True)

                src = row["original_path"]
                dst = os.path.join(species_dir, row["filename"])

                if os.path.exists(src) and not os.path.exists(dst):
                    os.symlink(src, dst)
                    created += 1

            except Exception as e:
                logger.warning("Symlink failed: %s", e)

            progress = int((i + 1) / max(total, 1) * 100)
            if i % 50 == 0:
                db.execute(
                    "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (progress, task_id),
                )
                db.commit()

        result = f'{{"total": {total}, "created": {created}}}'
        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, result_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (result, task_id),
        )
        db.commit()

    except Exception as e:
        logger.error("Organize task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()
