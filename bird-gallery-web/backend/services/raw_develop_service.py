import hashlib
import io
import logging
import math
import os
import subprocess
import threading
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageOps

from services.adobe_dng_service import ensure_sidecar_dng

logger = logging.getLogger(__name__)

RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2'}
_CACHE_LOCK = threading.Lock()
_DECODE_CACHE: OrderedDict[tuple, np.ndarray] = OrderedDict()
_MAX_CACHE_ITEMS = 6


def _get_exiftool_cmd() -> str:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    bundled = os.path.join(project_root, 'exiftools_mac', 'exiftool')
    return bundled if os.path.exists(bundled) else 'exiftool'


_EXIFTOOL = _get_exiftool_cmd()


def is_raw_path(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in RAW_EXTENSIONS


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)


def _cache_key(file_path: str, half_size: bool) -> tuple:
    stat = os.stat(file_path)
    return (file_path, stat.st_mtime_ns, stat.st_size, half_size)


def _remember_cache(key: tuple, image: np.ndarray):
    with _CACHE_LOCK:
        _DECODE_CACHE[key] = image
        _DECODE_CACHE.move_to_end(key)
        while len(_DECODE_CACHE) > _MAX_CACHE_ITEMS:
            _DECODE_CACHE.popitem(last=False)


def _get_cached_image(key: tuple) -> np.ndarray | None:
    with _CACHE_LOCK:
        value = _DECODE_CACHE.get(key)
        if value is not None:
            _DECODE_CACHE.move_to_end(key)
        return None if value is None else value.copy()


