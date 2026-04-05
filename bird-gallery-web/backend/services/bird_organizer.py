"""
鸟种符号链接目录整理服务

根据 photo_birds 表中的识别结果，在 data/gallery/by_bird/ 下
为每个鸟种创建符号链接，指向原始照片路径。
"""

import os
import shutil
import logging

logger = logging.getLogger(__name__)


def rebuild_bird_index(db, by_bird_dir: str, progress_cb=None) -> int:
    """重建鸟种符号链接目录。

    Args:
        db: SQLite 连接
        by_bird_dir: 目标符号链接根目录
        progress_cb: 可选的进度回调 (current, total) -> None

    Returns:
        创建的符号链接数量
    """
    # 清理旧链接
    if os.path.exists(by_bird_dir):
        shutil.rmtree(by_bird_dir)
    os.makedirs(by_bird_dir, exist_ok=True)

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
            cn = row["species_cn"] or "未识别"
            en = (row["species_en"] or "").replace(" ", "_")
            sci = (row["scientific_name"] or "").replace(" ", "_")
            dir_name = f"{cn}_{en}_{sci}".rstrip("_")

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

        if progress_cb and i % 50 == 0:
            progress_cb(i + 1, total)

    return created
