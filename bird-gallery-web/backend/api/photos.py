"""
照片管理 API — Phase 1

- 上传照片（白名单校验）
- 照片列表查询（分页+筛选）
- 照片详情
- 缩略图（用于 nginx @fastapi 回退懒生成）
- 单张识别
- 批量识别（异步任务）
"""

import os
import shutil
import uuid
import hashlib
import logging
import json
import tempfile
import subprocess
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from models.database import get_db
from api.auth import require_admin
from models.schemas import (
    PhotoDetail, PhotoMetadata, BirdResult, PhotoScore,
    PhotoListItem, PhotoListResponse, RecognizeResponse,
    BatchRecognizeRequest, TaskResponse,
)
from services.thumbnail_generator import (
    generate_all_thumbnails, generate_thumbnail, get_thumbnail_path,
    get_image_dimensions,
)
from services.model_manager import model_manager
from app_config_pkg import config as app_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["photos"])

# ── 常量 ──

# 白名单
_PHOTO_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.heif', '.heic',
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2',
}

_MAX_SINGLE_FILE = 10 * 1024 * 1024 * 1024  # 10GB


class ExifTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def _delete_photo_files(photo_id: str, original_path: str | None):
    """删除照片源文件及缩略图目录。"""
    if original_path and os.path.exists(original_path):
        try:
            os.unlink(original_path)
        except OSError as e:
            logger.warning("Failed to delete photo file %s: %s", original_path, e)
    # 删除缩略图目录
    thumb_dir = app_config.thumbnails_dir(photo_id)
    if os.path.isdir(thumb_dir):
        try:
            shutil.rmtree(thumb_dir)
        except OSError as e:
            logger.warning("Failed to delete thumbnail dir %s: %s", thumb_dir, e)


def _sanitize_filename(name: str) -> str:
    """文件名清洗：去除路径分隔符和危险字符。"""
    for ch in ('/', '\\', '..', '\x00'):
        name = name.replace(ch, '_')
    return name.strip()


def _validate_extension(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in _PHOTO_EXTENSIONS


def _file_hash(path: str) -> str:
    """计算文件 SHA256（流式读取，支持大文件）。"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _normalize_yolo_info(result: dict) -> dict:
    """兼容 yolo_info 可能为 dict / JSON 字符串 / 其他类型。"""
    yolo_info = result.get("yolo_info")
    if isinstance(yolo_info, dict):
        return yolo_info
    if isinstance(yolo_info, str):
        try:
            parsed = json.loads(yolo_info)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"detected": bool(yolo_info.strip()), "raw": yolo_info}
    return {}


# ── 上传 ──

@router.post("/photos/upload")
async def upload_photo(
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """上传单张照片（multipart/form-data）。"""
    if not file.filename:
        raise HTTPException(400, "Missing filename")

    safe_name = _sanitize_filename(file.filename)
    if not _validate_extension(safe_name):
        raise HTTPException(
            400,
            f"Unsupported file type. Allowed: {', '.join(sorted(_PHOTO_EXTENSIONS))}",
        )

    photo_id = str(uuid.uuid4())

    # 存储到 data/uploads/photos/
    upload_dir = app_config.photos_upload_dir()

    ext = os.path.splitext(safe_name)[1].lower()
    dest_path = os.path.join(upload_dir, f"{photo_id}{ext}")

    # 流式写入
    total_size = 0
    h = hashlib.sha256()
    with open(dest_path, 'wb') as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > _MAX_SINGLE_FILE:
                f.close()
                os.unlink(dest_path)
                raise HTTPException(413, "File too large (max 10GB)")
            h.update(chunk)
            f.write(chunk)

    file_hash = h.hexdigest()

    # 获取图片尺寸
    dims = get_image_dimensions(dest_path)
    width, height = dims if dims else (None, None)

    # 插入数据库
    db.execute(
        """INSERT INTO photos (id, original_path, filename, file_hash, width, height, file_size)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (photo_id, dest_path, safe_name, file_hash, width, height, total_size),
    )
    db.commit()

    # 生成缩略图（同步生成 sm，其他延迟）
    await run_in_threadpool(generate_thumbnail, dest_path, photo_id, "sm")

    # EXIF 元数据提取
    await _extract_and_store_exif(photo_id, dest_path, db)

    return {
        "id": photo_id,
        "photo_id": photo_id,
        "filename": safe_name,
        "size": total_size,
    }


@router.post("/photos/upload-folder")
async def upload_folder(
    files: list[UploadFile] = File(...),
    db=Depends(get_db),
):
    """批量上传文件夹中的照片（multipart 多文件）。"""
    if not files:
        raise HTTPException(400, "No files uploaded")

    results = []
    failed = []
    for f in files:
        try:
            item = await upload_photo(f, db)
            results.append(item)
        except Exception as e:
            failed.append({"filename": f.filename, "error": str(e)})

    return {
        "uploaded": len(results),
        "failed": len(failed),
        "items": results,
        "errors": failed,
    }


