"""
智能裁切服务

根据鸟类检测框和用户配置，提供 4 种构图模式的智能裁切。
"""

import json
import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# ── 裁切预设 ──

CROP_PRESETS: dict[str, dict] = {
    "4k_wallpaper": {
        "aspect_ratio": "16:9",
        "output_size": (3840, 2160),
        "composition": "environmental",
        "bird_padding": 1.3,
        "label": "4K \u58c1\u7eb8",
    },
    "phone_wallpaper": {
        "aspect_ratio": "9:16",
        "output_size": (2160, 3840),
        "composition": "center",
        "bird_padding": 1.3,
        "label": "\u624b\u673a\u58c1\u7eb8",
    },
    "social_square": {
        "aspect_ratio": "1:1",
        "output_size": (2160, 2160),
        "composition": "center",
        "bird_padding": 1.3,
        "label": "\u793e\u4ea4\u65b9\u56fe",
    },
    "bird_closeup": {
        "aspect_ratio": "4:3",
        "output_size": (3840, 2880),
        "composition": "tight",
        "bird_padding": 1.3,
        "label": "\u9e1f\u7c7b\u7279\u5199",
    },
    "cinematic": {
        "aspect_ratio": "21:9",
        "output_size": (3440, 1440),
        "composition": "rule-of-thirds",
        "bird_padding": 1.3,
        "label": "\u7535\u5f71\u5bbd\u5e45",
    },
    "original_crop": {
        "aspect_ratio": "original",
        "output_size": None,
        "composition": "center",
        "bird_padding": 1.3,
        "label": "\u539f\u56fe\u88c1\u5207",
    },
}

ASPECT_RATIOS: dict[str, float] = {
    "16:9": 16 / 9,
    "4:3": 4 / 3,
    "3:2": 3 / 2,
    "1:1": 1.0,
    "21:9": 21 / 9,
    "9:16": 9 / 16,
}


def _parse_detection_box(detection_box: str | None) -> Optional[list[float]]:
    """Parse detection_box JSON string to [x1, y1, x2, y2]."""
    if not detection_box:
        return None
    try:
        box = json.loads(detection_box)
        if isinstance(box, list) and len(box) == 4:
            return [float(v) for v in box]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def _clamp_rect(x: int, y: int, w: int, h: int,
                img_w: int, img_h: int) -> tuple[int, int, int, int]:
    """Clamp crop rect to image bounds, return (x, y, w, h)."""
    x = max(0, min(x, img_w - w))
    y = max(0, min(y, img_h - h))
    w = min(w, img_w)
    h = min(h, img_h)
    return x, y, w, h


def _bird_fully_inside(bird_box: list[float],
                       crop_x: int, crop_y: int,
                       crop_w: int, crop_h: int) -> bool:
    """Check if bird bbox is fully inside the crop rect."""
    bx1, by1, bx2, by2 = bird_box
    return (bx1 >= crop_x and by1 >= crop_y and
            bx2 <= crop_x + crop_w and by2 <= crop_y + crop_h)


def compute_crop_rect(
    img_w: int,
    img_h: int,
    bird_box: list[float],
    aspect_ratio: str = "16:9",
    composition: str = "center",
    bird_padding: float = 1.3,
) -> tuple[int, int, int, int]:
    """Compute crop rectangle (x, y, w, h) on the source image.

    Returns the crop box in image pixel coordinates.
    Falls back to center mode if bird would be cropped.
    """
    bx1, by1, bx2, by2 = bird_box
    bird_cx = (bx1 + bx2) / 2
    bird_cy = (by1 + by2) / 2
    bird_w = bx2 - bx1
    bird_h = by2 - by1

    # Determine target aspect ratio
    if aspect_ratio == "original":
        ratio = img_w / img_h
    else:
        ratio = ASPECT_RATIOS.get(aspect_ratio, 16 / 9)

    if composition == "tight":
        return _crop_tight(img_w, img_h, bird_box, ratio, bird_padding)
    elif composition == "environmental":
        return _crop_environmental(img_w, img_h, bird_box, ratio)
    elif composition == "rule-of-thirds":
        rect = _crop_rule_of_thirds(img_w, img_h, bird_box, ratio)
    else:  # center
        rect = _crop_center(img_w, img_h, bird_box, ratio)

    # Safety: verify bird is fully inside, fallback to center
    cx, cy, cw, ch = rect
    if not _bird_fully_inside(bird_box, cx, cy, cw, ch):
        rect = _crop_center(img_w, img_h, bird_box, ratio)

    return rect


def _crop_center(img_w: int, img_h: int,
                 bird_box: list[float], ratio: float
                 ) -> tuple[int, int, int, int]:
    """Bird center = crop center, maximum crop size within aspect ratio."""
    bx1, by1, bx2, by2 = bird_box
    bird_cx = (bx1 + bx2) / 2
    bird_cy = (by1 + by2) / 2

    # Maximum crop at this aspect ratio
    if img_w / img_h > ratio:
        crop_h = img_h
        crop_w = int(crop_h * ratio)
    else:
        crop_w = img_w
        crop_h = int(crop_w / ratio)

    cx = int(bird_cx - crop_w / 2)
    cy = int(bird_cy - crop_h / 2)
    cx, cy, crop_w, crop_h = _clamp_rect(cx, cy, crop_w, crop_h, img_w, img_h)
    return cx, cy, crop_w, crop_h


