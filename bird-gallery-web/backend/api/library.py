"""
图库扫描导入 API + 仪表盘统计

- 扫描本地目录导入（异步任务）
- 仪表盘统计
"""

import os
import uuid
import logging
import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from models.database import get_db, get_db_connection
from api.auth import require_admin
from app_config_pkg import config as app_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["library"])

# 白名单：allowed scan roots（防止路径穿越）
# 默认系统目录 + 环境变量 SCAN_EXTRA_ROOTS + config.json 中的 scan_roots
_DEFAULT_SCAN_ROOTS = [
    os.path.expanduser("~/Pictures"),
    os.path.expanduser("~/Photos"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads"),
    "/Volumes",
]
_extra = os.environ.get("SCAN_EXTRA_ROOTS", "")
if _extra:
    _DEFAULT_SCAN_ROOTS.extend(p.strip() for p in _extra.split(":") if p.strip())


def _get_allowed_scan_roots() -> list[str]:
    """获取合并后的扫描白名单（系统默认 + 环境变量 + config.json）。"""
    roots = list(_DEFAULT_SCAN_ROOTS)
    roots.extend(app_config.get_scan_roots())
    return roots

_PHOTO_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.heif', '.heic',
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2',
}


class ScanRequest(BaseModel):
    path: str
    recursive: bool = True


def _validate_scan_path(path: str) -> str:
    """校验扫描路径在白名单内，防止路径穿越。"""
    real_path = os.path.realpath(path)
    allowed = _get_allowed_scan_roots()
    for root in allowed:
        real_root = os.path.realpath(root)
        if real_path == real_root or real_path.startswith(real_root + os.sep):
            return real_path
    raise HTTPException(
        403,
        f"Path not in allowed roots. Allowed: {allowed}",
    )


@router.post("/library/scan", dependencies=[Depends(require_admin)])
async def scan_library(
    req: ScanRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """扫描本地目录导入照片（后台异步执行）。"""
    safe_path = _validate_scan_path(req.path)

    if not os.path.isdir(safe_path):
        raise HTTPException(404, f"Directory not found: {safe_path}")

    task_id = str(uuid.uuid4())
    config_json = json.dumps({"path": safe_path, "recursive": req.recursive}, ensure_ascii=False)
    db.execute(
        "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'scan', 'pending', ?)",
        (task_id, config_json),
    )
    db.commit()

    background_tasks.add_task(_scan_task, task_id, safe_path, req.recursive)
    return {"id": task_id, "task_id": task_id}


def _scan_task(task_id: str, scan_dir: str, recursive: bool):
    """后台扫描任务。"""
    import hashlib
    from services.thumbnail_generator import generate_thumbnail, get_image_dimensions, generate_preview_jpeg

    db = get_db_connection()
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        # 收集文件
        files = []
        if recursive:
            for root, dirs, filenames in os.walk(scan_dir):
                # 跳过隐藏目录（如 .superpicky/cache）
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for fn in filenames:
                    if fn.startswith('.'):
                        continue
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in _PHOTO_EXTENSIONS:
                        files.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(scan_dir):
                ext = os.path.splitext(fn)[1].lower()
                if ext in _PHOTO_EXTENSIONS:
                    files.append(os.path.join(scan_dir, fn))

        total = len(files)
        imported = 0

        for i, fpath in enumerate(files):
            try:
                # 检查是否已导入（通过 original_path 去重）
                existing = db.execute(
                    "SELECT id FROM photos WHERE original_path = ?",
                    (os.path.realpath(fpath),),
                ).fetchone()
                if existing:
                    continue

                photo_id = str(uuid.uuid4())
                file_size = os.path.getsize(fpath)

                # SHA256
                h = hashlib.sha256()
                with open(fpath, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        h.update(chunk)
                file_hash = h.hexdigest()

                # 尺寸
                dims = get_image_dimensions(fpath)
                width, height = dims if dims else (None, None)

                db.execute(
                    """INSERT INTO photos (id, original_path, filename, file_hash, width, height, file_size)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (photo_id, os.path.realpath(fpath), os.path.basename(fpath),
                     file_hash, width, height, file_size),
                )

                # 提取 EXIF 元数据
                _extract_exif_sync(db, photo_id, fpath)

                # 生成小缩略图
                generate_thumbnail(fpath, photo_id, "sm")
                # 预生成 JPEG 缓存供 AI 推理使用 (D 优化)
                generate_preview_jpeg(fpath, photo_id)
                imported += 1

            except Exception as e:
                logger.warning("Scan import failed for %s: %s", fpath, e)

            progress = int((i + 1) / max(total, 1) * 100)
            db.execute(
                "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (progress, task_id),
            )
            db.commit()

        result = f'{{"scanned": {total}, "imported": {imported}}}'
        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, result_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (result, task_id),
        )
        db.commit()

    except Exception as e:
        logger.error("Scan task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()


@router.get("/stats/dashboard")
async def dashboard_stats(db=Depends(get_db)):
    """仪表盘统计。"""
    photos_count = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    videos_count = db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

    species_count = db.execute(
        "SELECT COUNT(DISTINCT species_cn) FROM photo_birds WHERE species_cn IS NOT NULL AND rank = 1 AND confidence >= 70"
    ).fetchone()[0]

    recent_photos = db.execute(
        "SELECT id, filename, imported_at FROM photos ORDER BY imported_at DESC LIMIT 5"
    ).fetchall()

    burst_count = db.execute("SELECT COUNT(*) FROM burst_groups").fetchone()[0]

    return {
        "photos": photos_count,
        "videos": videos_count,
        "species": species_count,
        "bursts": burst_count,
        "recent_photos": [dict(r) for r in recent_photos],
    }


@router.get("/library/dashboard")
async def dashboard_stats_compat(db=Depends(get_db)):
    """兼容前端旧路径，复用 dashboard 统计逻辑。"""
    return await dashboard_stats(db)


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(str(v).split()[0])
    except (ValueError, TypeError):
        return None


def _safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _extract_exif_sync(db, photo_id: str, file_path: str):
    """同步提取 EXIF 并存入 photo_metadata 表（供 BackgroundTask 使用）。"""
    try:
        from tools.exiftool_manager import get_exiftool_manager
        etm = get_exiftool_manager()
        meta = etm.read_metadata(
            file_path,
            [
                "-Make", "-Model", "-LensModel",
                "-ISO", "-ExposureTime", "-FNumber",
                "-FocalLength", "-FocalLengthIn35mmFormat",
                "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
                "-DateTimeOriginal", "-OffsetTimeOriginal",
            ],
        )
        if not meta:
            return

        db.execute(
            """INSERT OR REPLACE INTO photo_metadata
               (photo_id, camera_make, camera_model, lens_model,
                iso, shutter_speed, aperture,
                focal_length, focal_length_35mm,
                gps_lat, gps_lon, gps_altitude,
                date_taken, timezone)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                photo_id,
                meta.get("Make"), meta.get("Model"), meta.get("LensModel"),
                _safe_int(meta.get("ISO")),
                meta.get("ExposureTime"),
                _safe_float(meta.get("FNumber")),
                _safe_float(meta.get("FocalLength")),
                _safe_float(meta.get("FocalLengthIn35mmFormat")),
                _safe_float(meta.get("GPSLatitude")),
                _safe_float(meta.get("GPSLongitude")),
                _safe_float(meta.get("GPSAltitude")),
                meta.get("DateTimeOriginal"),
                meta.get("OffsetTimeOriginal"),
            ),
        )
        db.commit()
    except Exception as e:
        logger.warning("EXIF extraction failed for %s: %s", photo_id, e)
