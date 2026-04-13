"""
分块上传管理 API

- 初始化上传会话
- 上传单块
- 查询已上传块
- 合并分块 + SHA256 校验
"""

import os
import shutil
import uuid
import json
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from starlette.concurrency import run_in_threadpool
from models.database import get_db
from app_config_pkg import config as app_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

_MAX_SINGLE_FILE = 10 * 1024 * 1024 * 1024  # 10GB
_DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024       # 10MB


@router.post("/upload/init")
async def init_upload(
    filename: str,
    file_size: int,
    file_type: str = "photo",
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    db=Depends(get_db),
):
    """初始化分块上传会话，返回 upload_id。"""
    if file_size > _MAX_SINGLE_FILE:
        raise HTTPException(413, f"File too large (max {_MAX_SINGLE_FILE // (1024**3)}GB)")
    if file_type not in ("photo", "video"):
        raise HTTPException(400, "file_type must be 'photo' or 'video'")

    upload_id = str(uuid.uuid4())
    chunk_count = (file_size + chunk_size - 1) // chunk_size

    # 创建块目录
    app_config.chunks_dir(upload_id)

    db.execute(
        """INSERT INTO upload_sessions
           (id, filename, file_size, chunk_count, chunk_size, status, uploaded_chunks, file_type)
           VALUES (?, ?, ?, ?, ?, 'uploading', '[]', ?)""",
        (upload_id, filename, file_size, chunk_count, chunk_size, file_type),
    )
    db.commit()

    return {
        "upload_id": upload_id,
        "chunk_count": chunk_count,
        "total_chunks": chunk_count,
        "chunk_size": chunk_size,
    }


@router.post("/upload/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    index: int = Query(..., ge=0),
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    """上传单个分块。"""
    session = db.execute(
        "SELECT * FROM upload_sessions WHERE id = ?", (upload_id,)
    ).fetchone()
    if not session:
        raise HTTPException(404, "Upload session not found")
    if session["status"] != "uploading":
        raise HTTPException(400, f"Upload session is {session['status']}")
    if index >= session["chunk_count"]:
        raise HTTPException(400, f"Chunk index {index} >= total {session['chunk_count']}")

    # 流式保存块（避免一次性读入整个 chunk 占用内存）
    chunk_path = os.path.join(app_config.chunks_dir(upload_id), f"{index:06d}")
    with open(chunk_path, 'wb') as f:
        shutil.copyfileobj(file.file, f, length=1024 * 1024)

    # 更新已接收块列表
    uploaded = json.loads(session["uploaded_chunks"])
    if index not in uploaded:
        uploaded.append(index)
        uploaded.sort()
    db.execute(
        "UPDATE upload_sessions SET uploaded_chunks = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(uploaded), upload_id),
    )
    db.commit()

    return {"index": index, "received": len(uploaded), "total": session["chunk_count"]}


@router.get("/upload/{upload_id}/status")
async def upload_status(upload_id: str, db=Depends(get_db)):
    """查询已上传块列表（断点续传）。"""
    session = db.execute(
        "SELECT * FROM upload_sessions WHERE id = ?", (upload_id,)
    ).fetchone()
    if not session:
        raise HTTPException(404, "Upload session not found")

    uploaded = json.loads(session["uploaded_chunks"])
    return {
        "upload_id": upload_id,
        "filename": session["filename"],
        "status": session["status"],
        "uploaded_chunks": uploaded,
        "total_chunks": session["chunk_count"],
        "received": len(uploaded),
    }


@router.post("/upload/{upload_id}/complete")
async def complete_upload(upload_id: str, db=Depends(get_db)):
    """合并分块 + SHA256 校验。"""
    session = db.execute(
        "SELECT * FROM upload_sessions WHERE id = ?", (upload_id,)
    ).fetchone()
    if not session:
        raise HTTPException(404, "Upload session not found")
    if session["status"] != "uploading":
        raise HTTPException(400, f"Upload session is {session['status']}")

    uploaded = json.loads(session["uploaded_chunks"])
    expected = list(range(session["chunk_count"]))
    missing = [i for i in expected if i not in uploaded]
    if missing:
        raise HTTPException(400, f"Missing chunks: {missing}")

    # 合并文件
    file_type = session["file_type"]
    if file_type == "video":
        dest_dir = app_config.videos_original_dir()
    else:
        dest_dir = app_config.photos_upload_dir()

    ext = os.path.splitext(session["filename"])[1].lower()
    dest_path = os.path.join(dest_dir, f"{upload_id}{ext}")

    h = hashlib.sha256()
    try:
        with open(dest_path, 'wb') as out:
            for i in expected:
                chunk_path = os.path.join(app_config.chunks_dir(upload_id), f"{i:06d}")
                with open(chunk_path, 'rb') as chunk_file:
                    while True:
                        data = chunk_file.read(8192)
                        if not data:
                            break
                        h.update(data)
                        out.write(data)
    except Exception as e:
        # 合并失败回滚
        if os.path.exists(dest_path):
            os.unlink(dest_path)
        db.execute(
            "UPDATE upload_sessions SET status = 'failed', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), upload_id),
        )
        db.commit()
        raise HTTPException(500, f"Merge failed: {e}")

    file_hash = h.hexdigest()

    # 更新会话
    db.execute(
        """UPDATE upload_sessions
           SET status = 'completed', file_hash = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (file_hash, upload_id),
    )
    db.commit()

    # 清理块目录
    chunk_dir = app_config.chunks_dir(upload_id)
    shutil.rmtree(chunk_dir, ignore_errors=True)

    # 注册到 photos 或 videos 表
    file_size = os.path.getsize(dest_path)
    if file_size == 0:
        os.unlink(dest_path)
        raise HTTPException(400, "Merged file is empty (0 bytes)")
    result = {"upload_id": upload_id, "file_hash": file_hash, "file_size": file_size}

    if file_type == "video":
        from services.video_processor import get_video_info, generate_thumbnail as gen_video_thumb
        info = await run_in_threadpool(get_video_info, dest_path)
        db.execute(
            """INSERT INTO videos (id, original_path, filename, duration, fps, frame_count, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (upload_id, dest_path, session["filename"],
             info.get("duration") if info else None,
             info.get("fps") if info else None,
             info.get("frame_count") if info else None),
        )
        db.commit()
        # 生成视频缩略图
        thumb_path = os.path.join(app_config.videos_thumbnails_dir(), f"{upload_id}.jpg")
        await run_in_threadpool(gen_video_thumb, dest_path, thumb_path)
        result["video_id"] = upload_id
    else:
        from services.thumbnail_generator import generate_thumbnail, get_image_dimensions
        dims = get_image_dimensions(dest_path)
        width, height = dims if dims else (None, None)
        db.execute(
            """INSERT INTO photos (id, original_path, filename, file_hash, width, height, file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (upload_id, dest_path, session["filename"], file_hash, width, height, file_size),
        )
        db.commit()
        await run_in_threadpool(generate_thumbnail, dest_path, upload_id, "sm")
        # EXIF 提取
        try:
            from api.photos import _extract_and_store_exif
            await _extract_and_store_exif(upload_id, dest_path, db)
        except Exception as e:
            logger.warning("EXIF extraction failed for %s: %s", upload_id, e)
        result["photo_id"] = upload_id

    return result