async def _extract_and_store_exif(photo_id: str, file_path: str, db):
    """提取 EXIF 并存入 photo_metadata 表。"""
    try:
        from tools.exiftool_manager import get_exiftool_manager
        etm = get_exiftool_manager()
        meta = await run_in_threadpool(
            etm.read_metadata,
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


def _safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(str(v).split()[0])  # "500.0 mm" → 500.0
    except (ValueError, TypeError):
        return None


# ── 筛选选项 ──

@router.get("/photos/filter-options")
async def get_filter_options(db=Depends(get_db)):
    """返回当前照片库中可用的筛选项（鸟种、日期、相机型号）。"""
    species_rows = db.execute(
        "SELECT DISTINCT species_cn FROM photo_birds WHERE species_cn IS NOT NULL AND rank = 1 ORDER BY species_cn"
    ).fetchall()

    camera_rows = db.execute(
        "SELECT DISTINCT camera_model FROM photo_metadata WHERE camera_model IS NOT NULL AND camera_model != '' ORDER BY camera_model"
    ).fetchall()

    date_rows = db.execute(
        "SELECT DISTINCT substr(date_taken, 1, 10) as d FROM photo_metadata WHERE date_taken IS NOT NULL ORDER BY d DESC"
    ).fetchall()

    return {
        "species": [r["species_cn"] for r in species_rows],
        "cameras": [r["camera_model"] for r in camera_rows],
        "dates": [r["d"] for r in date_rows],
    }


# ── 查询 ──

@router.get("/photos", response_model=PhotoListResponse)
async def list_photos(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    q: str | None = None,
    species: str | None = None,
    rating_min: int | None = None,
    rating_max: int | None = None,
    camera: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    iso_min: int | None = None,
    iso_max: int | None = None,
    aperture_min: float | None = None,
    aperture_max: float | None = None,
    shutter_speed: str | None = None,
    has_gps: bool | None = None,
    db=Depends(get_db),
):
    """分页查询照片列表，支持多条件筛选。"""
    conditions = []
    params = []

    if q:
        conditions.append(
            "(p.filename LIKE ? OR p.id IN (SELECT photo_id FROM photo_birds WHERE species_cn LIKE ? OR species_en LIKE ?))"
        )
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if species:
        conditions.append(
            "p.id IN (SELECT photo_id FROM photo_birds WHERE species_cn LIKE ? OR species_en LIKE ?)"
        )
        params.extend([f"%{species}%", f"%{species}%"])
    if rating_min is not None:
        conditions.append("ps.rating >= ?")
        params.append(rating_min)
    if rating_max is not None:
        conditions.append("ps.rating <= ?")
        params.append(rating_max)
    if camera:
        conditions.append("pm.camera_model LIKE ?")
        params.append(f"%{camera}%")
    if date_from:
        conditions.append("pm.date_taken >= ?")
        params.append(date_from)
    if date_to:
        if len(date_to) <= 10:
            conditions.append("pm.date_taken < ?")
            try:
                from datetime import datetime, timedelta
                sep = ':' if ':' in date_to[:5] else '-'
                dt = datetime.strptime(date_to, f"%Y{sep}%m{sep}%d")
                next_day = (dt + timedelta(days=1)).strftime(f"%Y{sep}%m{sep}%d")
                params.append(next_day)
            except ValueError:
                conditions.pop()
                conditions.append("pm.date_taken <= ?")
                params.append(date_to)
        else:
            conditions.append("pm.date_taken <= ?")
            params.append(date_to)
    if iso_min is not None:
        conditions.append("pm.iso >= ?")
        params.append(iso_min)
    if iso_max is not None:
        conditions.append("pm.iso <= ?")
        params.append(iso_max)
    if aperture_min is not None:
        conditions.append("pm.aperture >= ?")
        params.append(aperture_min)
    if aperture_max is not None:
        conditions.append("pm.aperture <= ?")
        params.append(aperture_max)
    if shutter_speed:
        conditions.append("pm.shutter_speed = ?")
        params.append(shutter_speed)
    if has_gps is not None:
        if has_gps:
            conditions.append("pm.gps_lat IS NOT NULL AND pm.gps_lon IS NOT NULL")
        else:
            conditions.append("(pm.gps_lat IS NULL OR pm.gps_lon IS NULL)")

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # Count
    count_sql = f"""
        SELECT COUNT(*) FROM photos p
        LEFT JOIN photo_metadata pm ON p.id = pm.photo_id
        LEFT JOIN photo_scores ps ON p.id = ps.photo_id
        {where}
    """
    total = db.execute(count_sql, params).fetchone()[0]

    # Query — 包含置信度、锐度、美学供前端展示
    offset = (page - 1) * page_size
    query_sql = f"""
        SELECT p.id, p.filename, ps.rating, ps.head_sharp, ps.nima_score,
               pm.date_taken, p.imported_at,
               (SELECT pb.species_cn FROM photo_birds pb
                WHERE pb.photo_id = p.id ORDER BY pb.confidence DESC LIMIT 1) as species_cn,
               (SELECT pb.confidence FROM photo_birds pb
                WHERE pb.photo_id = p.id ORDER BY pb.confidence DESC LIMIT 1) as top_confidence
        FROM photos p
        LEFT JOIN photo_metadata pm ON p.id = pm.photo_id
        LEFT JOIN photo_scores ps ON p.id = ps.photo_id
        {where}
        ORDER BY COALESCE(pm.date_taken, p.imported_at) DESC
        LIMIT ? OFFSET ?
    """
    rows = db.execute(query_sql, params + [page_size, offset]).fetchall()

    items = [
        PhotoListItem(
            id=row["id"],
            filename=row["filename"],
            rating=row["rating"],
            species_cn=row["species_cn"],
            confidence=row["top_confidence"] if isinstance(row["top_confidence"], (int, float)) else None,
            head_sharp=row["head_sharp"] if isinstance(row["head_sharp"], (int, float)) else None,
            nima_score=row["nima_score"] if isinstance(row["nima_score"], (int, float)) else None,
            date_taken=row["date_taken"],
            imported_at=row["imported_at"],
        )
        for row in rows
    ]

    return PhotoListResponse(items=items, total=total, page=page, page_size=page_size)


# ── 评分配置 ──

# 默认评分阈值（与 RatingEngine 默认值一致）
_DEFAULT_RATING_CONFIG = {
    "min_confidence": 0.50,
    "min_sharpness": 100,
    "min_nima": 3.5,
    "sharpness_threshold": 400,
    "nima_threshold": 5.0,
}


class RatingConfigUpdate(BaseModel):
    min_confidence: float = Field(None, ge=0.0, le=1.0)
    min_sharpness: float = Field(None, ge=0, le=1000)
    min_nima: float = Field(None, ge=1.0, le=10.0)
    sharpness_threshold: float = Field(None, ge=0, le=1000)
    nima_threshold: float = Field(None, ge=1.0, le=10.0)


def _get_config_path() -> str:
    cfg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, 'rating_config.json')


