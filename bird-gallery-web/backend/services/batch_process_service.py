"""
RAW 照片批量处理主流程编排

6 阶段管线:
  Phase 1: 鸟种识别 + 评分 (复用现有管线)
  Phase 2: 筛选 >= min_rating
  Phase 3: DxO PureRAW 降噪 → DNG
  Phase 4: Lightroom / darktable 自动调色 → TIFF
  Phase 5: 智能裁切 + 水印 → JPG
  Phase 6: 注册到 DB
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def _check_cancelled(db, task_id: str) -> bool:
    """Check if task has been cancelled."""
    row = db.execute(
        "SELECT status FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    return row and row["status"] == "cancelled"


def _update_progress(db, task_id: str, progress: int, result_data: dict):
    """Update task progress and result_json."""
    db.execute(
        "UPDATE tasks SET progress = ?, result_json = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (progress, json.dumps(result_data, ensure_ascii=False), task_id),
    )
    db.commit()


_RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2'}


def _open_image_for_crop(file_path: str) -> Image.Image:
    """Open an image for cropping. Supports TIFF, JPEG, DNG, and RAW.

    For RAW files (ARW/CR3/NEF etc.), extraction chain:
      1. rawpy extract_thumb (embedded full-res JPEG)
      2. rawpy postprocess (full RAW decode)
      3. exiftool -b -JpgFromRaw (fallback for newer cameras like Sony A7M5)
    """
    from io import BytesIO
    ext = Path(file_path).suffix.lower()

    if ext in ('.tiff', '.tif', '.jpg', '.jpeg', '.png'):
        return Image.open(file_path)

    if ext not in _RAW_EXTENSIONS:
        return Image.open(file_path)

    # RAW file — try multiple extraction methods
    # Method 1: rawpy
    try:
        import rawpy
        with rawpy.imread(file_path) as raw:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    return Image.open(BytesIO(thumb.data))
                elif thumb.format == rawpy.ThumbFormat.BITMAP:
                    return Image.fromarray(thumb.data)
            except Exception:
                pass
            rgb = raw.postprocess(
                use_camera_wb=True, output_bps=8, no_auto_bright=False,
            )
            return Image.fromarray(rgb)
    except Exception as e:
        logger.debug("rawpy failed for %s: %s, trying exiftool", file_path, e)

    # Method 2: exiftool extract embedded JPEG (works for newer cameras)
    import subprocess
    for tag in ('-JpgFromRaw', '-PreviewImage'):
        try:
            result = subprocess.run(
                ['exiftool', '-b', tag, file_path],
                capture_output=True, timeout=30,
            )
            if result.stdout and len(result.stdout) > 1000:
                return Image.open(BytesIO(result.stdout))
        except Exception:
            pass

    raise ValueError(f"Cannot open RAW file: {file_path}")


def run_batch_process(task_id: str, config_dict: dict):
    """Main batch processing entry point. Runs in background thread.

    Args:
        task_id: Task UUID
        config_dict: BatchProcessConfig as dict
    """
    from models.database import get_db_connection
    from main import inference_thread_lock
    from app_config_pkg import config as app_config
    from services.crop_service import (
        smart_crop, get_crop_presets, CROP_PRESETS,
        _parse_detection_box,
    )
    from services.watermark_service import (
        apply_watermark_layers, get_watermark_presets, WATERMARK_PRESETS,
    )
    from services import pureraw_service

    db = get_db_connection()

    # Parse config
    min_rating = config_dict.get("min_rating", 2)
    denoise_enabled = config_dict.get("denoise_enabled", True)
    denoise_algorithm = config_dict.get("denoise_algorithm", "DeepPRIME_XD3")
    denoise_luminance = config_dict.get("denoise_luminance", 40)
    denoise_chrominance = config_dict.get("denoise_chrominance", 50)
    auto_tone_enabled = config_dict.get("auto_tone_enabled", True)
    tone_mode = config_dict.get("tone_mode", "reference_version")
    reference_photo_id = config_dict.get("reference_photo_id")
    reference_version_id = config_dict.get("reference_version_id")
    tone_params = config_dict.get("tone_params")
    tone_reference_label = config_dict.get("tone_reference_label")
    auto_tone_tool = config_dict.get("auto_tone_tool", "lightroom")
    crop_preset = config_dict.get("crop_preset", "4k_wallpaper")
    crop_config = config_dict.get("crop_config")
    watermark_preset = config_dict.get("watermark_preset", "simple_copyright")
    watermark_layers_cfg = config_dict.get("watermark_layers")
    output_format = config_dict.get("output_format", "jpeg")
    output_quality = config_dict.get("output_quality", 95)
    output_dir = config_dict.get("output_dir", "")

    reference_tone_params = None
    if auto_tone_enabled and tone_mode == 'reference_version':
        from services.photo_edit_service import normalize_params

        if isinstance(tone_params, dict):
            reference_tone_params = normalize_params(tone_params)

    # Resolve crop settings
    if crop_preset != "custom" and crop_preset in CROP_PRESETS:
        preset = CROP_PRESETS[crop_preset]
        crop_aspect = preset["aspect_ratio"]
        crop_output_size = preset["output_size"]
        crop_composition = preset["composition"]
        crop_bird_padding = preset["bird_padding"]
    elif crop_config:
        crop_aspect = crop_config.get("aspect_ratio", "16:9")
        crop_output_size = crop_config.get("output_size", (3840, 2160))
        if isinstance(crop_output_size, list):
            crop_output_size = tuple(crop_output_size)
        crop_composition = crop_config.get("composition", "center")
        crop_bird_padding = crop_config.get("bird_padding", 1.3)
    else:
        crop_aspect = "16:9"
        crop_output_size = (3840, 2160)
        crop_composition = "center"
        crop_bird_padding = 1.3

    # Resolve watermark settings
    if watermark_preset != "custom" and watermark_preset in WATERMARK_PRESETS:
        wm_layers = WATERMARK_PRESETS[watermark_preset]["layers"]
    elif watermark_layers_cfg:
        wm_layers = watermark_layers_cfg
    else:
        wm_layers = []

    # Setup output directories
    if not output_dir:
        output_dir = app_config.exports_dir(task_id)
    os.makedirs(output_dir, exist_ok=True)
    denoise_dir = os.path.join(output_dir, "denoise")
    toned_dir = os.path.join(output_dir, "toned")
    final_dir = os.path.join(output_dir, "final")
    for d in [denoise_dir, toned_dir, final_dir]:
        os.makedirs(d, exist_ok=True)

    # Save config snapshot
    with open(os.path.join(output_dir, "config.json"), 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)

    pureraw_backup = None

    try:
        # ── Phase 1 & 2: Filter photos by rating ──
        _update_progress(db, task_id, 0, {
            "current_phase": "filter",
            "phase_progress": {"filter": 0, "denoise": 0, "tone": 0, "crop": 0},
        })

        # Get photos that meet the rating threshold
        rows = db.execute(
            """
            SELECT p.id, p.original_path, p.filename,
                   ps.rating,
                   pb.detection_box, pb.species_cn, pb.species_en
            FROM photos p
            LEFT JOIN photo_scores ps ON p.id = ps.photo_id
            LEFT JOIN photo_birds pb ON p.id = pb.photo_id AND pb.rank = 1
            WHERE ps.rating >= ?
            ORDER BY p.filename
            """,
            (min_rating,),
        ).fetchall()

        filtered_photos = []
        for row in rows:
            filtered_photos.append({
                "photo_id": row["id"],
                "original_path": row["original_path"],
                "filename": row["filename"],
                "rating": row["rating"],
                "detection_box": row["detection_box"],
                "species_cn": row["species_cn"],
                "species_en": row["species_en"],
            })

        total = len(filtered_photos)
        if total == 0:
            _update_progress(db, task_id, 100, {
                "current_phase": "done",
                "message": "No photos passed rating filter",
                "total": 0, "completed": 0,
            })
            db.execute(
                "UPDATE tasks SET status = 'done', progress = 100, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id,),
            )
            db.commit()
            return

        # Insert batch_process_items
        for photo in filtered_photos:
            db.execute(
                "INSERT OR IGNORE INTO batch_process_items "
                "(task_id, photo_id, phase) VALUES (?, ?, 'pending')",
                (task_id, photo["photo_id"]),
            )
        db.commit()

        logger.info("Batch process %s: %d photos passed filter (min_rating=%d)",
                     task_id, total, min_rating)

        _update_progress(db, task_id, 5, {
            "current_phase": "filter",
            "total": total,
            "phase_progress": {"filter": 100, "denoise": 0, "tone": 0, "crop": 0},
        })

        if _check_cancelled(db, task_id):
            return

        # ── Phase 3: PureRAW Denoise ──
        if denoise_enabled:
            _update_progress(db, task_id, 10, {
                "current_phase": "denoise",
                "total": total,
                "phase_progress": {"filter": 100, "denoise": 0, "tone": 0, "crop": 0},
            })

            pureraw_service.recover_orphaned_backup()
            pureraw_backup = pureraw_service.setup_preset(
                task_id, denoise_dir, denoise_algorithm,
                denoise_luminance, denoise_chrominance,
            )

            # Collect RAW files for PureRAW
            raw_files = [p["original_path"] for p in filtered_photos]
            pureraw_service.send_files_to_pureraw(raw_files)
            pureraw_service.trigger_processing_applescript()

            # Wait for output
            dng_files = pureraw_service.wait_for_output(
                denoise_dir, raw_files, denoise_algorithm,
                timeout=7200,
                cancel_check=lambda: _check_cancelled(db, task_id),
            )

            # Map input → DNG output
            dng_map = {}
            for dng_path in dng_files:
                stem = Path(dng_path).stem
                # DNG name: "{original_stem}-DxO_DeepPRIME XD3"
                for photo in filtered_photos:
                    orig_stem = Path(photo["filename"]).stem
                    if stem.startswith(orig_stem):
                        dng_map[photo["photo_id"]] = dng_path
                        break

            # Update batch items
            for photo in filtered_photos:
                pid = photo["photo_id"]
                if pid in dng_map:
                    db.execute(
                        "UPDATE batch_process_items SET phase = 'denoise', "
                        "denoise_output = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE task_id = ? AND photo_id = ?",
                        (dng_map[pid], task_id, pid),
                    )
            db.commit()

            # Restore PureRAW preset
            pureraw_service.restore_preset(pureraw_backup)
            pureraw_backup = None

            _update_progress(db, task_id, 40, {
                "current_phase": "denoise",
                "total": total,
                "phase_progress": {"filter": 100, "denoise": 100, "tone": 0, "crop": 0},
            })

        if _check_cancelled(db, task_id):
            return

        # ── Phase 4: Auto Tone (placeholder — requires manual LR trigger) ──
        if auto_tone_enabled:
            _update_progress(db, task_id, 45, {
                "current_phase": "tone",
                "total": total,
                "message": (
                    f"Applying saved edit template: {tone_reference_label}"
                    if tone_mode == 'reference_version'
                    else "Waiting for Lightroom auto-tone processing..."
                ),
                "phase_progress": {"filter": 100, "denoise": 100, "tone": 0, "crop": 0},
            })

            if tone_mode == 'reference_version':
                if reference_tone_params is None:
                    raise ValueError(
                        'reference tone params missing '
                        f'(photo_id={reference_photo_id}, version_id={reference_version_id})'
                    )

                from services.raw_develop_service import render_export_file

                for i, photo in enumerate(filtered_photos):
                    if _check_cancelled(db, task_id):
                        return

                    pid = photo["photo_id"]
                    bpi = db.execute(
                        "SELECT denoise_output FROM batch_process_items "
                        "WHERE task_id = ? AND photo_id = ?",
                        (task_id, pid),
                    ).fetchone()
                    input_file = (
                        bpi["denoise_output"]
                        if bpi and bpi["denoise_output"]
                        else photo["original_path"]
                    )
                    output_file = os.path.join(
                        toned_dir, Path(photo["filename"]).stem + ".tiff"
                    )

                    render_export_file(
                        input_file,
                        reference_tone_params,
                        output_file,
                        'tiff',
                        quality=95,
                    )
                    db.execute(
                        "UPDATE batch_process_items SET phase = 'tone', "
                        "tone_output = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE task_id = ? AND photo_id = ?",
                        (output_file, task_id, pid),
                    )
                    db.commit()

                    progress = 45 + int((i + 1) / total * 15)
                    _update_progress(db, task_id, progress, {
                        "current_phase": "tone",
                        "current_file": photo["filename"],
                        "total": total,
                        "message": tone_reference_label or 'Applying saved edit template',
                        "phase_progress": {
                            "filter": 100, "denoise": 100,
                            "tone": int((i + 1) / total * 100), "crop": 0,
                        },
                    })
            elif auto_tone_tool == "darktable":
                # darktable-cli fallback
                for i, photo in enumerate(filtered_photos):
                    if _check_cancelled(db, task_id):
                        return
                    pid = photo["photo_id"]
                    # Input: DNG (if denoised) or original RAW
                    bpi = db.execute(
                        "SELECT denoise_output FROM batch_process_items "
                        "WHERE task_id = ? AND photo_id = ?",
                        (task_id, pid),
                    ).fetchone()
                    input_file = (bpi["denoise_output"] if bpi and bpi["denoise_output"]
                                  else photo["original_path"])
                    output_file = os.path.join(
                        toned_dir, Path(photo["filename"]).stem + ".tiff"
                    )
                    try:
                        import subprocess
                        subprocess.run(
                            ["darktable-cli", input_file, output_file,
                             "--core", "--conf",
                             "plugins/imageio/format/tiff/bps=16"],
                            capture_output=True, text=True, timeout=120,
                        )
                        if os.path.exists(output_file):
                            db.execute(
                                "UPDATE batch_process_items SET phase = 'tone', "
                                "tone_output = ?, updated_at = CURRENT_TIMESTAMP "
                                "WHERE task_id = ? AND photo_id = ?",
                                (output_file, task_id, pid),
                            )
                            db.commit()
                    except Exception as e:
                        logger.warning("darktable-cli failed for %s: %s",
                                       photo["filename"], e)

                    progress = 45 + int((i + 1) / total * 15)
                    _update_progress(db, task_id, progress, {
                        "current_phase": "tone",
                        "current_file": photo["filename"],
                        "total": total,
                        "phase_progress": {
                            "filter": 100, "denoise": 100,
                            "tone": int((i + 1) / total * 100), "crop": 0,
                        },
                    })
            else:
                # Lightroom — semi-manual: notify user, wait for output in toned_dir
                logger.info(
                    "Lightroom auto-tone: please import DNG files from %s "
                    "into Lightroom and run SuperPicky Auto Tone + Export plugin. "
                    "Export TIFF to: %s",
                    denoise_dir, toned_dir,
                )
                # Poll for TIFF files in toned_dir
                expected_count = total
                timeout = 7200  # 2 hours
                start = time.time()
                while time.time() - start < timeout:
                    if _check_cancelled(db, task_id):
                        return
                    tiff_files = list(Path(toned_dir).glob("*.tif*"))
                    if len(tiff_files) >= expected_count:
                        break
                    progress_pct = int(len(tiff_files) / expected_count * 100)
                    _update_progress(db, task_id, 45 + int(progress_pct * 0.15), {
                        "current_phase": "tone",
                        "total": total,
                        "message": f"Waiting for LR output: {len(tiff_files)}/{expected_count}",
                        "phase_progress": {
                            "filter": 100, "denoise": 100,
                            "tone": progress_pct, "crop": 0,
                        },
                    })
                    time.sleep(5)

                # Map toned files
                for tiff_path in Path(toned_dir).glob("*.tif*"):
                    stem = tiff_path.stem
                    for photo in filtered_photos:
                        orig_stem = Path(photo["filename"]).stem
                        if stem.startswith(orig_stem):
                            db.execute(
                                "UPDATE batch_process_items SET phase = 'tone', "
                                "tone_output = ?, updated_at = CURRENT_TIMESTAMP "
                                "WHERE task_id = ? AND photo_id = ?",
                                (str(tiff_path), task_id, photo["photo_id"]),
                            )
                            break
                db.commit()

            _update_progress(db, task_id, 60, {
                "current_phase": "tone",
                "total": total,
                "phase_progress": {"filter": 100, "denoise": 100, "tone": 100, "crop": 0},
            })

        if _check_cancelled(db, task_id):
            return

        # ── Phase 5 & 6: Smart Crop + Watermark + Register ──
        _update_progress(db, task_id, 65, {
            "current_phase": "crop",
            "total": total,
            "phase_progress": {"filter": 100, "denoise": 100, "tone": 100, "crop": 0},
        })

        completed = 0
        failed = 0

        for i, photo in enumerate(filtered_photos):
            if _check_cancelled(db, task_id):
                return

            pid = photo["photo_id"]
            try:
                # Determine input file: toned > denoised > original
                bpi = db.execute(
                    "SELECT tone_output, denoise_output FROM batch_process_items "
                    "WHERE task_id = ? AND photo_id = ?",
                    (task_id, pid),
                ).fetchone()

                input_file = None
                if bpi:
                    if bpi["tone_output"] and os.path.exists(bpi["tone_output"]):
                        input_file = bpi["tone_output"]
                    elif bpi["denoise_output"] and os.path.exists(bpi["denoise_output"]):
                        input_file = bpi["denoise_output"]
                if not input_file:
                    input_file = photo["original_path"]

                # Open image
                img = _open_image_for_crop(input_file)

                # Smart crop
                detection_box = _parse_detection_box(photo["detection_box"])
                if detection_box:
                    img = smart_crop(
                        img, detection_box,
                        aspect_ratio=crop_aspect,
                        output_size=crop_output_size,
                        composition=crop_composition,
                        bird_padding=crop_bird_padding,
                    )
                elif crop_output_size:
                    # No bird detected — simple center crop / resize
                    if img.width > crop_output_size[0] or img.height > crop_output_size[1]:
                        img.thumbnail(crop_output_size, Image.LANCZOS)

                # Watermark
                if wm_layers:
                    # Get EXIF for info-bar
                    exif_row = db.execute(
                        "SELECT camera_model, lens_model, focal_length, "
                        "aperture, shutter_speed, iso "
                        "FROM photo_metadata WHERE photo_id = ?",
                        (pid,),
                    ).fetchone()
                    exif_data = dict(exif_row) if exif_row else {}

                    img = apply_watermark_layers(
                        img,
                        wm_layers,
                        species_cn=photo.get("species_cn", ""),
                        species_en=photo.get("species_en", ""),
                        exif_data=exif_data,
                    )

                # Save final output
                stem = Path(photo["filename"]).stem
                if output_format == "jpeg":
                    ext = ".jpg"
                elif output_format == "tiff":
                    ext = ".tiff"
                else:
                    ext = ".png"
                final_name = f"{stem}_{crop_preset}{ext}"
                final_path = os.path.join(final_dir, final_name)

                # Convert RGBA → RGB for JPEG
                if output_format == "jpeg" and img.mode == "RGBA":
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg

                save_kwargs = {}
                if output_format == "jpeg":
                    save_kwargs = {"quality": output_quality, "subsampling": 0}
                elif output_format == "tiff":
                    save_kwargs = {"compression": "tiff_lzw"}

                img.save(final_path, **save_kwargs)
                img.close()

                # Copy EXIF from original RAW to final output
                try:
                    from tools.exiftool_manager import get_exiftool_manager
                    etm = get_exiftool_manager()
                    etm.copy_metadata(photo["original_path"], final_path)
                except Exception as e:
                    logger.warning("EXIF copy failed for %s: %s", final_name, e)

                # Get final file info
                file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
                try:
                    with Image.open(final_path) as fimg:
                        final_w, final_h = fimg.size
                except Exception:
                    final_w, final_h = 0, 0

                # Update batch_process_items
                db.execute(
                    "UPDATE batch_process_items SET phase = 'done', "
                    "final_output = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE task_id = ? AND photo_id = ?",
                    (final_path, task_id, pid),
                )

                # Register to processed_photos
                db.execute(
                    "INSERT INTO processed_photos "
                    "(photo_id, task_id, file_path, crop_preset, watermark_preset, "
                    "config_json, width, height, file_size) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (pid, task_id, final_path, crop_preset, watermark_preset,
                     json.dumps(config_dict, ensure_ascii=False),
                     final_w, final_h, file_size),
                )
                db.commit()
                completed += 1

            except Exception as e:
                logger.error("Failed to process %s: %s", photo["filename"], e)
                db.execute(
                    "UPDATE batch_process_items SET phase = 'error', "
                    "error_msg = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE task_id = ? AND photo_id = ?",
                    (str(e), task_id, pid),
                )
                db.commit()
                failed += 1

            # Update progress
            progress = 65 + int((i + 1) / total * 35)
            _update_progress(db, task_id, min(progress, 99), {
                "current_phase": "crop",
                "current_file": photo["filename"],
                "total": total,
                "completed": completed,
                "failed": failed,
                "phase_progress": {
                    "filter": 100, "denoise": 100, "tone": 100,
                    "crop": int((i + 1) / total * 100),
                },
            })

        # ── Done ──
        final_status = db.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if final_status and final_status["status"] != "cancelled":
            _update_progress(db, task_id, 100, {
                "current_phase": "done",
                "total": total,
                "completed": completed,
                "failed": failed,
                "phase_progress": {"filter": 100, "denoise": 100, "tone": 100, "crop": 100},
            })
            db.execute(
                "UPDATE tasks SET status = 'done', progress = 100, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id,),
            )
            db.commit()

        logger.info(
            "Batch process %s done: %d/%d completed, %d failed",
            task_id, completed, total, failed,
        )

        # Cleanup intermediate files (only on full success)
        if failed == 0:
            for d in [denoise_dir, toned_dir]:
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
            logger.info("Cleaned intermediate directories for task %s", task_id)

    except InterruptedError:
        logger.info("Batch process %s cancelled", task_id)
    except Exception as e:
        logger.error("Batch process %s failed: %s", task_id, e, exc_info=True)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(e), task_id),
        )
        db.commit()
    finally:
        # Restore PureRAW preset if not yet restored
        if pureraw_backup and os.path.exists(pureraw_backup):
            try:
                pureraw_service.restore_preset(pureraw_backup)
            except Exception:
                pass
        db.close()
