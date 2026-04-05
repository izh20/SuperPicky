"""
重复/相似照片检测服务

- 精确重复：SHA256 匹配
- 视觉相似：pHash / dHash (imagehash)
"""

import uuid
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def find_duplicates(db) -> list[dict]:
    """检测重复照片，结果写入 duplicate_groups 表并返回。"""
    # 先清除旧的去重组
    db.execute("DELETE FROM duplicate_groups")
    db.commit()

    groups = []

    # ── 1. 精确重复（SHA256）──
    hash_groups = db.execute("""
        SELECT file_hash, GROUP_CONCAT(id) as ids, COUNT(*) as cnt
        FROM photos
        WHERE file_hash IS NOT NULL
        GROUP BY file_hash
        HAVING cnt > 1
    """).fetchall()

    for row in hash_groups:
        group_id = str(uuid.uuid4())
        ids = row["ids"].split(",")
        for pid in ids:
            db.execute(
                "INSERT INTO duplicate_groups (group_id, photo_id, hash_type, similarity) VALUES (?, ?, 'exact', 1.0)",
                (group_id, pid),
            )
        groups.append({
            "group_id": group_id,
            "hash_type": "exact",
            "photo_count": len(ids),
            "photo_ids": ids,
        })

    # ── 2. 视觉相似（pHash）──
    try:
        import imagehash
        from PIL import Image

        # 计算所有照片的 pHash
        photos = db.execute(
            "SELECT id, original_path FROM photos WHERE original_path IS NOT NULL"
        ).fetchall()

        hashes: dict[str, str] = {}  # photo_id → hash_str
        for photo in photos:
            try:
                img = Image.open(photo["original_path"])
                h = imagehash.phash(img)
                hashes[photo["id"]] = h
            except Exception:
                continue

        # 两两比较（O(n^2)，但 ≤10 用户场景照片量可控）
        ids = list(hashes.keys())
        similar_groups: dict[str, set] = {}  # 合并相似组
        visited = set()

        for i in range(len(ids)):
            if ids[i] in visited:
                continue
            group = {ids[i]}
            for j in range(i + 1, len(ids)):
                if ids[j] in visited:
                    continue
                distance = hashes[ids[i]] - hashes[ids[j]]
                if distance <= 10:  # 高度相似阈值
                    group.add(ids[j])

            if len(group) > 1:
                group_id = str(uuid.uuid4())
                for pid in group:
                    visited.add(pid)
                    distance = int(hashes[ids[i]] - hashes[pid])
                    similarity = max(0, 1.0 - distance / 64.0)
                    db.execute(
                        "INSERT INTO duplicate_groups (group_id, photo_id, hash_type, similarity) VALUES (?, ?, 'phash', ?)",
                        (group_id, pid, similarity),
                    )
                groups.append({
                    "group_id": group_id,
                    "hash_type": "phash",
                    "photo_count": len(group),
                    "photo_ids": list(group),
                })

    except ImportError:
        logger.warning("imagehash not installed, skipping visual similarity check")

    db.commit()
    return groups