def _load_rating_config() -> dict:
    path = _get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            merged = {**_DEFAULT_RATING_CONFIG, **cfg}
            return merged
        except Exception:
            pass
    return dict(_DEFAULT_RATING_CONFIG)


def _save_rating_config(cfg: dict):
    path = _get_config_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _make_rating_engine() -> 'RatingEngine':
    """根据当前配置创建 RatingEngine 实例。"""
    from core.rating_engine import RatingEngine
    cfg = _load_rating_config()
    return RatingEngine(
        min_confidence=cfg["min_confidence"],
        min_sharpness=cfg["min_sharpness"],
        min_nima=cfg["min_nima"],
        sharpness_threshold=cfg["sharpness_threshold"],
        nima_threshold=cfg["nima_threshold"],
    )


@router.get("/photos/rating-config")
async def get_rating_config():
    """获取当前评分配置。"""
    cfg = _load_rating_config()
    return {
        "config": cfg,
        "defaults": _DEFAULT_RATING_CONFIG,
        "rules": [
            {"key": "min_confidence", "label": "AI 置信度最低阈值",
             "desc": "低于此值的照片评为 0 星（问题照片）", "unit": "", "min": 0.0, "max": 1.0, "step": 0.05},
            {"key": "min_sharpness", "label": "头部锐度最低阈值",
             "desc": "鸟头区域锐度低于此值评为 0 星", "unit": "", "min": 0, "max": 500, "step": 10},
            {"key": "min_nima", "label": "TOPIQ 美学最低阈值",
             "desc": "美学评分低于此值评为 0 星", "unit": "分", "min": 1.0, "max": 10.0, "step": 0.1},
            {"key": "sharpness_threshold", "label": "锐度达标阈值",
             "desc": "锐度 ≥ 此值算「锐度达标」，影响 2★/3★ 判定", "unit": "", "min": 100, "max": 800, "step": 10},
            {"key": "nima_threshold", "label": "TOPIQ 美学达标阈值",
             "desc": "美学 ≥ 此值算「美学达标」，影响 2★/3★ 判定", "unit": "分", "min": 3.0, "max": 8.0, "step": 0.1},
        ],
        "scoring_logic": [
            "❌ -1 星：未检测到鸟（排除）",
            "0 星：置信度 < min_confidence，或锐度 < min_sharpness，或美学 < min_nima",
            "★ 1 星：关键点不可见（无法看到眼睛/鸟嘴），或通过最低标准但锐度和美学都不达标",
            "★★ 2 星：锐度达标 或 美学达标（满足其一）",
            "★★★ 3 星：锐度 + 美学双达标（优选）",
            "附加规则：眼睛可见度低（<0.5）会降级；曝光问题会降一级",
        ],
    }