def _crop_rule_of_thirds(img_w: int, img_h: int,
                         bird_box: list[float], ratio: float
                         ) -> tuple[int, int, int, int]:
    """Place bird center nearest to a rule-of-thirds intersection point,
    preferring upper intersections."""
    bx1, by1, bx2, by2 = bird_box
    bird_cx = (bx1 + bx2) / 2
    bird_cy = (by1 + by2) / 2

    # Maximum crop at this aspect ratio
    if img_w / img_h > ratio:
        crop_h = img_h
        crop_w = int(crop_h * ratio)
    else:
        crop_w = img_w
        crop_h = int(crop_w / ratio)

    # 4 intersection points relative to crop frame
    thirds_points = [
        (crop_w / 3, crop_h / 3),      # top-left
        (2 * crop_w / 3, crop_h / 3),   # top-right
        (crop_w / 3, 2 * crop_h / 3),   # bottom-left
        (2 * crop_w / 3, 2 * crop_h / 3),  # bottom-right
    ]

    # Prefer upper points — weight lower y
    best_offset = None
    best_score = float('inf')
    for tx, ty in thirds_points:
        # Crop origin so that bird_cx,bird_cy sits at thirds point
        ox = int(bird_cx - tx)
        oy = int(bird_cy - ty)
        ox, oy, _, _ = _clamp_rect(ox, oy, crop_w, crop_h, img_w, img_h)
        # Score = distance + penalty for bottom points
        dx = bird_cx - (ox + tx)
        dy = bird_cy - (oy + ty)
        dist = (dx ** 2 + dy ** 2) ** 0.5
        # Prefer upper row
        y_penalty = 0 if ty < crop_h / 2 else 50
        score = dist + y_penalty
        if score < best_score:
            best_score = score
            best_offset = (ox, oy)

    cx, cy = best_offset  # type: ignore[misc]
    return cx, cy, crop_w, crop_h


def _crop_tight(img_w: int, img_h: int,
                bird_box: list[float], ratio: float,
                bird_padding: float
                ) -> tuple[int, int, int, int]:
    """Tight crop around bird with padding, then adjust to aspect ratio."""
    bx1, by1, bx2, by2 = bird_box
    bird_cx = (bx1 + bx2) / 2
    bird_cy = (by1 + by2) / 2
    bird_w = bx2 - bx1
    bird_h = by2 - by1

    # Padded bird area
    pad_w = bird_w * bird_padding
    pad_h = bird_h * bird_padding

    # Adjust to target aspect ratio (expand the smaller dimension)
    if pad_w / pad_h > ratio:
        crop_w = int(pad_w)
        crop_h = int(crop_w / ratio)
    else:
        crop_h = int(pad_h)
        crop_w = int(crop_h * ratio)

    # Ensure minimum size
    crop_w = max(crop_w, 100)
    crop_h = max(crop_h, 100)

    # Clamp to image
    crop_w = min(crop_w, img_w)
    crop_h = min(crop_h, img_h)

    cx = int(bird_cx - crop_w / 2)
    cy = int(bird_cy - crop_h / 2)
    cx, cy, crop_w, crop_h = _clamp_rect(cx, cy, crop_w, crop_h, img_w, img_h)
    return cx, cy, crop_w, crop_h


def _crop_environmental(img_w: int, img_h: int,
                        bird_box: list[float], ratio: float
                        ) -> tuple[int, int, int, int]:
    """Maximize crop area (near full image), shift to include bird."""
    # Use full image width/height constrained by aspect ratio
    if img_w / img_h > ratio:
        crop_h = img_h
        crop_w = int(crop_h * ratio)
    else:
        crop_w = img_w
        crop_h = int(crop_w / ratio)

    bx1, by1, bx2, by2 = bird_box
    bird_cx = (bx1 + bx2) / 2
    bird_cy = (by1 + by2) / 2

    # Try to center horizontally on bird (but still full-size)
    cx = int(bird_cx - crop_w / 2)
    cy = int(bird_cy - crop_h / 2)
    cx, cy, crop_w, crop_h = _clamp_rect(cx, cy, crop_w, crop_h, img_w, img_h)
    return cx, cy, crop_w, crop_h


def smart_crop(
    img: Image.Image,
    bird_box: list[float],
    aspect_ratio: str = "16:9",
    output_size: tuple[int, int] | None = (3840, 2160),
    composition: str = "center",
    bird_padding: float = 1.3,
) -> Image.Image:
    """Perform smart crop on a PIL Image and return the cropped result.

    Args:
        img: Source PIL Image
        bird_box: [x1, y1, x2, y2] in image pixel coordinates
        aspect_ratio: Target aspect ratio string
        output_size: (width, height) to resize to, or None to keep crop size
        composition: Composition mode
        bird_padding: Padding multiplier for tight mode

    Returns:
        Cropped (and optionally resized) PIL Image
    """
    cx, cy, cw, ch = compute_crop_rect(
        img.width, img.height, bird_box,
        aspect_ratio, composition, bird_padding,
    )
    cropped = img.crop((cx, cy, cx + cw, cy + ch))

    if output_size:
        target_w, target_h = output_size
        # Only resize if target is smaller than crop (downscale only)
        if cropped.width > target_w or cropped.height > target_h:
            cropped = cropped.resize((target_w, target_h), Image.LANCZOS)

    return cropped


def get_crop_presets() -> dict[str, dict]:
    """Return all available crop presets."""
    return CROP_PRESETS
