"""
临时鸟类识别 API — 接收上传图片，返回识别结果，不写入数据库。
"""

import os
import tempfile
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from starlette.concurrency import run_in_threadpool

router = APIRouter(tags=["identify"])

logger = logging.getLogger("bird-gallery")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heif", ".heic", ".webp",
                      ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _run_identify(image_path: str) -> dict:
    from birdid import identify_bird
    return identify_bird(image_path, use_yolo=True, top_k=5)


@router.post("/identify")
async def identify_image(file: UploadFile = File(...)):
    """上传图片进行鸟类识别（不写入数据库）。"""
    if not file.filename:
        raise HTTPException(400, "未提供文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式：{ext}")

    # 读取文件并检查大小
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件过大，最大支持 50MB")
    if len(data) == 0:
        raise HTTPException(400, "文件为空")

    # 写入临时文件
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        tmp.write(data)
        tmp.close()

        from main import inference_lock
        async with inference_lock:
            result = await run_in_threadpool(_run_identify, tmp.name)

        if not result or not result.get("success"):
            err = result.get("error", "识别失败") if result else "识别失败"
            raise HTTPException(500, err)

        # 构建返回结果
        birds = []
        yolo_info = result.get("yolo_info") or {}
        bbox = yolo_info.get("bbox") or yolo_info.get("box")

        for i, r in enumerate(result.get("results", [])):
            birds.append({
                "species_cn": r.get("species_cn") or r.get("cn_name"),
                "species_en": r.get("species_en") or r.get("en_name"),
                "scientific_name": r.get("scientific_name"),
                "confidence": r.get("confidence"),
                "rank": i + 1,
            })

        return {
            "success": True,
            "birds": birds,
            "detection_box": bbox,
        }
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