@router.put("/photos/rating-config", dependencies=[Depends(require_admin)])
async def update_rating_config(req: RatingConfigUpdate):
    """更新评分配置。"""
    cfg = _load_rating_config()
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    cfg.update(updates)
    _save_rating_config(cfg)
    return {"config": cfg}


@router.post("/photos/rating-config/reset", dependencies=[Depends(require_admin)])
async def reset_rating_config():
    """恢复默认评分配置。"""
    _save_rating_config(dict(_DEFAULT_RATING_CONFIG))
    return {"config": dict(_DEFAULT_RATING_CONFIG)}


@router.post("/photos/recognize-all")
async def recognize_all(
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """一键识别图库中所有未识别的照片（异步任务）。"""
    rows = db.execute(
        """SELECT p.id FROM photos p
           LEFT JOIN photo_birds pb ON pb.photo_id = p.id
           WHERE pb.id IS NULL"""
    ).fetchall()
    photo_ids = [r["id"] for r in rows]

    if not photo_ids:
        task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status, progress) VALUES (?, 'recognize_all', 'done', 100)",
            (task_id,),
        )
        db.commit()
        return {"id": task_id, "task_id": task_id, "total": 0}

    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'recognize_all', 'pending')",
        (task_id,),
    )
    db.commit()

    background_tasks.add_task(_batch_recognize_task, task_id, photo_ids)
    return {"id": task_id, "task_id": task_id, "total": len(photo_ids)}


@router.post("/photos/recalculate-ratings")
async def recalculate_ratings(
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """按当前评分配置重新计算所有已有评分数据的照片评分（不重跑识别）。"""
    rows = db.execute(
        """SELECT ps.photo_id, ps.head_sharp, ps.nima_score,
                  pm.iso
           FROM photo_scores ps
           LEFT JOIN photo_metadata pm ON pm.photo_id = ps.photo_id
           WHERE ps.rating != -1"""
    ).fetchall()

    if not rows:
        task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status, progress) VALUES (?, 'recalculate', 'done', 100)",
            (task_id,),
        )
        db.commit()
        return {"id": task_id, "task_id": task_id, "total": 0}

    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'recalculate', 'pending')",
        (task_id,),
    )
    db.commit()

    score_data = [
        {
            "photo_id": r["photo_id"],
            "head_sharp": r["head_sharp"],
            "nima_score": r["nima_score"],
            "iso": r["iso"],
        }
        for r in rows
    ]
    background_tasks.add_task(_recalculate_ratings_task, task_id, score_data)
    return {"id": task_id, "task_id": task_id, "total": len(score_data)}


class BatchDeleteRequest(BaseModel):
    photo_ids: list[str] = Field(..., min_length=1, max_length=500)


@router.post("/photos/batch-delete", dependencies=[Depends(require_admin)])
async def batch_delete_photos(req: BatchDeleteRequest, db=Depends(get_db)):
    """批量删除照片及其磁盘文件，级联删除关联数据。"""
    placeholders = ",".join("?" for _ in req.photo_ids)
    rows = db.execute(
        f"SELECT id, original_path FROM photos WHERE id IN ({placeholders})", req.photo_ids
    ).fetchall()
    file_map = {r["id"]: r["original_path"] for r in rows}
    found_ids = list(file_map.keys())
    if not found_ids:
        raise HTTPException(404, "No valid photo IDs found")

    for pid in found_ids:
        db.execute("DELETE FROM photo_metadata WHERE photo_id = ?", (pid,))
        db.execute("DELETE FROM photo_scores WHERE photo_id = ?", (pid,))
        db.execute("DELETE FROM photo_birds WHERE photo_id = ?", (pid,))
        db.execute("DELETE FROM photo_tags WHERE photo_id = ?", (pid,))
        db.execute("DELETE FROM burst_group_photos WHERE photo_id = ?", (pid,))
        db.execute("DELETE FROM duplicate_groups WHERE photo_id = ?", (pid,))
        db.execute("DELETE FROM photos WHERE id = ?", (pid,))
    db.commit()

    for pid in found_ids:
        _delete_photo_files(pid, file_map[pid])

    return {"deleted": len(found_ids), "ids": found_ids}


