"""
RAW 批量处理 API

端点:
- GET  /batch-process/options      预设列表
- POST /batch-process/start        启动批处理
- GET  /batch-process/{task_id}/results  获取结果
- POST /batch-process/preview-crop       裁切预览
- POST /batch-process/preview-watermark  水印预览
"""

import json
import logging
import os
import uuid
from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from models.database import get_db, get_db_connection
from models.batch_schemas import (
    BatchProcessConfig,
    BatchProcessStartResponse,
    BatchProcessResultsResponse,
    BatchProcessResultItem,
)
from services.crop_service import (
    get_crop_presets, smart_crop, _parse_detection_box,
)
from services.watermark_service import (
    get_watermark_presets, apply_watermark_layers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-process", tags=["batch-process"])


@router.get("/options")
async def get_options():
    """Return available presets and parameter ranges."""
    return {
        "crop_presets": get_crop_presets(),
        "watermark_presets": get_watermark_presets(),
        "denoise_algorithms": ["DeepPRIME_3", "DeepPRIME_XD3"],
        "auto_tone_tools": ["lightroom", "darktable"],
        "output_formats": ["jpeg", "tiff", "png"],
        "aspect_ratios": ["16:9", "4:3", "3:2", "1:1", "21:9", "9:16", "original"],
        "compositions": ["center", "rule-of-thirds", "tight", "environmental"],
    }


@router.post("/start", response_model=BatchProcessStartResponse)
async def start_batch_process(
    config: BatchProcessConfig,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """Start a batch processing task. Global mutex: only one at a time."""
    task_id = str(uuid.uuid4())
    config_json = config.model_dump_json()

    # Atomic insert with mutex check
    result = db.execute(
        """
        INSERT INTO tasks (id, type, status, config_json, created_at)
        SELECT :id, 'batch_process', 'running', :config, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM tasks WHERE type = 'batch_process' AND status = 'running'
        )
        """,
        {"id": task_id, "config": config_json},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(409, "已有批处理任务在执行中")

    # Count filtered photos for estimate
    total = db.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    filtered = db.execute(
        """
        SELECT COUNT(*) FROM photos p
        JOIN photo_scores ps ON p.id = ps.photo_id
        WHERE ps.rating >= ?
        """,
        (config.min_rating,),
    ).fetchone()[0]

    # Estimate time (rough)
    est_minutes = int(filtered * 0.4)  # ~24s per photo total

    # Launch background task
    from services.batch_process_service import run_batch_process
    background_tasks.add_task(
        run_batch_process, task_id, config.model_dump(),
    )

    return BatchProcessStartResponse(
        task_id=task_id,
        total_photos=total,
        filtered_photos=filtered,
        estimated_time_minutes=est_minutes,
    )


@router.get("/{task_id}/results", response_model=BatchProcessResultsResponse)
async def get_results(task_id: str, db=Depends(get_db)):
    """Get batch processing results for a task."""
    task = db.execute(
        "SELECT id FROM tasks WHERE id = ? AND type = 'batch_process'",
        (task_id,),
    ).fetchone()
    if not task:
        raise HTTPException(404, "Task not found")

    rows = db.execute(
        """
        SELECT bpi.photo_id, p.filename, bpi.phase,
               bpi.final_output, bpi.error_msg
        FROM batch_process_items bpi
        JOIN photos p ON bpi.photo_id = p.id
        WHERE bpi.task_id = ?
        ORDER BY p.filename
        """,
        (task_id,),
    ).fetchall()

    items = []
    completed = 0
    failed = 0
    for row in rows:
        items.append(BatchProcessResultItem(
            photo_id=row["photo_id"],
            filename=row["filename"],
            phase=row["phase"],
            final_output=row["final_output"],
            error_msg=row["error_msg"],
        ))
        if row["phase"] == "done":
            completed += 1
        elif row["phase"] == "error":
            failed += 1

    return BatchProcessResultsResponse(
        task_id=task_id,
        total=len(items),
        completed=completed,
        failed=failed,
        items=items,
    )


@router.get("/{task_id}/photo/{photo_id}")
async def get_processed_photo(
    task_id: str,
    photo_id: str,
    thumb: bool = False,
    db=Depends(get_db),
):
    """Serve a processed photo file over HTTP.

    Args:
        thumb: If true, returns a 400px thumbnail instead of full-size.
    """
    row = db.execute(
        "SELECT final_output FROM batch_process_items "
        "WHERE task_id = ? AND photo_id = ? AND phase = 'done'",
        (task_id, photo_id),
    ).fetchone()
    if not row or not row["final_output"]:
        raise HTTPException(404, "Processed photo not found")

    file_path = row["final_output"]
    if not os.path.exists(file_path):
        raise HTTPException(404, "Photo file missing from disk")

    if thumb:
        from PIL import Image as PILImage
        img = PILImage.open(file_path)
        img.thumbnail((400, 400))
        buf = BytesIO()
        if img.mode == "RGBA":
            bg = PILImage.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        img.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        img.close()
        return StreamingResponse(buf, media_type="image/jpeg")

    # Serve full file
    ext = os.path.splitext(file_path)[1].lower()
    media_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.tiff': 'image/tiff', '.tif': 'image/tiff',
    }
    media_type = media_types.get(ext, 'application/octet-stream')

    from fastapi.responses import FileResponse
    return FileResponse(file_path, media_type=media_type)


@router.post("/preview-crop")
async def preview_crop(
    photo_id: str,
    crop_config: dict,
    db=Depends(get_db),
):
    """Preview crop for a single photo. Returns JPEG thumbnail."""
    from services.thumbnail_generator import _open_image

    photo = db.execute(
        "SELECT original_path FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    if not photo:
        raise HTTPException(404, "Photo not found")

    bird = db.execute(
        "SELECT detection_box FROM photo_birds "
        "WHERE photo_id = ? AND rank = 1",
        (photo_id,),
    ).fetchone()

    detection_box = _parse_detection_box(
        bird["detection_box"] if bird else None
    )

    try:
        img = _open_image(photo["original_path"])
    except Exception:
        raise HTTPException(500, "Cannot open image")

    if detection_box:
        img = smart_crop(
            img, detection_box,
            aspect_ratio=crop_config.get("aspect_ratio", "16:9"),
            output_size=crop_config.get("output_size"),
            composition=crop_config.get("composition", "center"),
            bird_padding=crop_config.get("bird_padding", 1.3),
        )

    # Resize for preview
    img.thumbnail((800, 800))
    if img.mode == "RGBA":
        from PIL import Image
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    img.close()

    return StreamingResponse(buf, media_type="image/jpeg")


@router.post("/preview-watermark")
async def preview_watermark(
    photo_id: str,
    watermark_layers: list[dict],
    db=Depends(get_db),
):
    """Preview watermark for a single photo. Returns JPEG thumbnail."""
    from services.thumbnail_generator import _open_image

    photo = db.execute(
        "SELECT original_path FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    if not photo:
        raise HTTPException(404, "Photo not found")

    # Get species + EXIF info
    bird = db.execute(
        "SELECT species_cn, species_en FROM photo_birds "
        "WHERE photo_id = ? AND rank = 1",
        (photo_id,),
    ).fetchone()
    species_cn = bird["species_cn"] if bird else ""
    species_en = bird["species_en"] if bird else ""

    exif_row = db.execute(
        "SELECT camera_model, lens_model, focal_length, "
        "aperture, shutter_speed, iso "
        "FROM photo_metadata WHERE photo_id = ?",
        (photo_id,),
    ).fetchone()
    exif_data = dict(exif_row) if exif_row else {}

    try:
        img = _open_image(photo["original_path"])
    except Exception:
        raise HTTPException(500, "Cannot open image")

    # Resize down for preview first
    img.thumbnail((800, 800))

    img = apply_watermark_layers(
        img, watermark_layers,
        species_cn=species_cn,
        species_en=species_en,
        exif_data=exif_data,
    )

    if img.mode == "RGBA":
        from PIL import Image
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    img.close()

    return StreamingResponse(buf, media_type="image/jpeg")