def _load_standard_image(file_path: str) -> np.ndarray:
    with Image.open(file_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        rgb = np.asarray(image, dtype=np.float32) / 255.0
    return _srgb_to_linear(rgb)


def _decode_with_rawpy(file_path: str, half_size: bool) -> np.ndarray:
    import rawpy

    with rawpy.imread(file_path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            half_size=half_size,
            output_bps=16,
            no_auto_bright=True,
            gamma=(1, 1),
        )
    return np.asarray(rgb, dtype=np.float32) / 65535.0


def _load_raw_image(file_path: str, half_size: bool) -> np.ndarray:
    try:
        return _decode_with_rawpy(file_path, half_size=half_size)
    except Exception as exc:
        sidecar_dng = ensure_sidecar_dng(file_path)
        if sidecar_dng and os.path.abspath(sidecar_dng) != os.path.abspath(file_path):
            try:
                logger.info('rawpy decode failed for %s, retrying with DNG sidecar %s', file_path, sidecar_dng)
                return _decode_with_rawpy(sidecar_dng, half_size=half_size)
            except Exception as sidecar_exc:
                logger.warning('DNG sidecar decode failed for %s via %s: %s', file_path, sidecar_dng, sidecar_exc)

        logger.warning('rawpy decode failed for %s, falling back to embedded preview: %s', file_path, exc)
        preview = _extract_embedded_preview(file_path)
        if preview is None:
            raise
        return preview


def _extract_embedded_preview(file_path: str) -> np.ndarray | None:
    for tag in ('-JpgFromRaw', '-PreviewImage'):
        try:
            result = subprocess.run(
                [_EXIFTOOL, tag, '-b', file_path],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0 or len(result.stdout) < 1024:
                continue
            with Image.open(io.BytesIO(result.stdout)) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                rgb = np.asarray(image, dtype=np.float32) / 255.0
                return _srgb_to_linear(rgb)
        except Exception:
            continue
    return None


def decode_linear_rgb(file_path: str, half_size: bool) -> np.ndarray:
    key = _cache_key(file_path, half_size)
    cached = _get_cached_image(key)
    if cached is not None:
        return cached

    if is_raw_path(file_path):
        image = _load_raw_image(file_path, half_size=half_size)
    else:
        image = _load_standard_image(file_path)

    _remember_cache(key, image)
    return image.copy()


def _apply_temperature_tint(rgb: np.ndarray, temperature: float, tint: float) -> np.ndarray:
    temperature = float(temperature)
    tint = float(tint)
    temp_norm = np.clip((temperature - 6500.0) / 4500.0, -1.0, 1.0)
    tint_norm = np.clip(tint / 150.0, -1.0, 1.0)

    red_gain = 1.0 + 0.18 * temp_norm + 0.04 * tint_norm
    green_gain = 1.0 - 0.12 * tint_norm
    blue_gain = 1.0 - 0.18 * temp_norm + 0.04 * tint_norm
    gains = np.array([red_gain, green_gain, blue_gain], dtype=np.float32)
    return rgb * gains.reshape((1, 1, 3))


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _apply_tone_controls(rgb: np.ndarray, params: dict) -> np.ndarray:
    luma = _luma(rgb)
    shadow_mask = np.clip((0.55 - luma) / 0.55, 0.0, 1.0) ** 2
    highlight_mask = np.clip((luma - 0.45) / 0.55, 0.0, 1.0) ** 2
    black_mask = np.clip((0.22 - luma) / 0.22, 0.0, 1.0) ** 2
    white_mask = np.clip((luma - 0.78) / 0.22, 0.0, 1.0) ** 2

    luma_adjusted = luma.copy()
    luma_adjusted += shadow_mask * (float(params.get('shadows', 0)) / 100.0) * 0.32
    luma_adjusted += highlight_mask * (float(params.get('highlights', 0)) / 100.0) * 0.28
    luma_adjusted += black_mask * (float(params.get('blacks', 0)) / 100.0) * 0.20
    luma_adjusted += white_mask * (float(params.get('whites', 0)) / 100.0) * 0.18

    contrast = float(params.get('contrast', 0)) / 100.0
    contrast_gain = 1.0 + 0.45 * contrast
    luma_adjusted = 0.5 + (luma_adjusted - 0.5) * contrast_gain
    luma_adjusted = np.clip(luma_adjusted, 0.0, 4.0)

    scale = np.where(luma > 1e-6, luma_adjusted / np.maximum(luma, 1e-6), 1.0)
    return rgb * scale[..., None]


def _apply_color_controls(rgb_srgb: np.ndarray, params: dict) -> np.ndarray:
    gray = _luma(rgb_srgb)[..., None]
    rgb = rgb_srgb.copy()

    vibrance = float(params.get('vibrance', 0)) / 100.0
    if abs(vibrance) > 1e-6:
        chroma = np.max(rgb, axis=2) - np.min(rgb, axis=2)
        protection = np.clip(chroma / 0.8, 0.0, 1.0)
        vib_gain = 1.0 + vibrance * (1.0 - protection) * 0.85
        rgb = gray + (rgb - gray) * vib_gain[..., None]

    saturation = float(params.get('saturation', 0)) / 100.0
    if abs(saturation) > 1e-6:
        sat_gain = 1.0 + saturation * 0.9
        rgb = gray + (rgb - gray) * sat_gain

    return np.clip(rgb, 0.0, 1.0)


def _resize_if_needed(rgb_srgb: np.ndarray, max_size: int | None) -> np.ndarray:
    if not max_size or max_size <= 0:
        return rgb_srgb
    height, width = rgb_srgb.shape[:2]
    largest = max(height, width)
    if largest <= max_size:
        return rgb_srgb
    scale = max_size / float(largest)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    image = Image.fromarray(np.clip(rgb_srgb * 255.0, 0, 255).astype(np.uint8), mode='RGB')
    image = image.resize(new_size, Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def compute_histogram(rgb_srgb: np.ndarray) -> dict:
    luma = np.clip(_luma(rgb_srgb), 0.0, 1.0)
    hist, _ = np.histogram(luma, bins=64, range=(0.0, 1.0))
    return {
        'luma': hist.astype(int).tolist(),
    }


def render_to_srgb(file_path: str, params: dict, preview_size: int | None = None, for_export: bool = False) -> tuple[np.ndarray, dict]:
    half_size = not for_export
    linear_rgb = decode_linear_rgb(file_path, half_size=half_size)
    linear_rgb = _apply_temperature_tint(
        linear_rgb,
        params.get('temperature', 6500),
        params.get('tint', 0),
    )

    exposure = float(params.get('exposure', 0.0))
    if abs(exposure) > 1e-6:
        linear_rgb = linear_rgb * math.pow(2.0, exposure)

    linear_rgb = _apply_tone_controls(linear_rgb, params)
    linear_rgb = np.clip(linear_rgb, 0.0, 4.0)

    tonemapped = linear_rgb / (1.0 + linear_rgb)
    rgb_srgb = _linear_to_srgb(tonemapped)
    rgb_srgb = _apply_color_controls(rgb_srgb, params)
    rgb_srgb = _resize_if_needed(rgb_srgb, None if for_export else preview_size)
    histogram = compute_histogram(rgb_srgb)
    return rgb_srgb, histogram


def save_rgb_image(rgb_srgb: np.ndarray, output_path: str, image_format: str, quality: int = 90):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    image = Image.fromarray(np.clip(rgb_srgb * 255.0, 0, 255).astype(np.uint8), mode='RGB')
    save_format = image_format.upper()
    if save_format == 'JPG':
        save_format = 'JPEG'
    if save_format == 'TIF':
        save_format = 'TIFF'
    save_kwargs = {}
    if save_format == 'JPEG':
        save_kwargs['quality'] = max(50, min(quality, 100))
    image.save(output_path, save_format, **save_kwargs)


def render_preview_file(file_path: str, params: dict, output_path: str, preview_size: int, quality: int = 90) -> dict:
    rgb_srgb, histogram = render_to_srgb(file_path, params, preview_size=preview_size, for_export=False)
    save_rgb_image(rgb_srgb, output_path, 'JPEG', quality=quality)
    return histogram


def render_export_file(file_path: str, params: dict, output_path: str, export_format: str, quality: int = 95) -> dict:
    rgb_srgb, histogram = render_to_srgb(file_path, params, preview_size=None, for_export=True)
    save_rgb_image(rgb_srgb, output_path, export_format, quality=quality)
    return histogram


def histogram_hash(histogram: dict | None) -> str | None:
    if not histogram:
        return None
    payload = repr(histogram).encode('utf-8')
    return hashlib.sha1(payload).hexdigest()