@router.get("/photos/{photo_id}", response_model=PhotoDetail)
async def get_photo(photo_id: str, db=Depends(get_db)):
    """照片详情：含 EXIF、识别结果、评分。"""
    photo = db.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not photo:
        raise HTTPException(404, "Photo not found")

    meta_row = db.execute(
        "SELECT * FROM photo_metadata WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    metadata = PhotoMetadata(**dict(meta_row)) if meta_row else None

    birds_rows = db.execute(
        "SELECT * FROM photo_birds WHERE photo_id = ? ORDER BY rank", (photo_id,)
    ).fetchall()
    birds = [BirdResult(**dict(r)) for r in birds_rows]

    score_row = db.execute(
        "SELECT * FROM photo_scores WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    scores = PhotoScore(**dict(score_row)) if score_row else None

    return PhotoDetail(
        id=photo["id"],
        filename=photo["filename"],
        original_path=photo["original_path"],
        file_size=photo["file_size"],
        width=photo["width"],
        height=photo["height"],
        imported_at=photo["imported_at"],
        metadata=metadata,
        birds=birds,
        score=scores,
    )


# ── 缩略图（nginx @fastapi 回退懒生成）──

@router.get("/photos/{photo_id}/thumbnail")
async def get_thumbnail(
    photo_id: str,
    size: str = Query("sm", pattern="^(sm|md|lg)$"),
    db=Depends(get_db),
):
    """懒生成缩略图并返回。nginx 配置 try_files 回退到此路由。"""
    # 先检查是否已存在
    existing = get_thumbnail_path(photo_id, size)
    if existing:
        return FileResponse(existing, media_type="image/jpeg")

    # 查找原始文件路径
    photo = db.execute(
        "SELECT original_path FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    if not photo:
        raise HTTPException(404, "Photo not found")

    path = await run_in_threadpool(generate_thumbnail, photo["original_path"], photo_id, size)
    if not path:
        raise HTTPException(500, "Failed to generate thumbnail")

    return FileResponse(path, media_type="image/jpeg")


@router.get("/photos/{photo_id}/original")
async def get_original(photo_id: str, db=Depends(get_db)):
    """下载原图（受 nginx Basic Auth 保护）。"""
    row = db.execute(
        "SELECT original_path, filename FROM photos WHERE id = ?",
        (photo_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Photo not found")

    path = row["original_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Original file not found")

    return FileResponse(path, filename=row["filename"])


def _write_exif_text_with_tempfile(file_path: str, text: str, tags: list[str]) -> dict:
    """使用 UTF-8 临时文件重定向写入 Exif（避免中文乱码）。"""
    from tools.exiftool_manager import get_exiftool_manager

    etm = get_exiftool_manager()
    fd, temp_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)

        cmd = [
            etm.exiftool_path,
            "-charset", "utf8",
            "-overwrite_original_in_place",
        ]
        for tag in tags:
            cmd.append(f"-{tag}<={temp_path}")
        cmd.append(file_path)

        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(err.strip() or "Exif write failed")

        read_tags = [f"-{t}" for t in tags]
        meta = etm.read_metadata(file_path, read_tags) or {}
        return meta
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _write_exif_bird_info(file_path: str, birds: list, rating: int | None):
    """将识别结果和评分自动写入 EXIF/XMP/IPTC（UTF-8 安全）。"""
    if not file_path or not os.path.exists(file_path):
        return

    top_bird = None
    for b in (birds or []):
        species = getattr(b, 'species_cn', None) or (b.get('species_cn') if isinstance(b, dict) else None)
        if species:
            top_bird = species
            break

    if not top_bird:
        return

    parts = []
    for b in birds[:3]:
        cn = getattr(b, 'species_cn', None) or (b.get('species_cn') if isinstance(b, dict) else None)
        conf = getattr(b, 'confidence', None) or (b.get('confidence') if isinstance(b, dict) else None)
        if cn and conf is not None:
            parts.append(f"{cn} ({conf:.1f}%)")
    desc = "AI识别: " + ", ".join(parts) if parts else f"AI识别: {top_bird}"
    if rating is not None and rating >= 0:
        star_map = {0: "0星", 1: "1星(普通)", 2: "2星(良好)", 3: "3星(优选)"}
        desc += f" | 评分: {star_map.get(rating, f'{rating}星')}"

    xmp_rating = {-1: 0, 0: 1, 1: 2, 2: 3, 3: 5}.get(rating, 0) if rating is not None else 0

    try:
        _write_exif_text_with_tempfile(file_path, top_bird, ["XMP:Title"])
        _write_exif_text_with_tempfile(file_path, desc, ["XMP:Description", "IPTC:Caption-Abstract"])
        from tools.exiftool_manager import get_exiftool_manager
        etm = get_exiftool_manager()
        cmd = [
            etm.exiftool_path,
            "-overwrite_original_in_place",
            f"-XMP:Rating={xmp_rating}",
            file_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
    except Exception as e:
        logger.warning("Auto EXIF write failed for %s: %s", file_path, e)


@router.post("/photos/{photo_id}/exif/write-title")
async def write_exif_title(photo_id: str, req: ExifTextRequest, db=Depends(get_db)):
    """写入 EXIF/XMP 标题（UTF-8 临时文件方式）。"""
    row = db.execute(
        "SELECT original_path FROM photos WHERE id = ?",
        (photo_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Photo not found")

    try:
        meta = await run_in_threadpool(
            _write_exif_text_with_tempfile,
            row["original_path"],
            req.text,
            ["XMP:Title"],
        )
    except Exception as e:
        raise HTTPException(500, f"Write title failed: {e}")

    return {
        "photo_id": photo_id,
        "written": True,
        "title": meta.get("Title") or meta.get("XMP:Title"),
    }


@router.post("/photos/{photo_id}/exif/write-caption")
async def write_exif_caption(photo_id: str, req: ExifTextRequest, db=Depends(get_db)):
    """写入 EXIF/XMP 描述（UTF-8 临时文件方式）。"""
    row = db.execute(
        "SELECT original_path FROM photos WHERE id = ?",
        (photo_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Photo not found")

    try:
        meta = await run_in_threadpool(
            _write_exif_text_with_tempfile,
            row["original_path"],
            req.text,
            ["XMP:Description", "IPTC:Caption-Abstract"],
        )
    except Exception as e:
        raise HTTPException(500, f"Write caption failed: {e}")

    return {
        "photo_id": photo_id,
        "written": True,
        "caption": (
            meta.get("Description")
            or meta.get("Caption-Abstract")
            or meta.get("XMP:Description")
            or meta.get("IPTC:Caption-Abstract")
        ),
    }


# ── 识别 ──

@router.post("/photos/{photo_id}/recognize", response_model=RecognizeResponse)
async def recognize_photo(photo_id: str, db=Depends(get_db)):
    """单张鸟类识别（串行化推理）。"""
    photo = db.execute(
        "SELECT original_path FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    if not photo:
        raise HTTPException(404, "Photo not found")

    from main import inference_lock

    async with inference_lock:
        result = await run_in_threadpool(_run_identify, photo["original_path"])

    if not result or not result.get("success"):
        err = result.get("error", "Unknown error") if result else "Identification failed"
        raise HTTPException(500, err)

    # 存储识别结果
    birds = _store_bird_results(db, photo_id, result)
    scores = _store_scores(db, photo_id, result, image_path=photo["original_path"])

    # 自动写入 EXIF
    rating_val = scores.rating if scores else None
    await run_in_threadpool(_write_exif_bird_info, photo["original_path"], birds, rating_val)

    return RecognizeResponse(photo_id=photo_id, birds=birds, score=scores)


def _run_identify(image_path: str) -> dict:
    """在线程池中执行鸟类识别。"""
    from birdid import identify_bird

    return identify_bird(image_path, use_yolo=True, top_k=5)


def _store_bird_results(db, photo_id: str, result: dict) -> list[BirdResult]:
    """存储识别结果到 photo_birds 表。"""
    db.execute("DELETE FROM photo_birds WHERE photo_id = ?", (photo_id,))

    birds = []
    yolo_info = _normalize_yolo_info(result)
    bbox = yolo_info.get("bbox") or yolo_info.get("box")
    detection_box = json.dumps(bbox) if bbox else None

    for i, r in enumerate(result.get("results", [])):
        bird = BirdResult(
            species_cn=r.get("species_cn") or r.get("cn_name"),
            species_en=r.get("species_en") or r.get("en_name"),
            scientific_name=r.get("scientific_name"),
            confidence=r.get("confidence"),
            rank=i + 1,
            detection_box=detection_box,
        )
        db.execute(
            """INSERT INTO photo_birds
               (photo_id, species_cn, species_en, scientific_name, confidence, rank, detection_box)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (photo_id, bird.species_cn, bird.species_en, bird.scientific_name,
             bird.confidence, bird.rank, bird.detection_box),
        )
        birds.append(bird)

    db.commit()
    return birds


def _store_scores(db, photo_id: str, result: dict, image_path: str = None) -> PhotoScore | None:
    """计算完整评分并存储到 photo_scores 表。"""
    yolo_info = _normalize_yolo_info(result)
    if not yolo_info.get("detected"):
        score = PhotoScore(rating=-1)
        db.execute(
            "INSERT OR REPLACE INTO photo_scores (photo_id, rating) VALUES (?, ?)",
            (photo_id, -1),
        )
        db.commit()
        return score

    # ── 基础参数 ──
    confidence = yolo_info.get("confidence", 0.0)
    if confidence > 1.0:
        confidence = confidence / 100.0

    # ── 关键点检测 + TOPIQ 美学评分 ──
    head_sharpness = 0.0
    topiq = None
    all_keypoints_hidden = False
    best_eye_visibility = 1.0

    bbox = yolo_info.get("bbox")
    img_size = yolo_info.get("img_size")

    if image_path and bbox:
        try:
            head_sharpness, topiq, all_keypoints_hidden, best_eye_visibility = (
                _run_keypoint_and_topiq(image_path, bbox, img_size)
            )
        except Exception as e:
            logger.warning("Full rating failed for %s: %s", photo_id, e)

    # ── ISO 锐度归一化 ──
    iso_value = None
    row = db.execute(
        "SELECT iso FROM photo_metadata WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    if row and row["iso"]:
        iso_value = row["iso"]

    iso_factor = 1.0
    if iso_value and iso_value > 100:
        iso_factor = 1.0 + (iso_value - 100) / 800
    normalized_sharpness = head_sharpness * iso_factor

    # ── RatingEngine 计算 ──
    engine = _make_rating_engine()
    rating_result = engine.calculate(
        detected=True,
        confidence=confidence,
        sharpness=normalized_sharpness,
        topiq=topiq,
        all_keypoints_hidden=all_keypoints_hidden,
        best_eye_visibility=best_eye_visibility,
    )

    score = PhotoScore(
        rating=rating_result.rating,
        head_sharp=head_sharpness,
        nima_score=topiq,
    )
    db.execute(
        """INSERT OR REPLACE INTO photo_scores
           (photo_id, rating, head_sharp, nima_score)
           VALUES (?, ?, ?, ?)""",
        (photo_id, rating_result.rating, head_sharpness, topiq),
    )
    db.commit()
    return score


def _run_keypoint_and_topiq(
    image_path: str,
    bbox: list,
    img_size: list | None,
) -> tuple:
    """运行关键点检测和 TOPIQ 美学评分。"""
    import cv2
    import numpy as np

    head_sharpness = 0.0
    topiq_score = None
    all_keypoints_hidden = False
    best_eye_visibility = 1.0

    orig_img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if orig_img is None:
        return head_sharpness, topiq_score, all_keypoints_hidden, best_eye_visibility

    h_orig, w_orig = orig_img.shape[:2]

    x1, y1, x2, y2 = bbox
    if img_size and len(img_size) == 2:
        iw, ih = img_size
        if iw != w_orig or ih != h_orig:
            sx, sy = w_orig / iw, h_orig / ih
            x1, y1, x2, y2 = int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)

    bbox_w, bbox_h = x2 - x1, y2 - y1

    pad = int(max(bbox_w, bbox_h) * 0.15)
    cx1 = max(0, x1 - pad)
    cy1 = max(0, y1 - pad)
    cx2 = min(w_orig, x2 + pad)
    cy2 = min(h_orig, y2 + pad)

    bird_crop_bgr = orig_img[cy1:cy2, cx1:cx2].copy()
    crop_rgb = cv2.cvtColor(bird_crop_bgr, cv2.COLOR_BGR2RGB)

    try:
        kp_detector = model_manager.get(
            "keypoint",
            lambda: _load_keypoint_detector(),
        )
        kp_result = kp_detector.detect(
            crop_rgb,
            box=(cx1, cy1, cx2 - cx1, cy2 - cy1),
        )
        if kp_result is not None:
            head_sharpness = kp_result.head_sharpness
            best_eye_visibility = kp_result.best_eye_visibility
            all_keypoints_hidden = kp_result.all_keypoints_hidden
    except Exception as e:
        logger.warning("Keypoint detection failed: %s", e)

    if not all_keypoints_hidden and best_eye_visibility >= 0.3:
        try:
            scorer = model_manager.get(
                "topiq",
                lambda: _load_topiq_scorer(),
            )
            topiq_score = scorer.calculate_from_array(orig_img)
            if topiq_score is not None:
                topiq_score = float(max(1.0, min(10.0, topiq_score)))
        except Exception as e:
            logger.warning("TOPIQ scoring failed: %s", e)

    del orig_img

    return head_sharpness, topiq_score, all_keypoints_hidden, best_eye_visibility


def _load_keypoint_detector():
    """加载关键点检测器（供 ModelManager 回调使用）。"""
    from core.keypoint_detector import KeypointDetector
    return KeypointDetector()


def _load_topiq_scorer():
    """加载 TOPIQ 美学评分器（供 ModelManager 回调使用）。"""
    from iqa_scorer import IQAScorer
    return IQAScorer()


# ── 批量识别 ──

@router.post("/photos/batch-recognize")
async def batch_recognize(
    req: BatchRecognizeRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """批量识别（后台异步执行，返回 task_id）。"""
    placeholders = ",".join("?" for _ in req.photo_ids)
    rows = db.execute(
        f"SELECT id FROM photos WHERE id IN ({placeholders})", req.photo_ids
    ).fetchall()
    found_ids = [r["id"] for r in rows]
    if not found_ids:
        raise HTTPException(404, "No valid photo IDs found")

    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tasks (id, type, status) VALUES (?, 'recognize', 'pending')",
        (task_id,),
    )
    db.commit()

    background_tasks.add_task(_batch_recognize_task, task_id, found_ids)
    return {"id": task_id, "task_id": task_id}


def _recalculate_ratings_task(task_id: str, score_data: list[dict]):
    """后台重算评分任务（不重跑识别，仅按当前配置重新计算 rating）。"""
    from models.database import get_db_connection

    db = get_db_connection()
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        engine = _make_rating_engine()
        total = len(score_data)

        for i, item in enumerate(score_data):
            pid = item["photo_id"]
            head_sharp = item.get("head_sharp") or 0.0
            nima_score = item.get("nima_score")
            iso_value = item.get("iso")

            iso_factor = 1.0
            if iso_value and iso_value > 100:
                iso_factor = 1.0 + (iso_value - 100) / 800
            normalized_sharpness = head_sharp * iso_factor

            bird_row = db.execute(
                "SELECT confidence FROM photo_birds WHERE photo_id = ? ORDER BY rank LIMIT 1",
                (pid,),
            ).fetchone()
            confidence = 0.0
            if bird_row and bird_row["confidence"]:
                confidence = bird_row["confidence"]
                if confidence > 1.0:
                    confidence = confidence / 100.0

            rating_result = engine.calculate(
                detected=True,
                confidence=confidence,
                sharpness=normalized_sharpness,
                topiq=nima_score,
            )

            db.execute(
                "UPDATE photo_scores SET rating = ? WHERE photo_id = ?",
                (rating_result.rating, pid),
            )

            progress = int((i + 1) / total * 100)
            db.execute(
                "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (progress, task_id),
            )
            db.commit()

        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()
    except Exception as e:
        logger.error("Recalculate ratings task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()


def _batch_recognize_task(task_id: str, photo_ids: list[str]):
    """后台批量识别任务（BackgroundTasks 中运行，使用独立 DB 连接）。"""
    from models.database import get_db_connection
    from birdid import identify_bird
    from main import inference_thread_lock

    db = get_db_connection()
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        total = len(photo_ids)
        for i, pid in enumerate(photo_ids):
            try:
                row = db.execute(
                    "SELECT original_path FROM photos WHERE id = ?", (pid,)
                ).fetchone()
                if not row:
                    continue

                with inference_thread_lock:
                    result = identify_bird(row["original_path"], use_yolo=True, top_k=5)

                if result and result.get("success"):
                    birds = _store_bird_results(db, pid, result)
                    scores = _store_scores(db, pid, result, image_path=row["original_path"])
                    # 自动写入 EXIF
                    rating_val = scores.rating if scores else None
                    try:
                        _write_exif_bird_info(row["original_path"], birds, rating_val)
                    except Exception as e:
                        logger.warning("EXIF write failed for %s: %s", pid, e)
            except Exception as e:
                logger.warning("Recognize failed for photo %s: %s", pid, e)

            progress = int((i + 1) / total * 100)
            if i % 3 == 0:
                db.execute(
                    "UPDATE tasks SET progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (progress, task_id),
                )
                db.commit()

        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()
    except Exception as e:
        logger.error("Batch recognize task %s failed: %s", task_id, e)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        db.close()


@router.delete("/photos/{photo_id}", dependencies=[Depends(require_admin)])
async def delete_photo(photo_id: str, db=Depends(get_db)):
    """删除单张照片及其磁盘文件，级联删除关联数据。"""
    photo = db.execute("SELECT id, original_path FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not photo:
        raise HTTPException(404, "Photo not found")

    db.execute("DELETE FROM photo_metadata WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photo_scores WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photo_birds WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photo_tags WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM burst_group_photos WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM duplicate_groups WHERE photo_id = ?", (photo_id,))
    db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    db.commit()

    _delete_photo_files(photo_id, photo["original_path"])

    return {"deleted": True}
