"""
水印服务

支持 4 种水印类型：text/image/tiled/info-bar。
可叠加多层水印。
"""

import logging
import math
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── 水印预设 ──

WATERMARK_PRESETS: dict[str, dict] = {
    "simple_copyright": {
        "label": "\u7b80\u7ea6\u7248\u6743",
        "layers": [
            {"type": "text", "text": "\u00a9 YourName", "position": "bottom-right"},
        ],
    },
    "brand_logo": {
        "label": "\u54c1\u724cLogo",
        "layers": [
            {"type": "image", "logo_path": "", "position": "bottom-right", "logo_scale": 0.1},
        ],
    },
    "anti_theft": {
        "label": "\u9632\u76d7\u6c34\u5370",
        "layers": [
            {"type": "tiled", "text": "\u00a9 YourName", "opacity": 30, "rotation": -30},
        ],
    },
    "bird_guide": {
        "label": "\u9e1f\u7c7b\u56fe\u9274",
        "layers": [
            {"type": "info-bar", "show_species": True, "show_exif": True, "show_copyright": True},
        ],
    },
    "social_share": {
        "label": "\u793e\u4ea4\u5206\u4eab",
        "layers": [
            {"type": "info-bar", "show_species": True, "show_exif": True, "show_copyright": True},
            {"type": "text", "text": "@my_bird_account", "position": "bottom-right"},
        ],
    },
    "none": {
        "label": "\u65e0\u6c34\u5370",
        "layers": [],
    },
}

# Default font path for macOS
_DEFAULT_FONT = "/System/Library/Fonts/PingFang.ttc"


def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load font with fallback."""
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype(_DEFAULT_FONT, size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _calc_position(
    canvas_w: int, canvas_h: int,
    elem_w: int, elem_h: int,
    position: str, margin: int,
) -> tuple[int, int]:
    """Calculate (x, y) given a 9-grid position string."""
    positions = {
        "top-left": (margin, margin),
        "top-center": ((canvas_w - elem_w) // 2, margin),
        "top-right": (canvas_w - elem_w - margin, margin),
        "center-left": (margin, (canvas_h - elem_h) // 2),
        "center": ((canvas_w - elem_w) // 2, (canvas_h - elem_h) // 2),
        "center-right": (canvas_w - elem_w - margin, (canvas_h - elem_h) // 2),
        "bottom-left": (margin, canvas_h - elem_h - margin),
        "bottom-center": ((canvas_w - elem_w) // 2, canvas_h - elem_h - margin),
        "bottom-right": (canvas_w - elem_w - margin, canvas_h - elem_h - margin),
    }
    return positions.get(position, positions["bottom-right"])


def apply_text_watermark(
    img: Image.Image,
    text: str = "\u00a9 YourName",
    font_path: str = _DEFAULT_FONT,
    font_size: int = 48,
    color: tuple[int, int, int] = (255, 255, 255),
    opacity: int = 128,
    position: str = "bottom-right",
    margin: int = 40,
    shadow: bool = True,
    shadow_color: tuple[int, int, int] = (0, 0, 0),
    shadow_offset: int = 2,
) -> Image.Image:
    """Apply text watermark to image."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_font(font_path, font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = _calc_position(img.width, img.height, tw, th, position, margin)

    if shadow:
        draw.text(
            (x + shadow_offset, y + shadow_offset),
            text, font=font,
            fill=(*shadow_color, opacity),
        )
    draw.text((x, y), text, font=font, fill=(*color, opacity))

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    result = Image.alpha_composite(img, overlay)
    return result


def apply_image_watermark(
    img: Image.Image,
    logo_path: str,
    logo_scale: float = 0.1,
    opacity: int = 180,
    position: str = "bottom-right",
    margin: int = 40,
) -> Image.Image:
    """Apply image/logo watermark."""
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except (OSError, IOError):
        logger.warning("Cannot open logo: %s, skipping", logo_path)
        return img

    # Scale logo
    target_w = int(img.width * logo_scale)
    ratio = target_w / logo.width
    target_h = int(logo.height * ratio)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    # Apply opacity
    if opacity < 255:
        alpha = logo.getchannel("A")
        alpha = alpha.point(lambda a: int(a * opacity / 255))
        logo.putalpha(alpha)

    x, y = _calc_position(img.width, img.height, target_w, target_h, position, margin)

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay.paste(logo, (x, y))
    result = Image.alpha_composite(img, overlay)
    return result


def apply_tiled_watermark(
    img: Image.Image,
    text: str = "\u00a9 YourName",
    font_size: int = 36,
    opacity: int = 30,
    color: tuple[int, int, int] = (255, 255, 255),
    rotation: int = -30,
    spacing_x: int = 300,
    spacing_y: int = 200,
    font_path: str = _DEFAULT_FONT,
) -> Image.Image:
    """Apply tiled watermark across entire image."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    font = _load_font(font_path, font_size)

    # Create a large canvas for tiling (larger than image to handle rotation)
    diag = int(math.sqrt(img.width ** 2 + img.height ** 2))
    tile_canvas = Image.new("RGBA", (diag * 2, diag * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile_canvas)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]

    for y in range(0, diag * 2, spacing_y):
        for x in range(0, diag * 2, spacing_x + tw):
            draw.text((x, y), text, font=font, fill=(*color, opacity))

    # Rotate and crop to image size
    tile_canvas = tile_canvas.rotate(rotation, expand=False, center=(diag, diag))
    # Crop center
    left = diag - img.width // 2
    top = diag - img.height // 2
    tile_canvas = tile_canvas.crop(
        (left, top, left + img.width, top + img.height)
    )

    result = Image.alpha_composite(img, tile_canvas)
    return result


def apply_info_bar(
    img: Image.Image,
    species_cn: str = "",
    species_en: str = "",
    exif_data: Optional[dict] = None,
    bar_position: str = "bottom",
    bar_mode: str = "append",
    bar_bg_color: tuple[int, int, int] = (20, 20, 20),
    bar_padding: int = 24,
    text_color: tuple[int, int, int] = (230, 230, 230),
    font_path: str = _DEFAULT_FONT,
    title_font_size: int = 42,
    detail_font_size: int = 28,
    show_species: bool = True,
    species_lang: str = "cn+en",
    show_exif: bool = True,
    exif_fields: Optional[list[str]] = None,
    show_copyright: bool = True,
    copyright_text: str = "\u00a9 2026 YourName",
) -> Image.Image:
    """Apply info-bar watermark (EXIF + species info bar)."""
    title_font = _load_font(font_path, title_font_size)
    detail_font = _load_font(font_path, detail_font_size)

    # Build text lines
    lines: list[tuple[str, ImageFont.FreeTypeFont]] = []

    if show_species:
        species_text = ""
        if species_lang == "cn":
            species_text = species_cn or ""
        elif species_lang == "en":
            species_text = species_en or ""
        elif species_lang == "cn+en":
            parts = [p for p in [species_cn, species_en] if p]
            species_text = " ".join(parts)
        elif species_lang == "scientific":
            species_text = species_en or species_cn or ""
        if species_text:
            lines.append((species_text, title_font))

    if show_exif and exif_data:
        all_fields = exif_fields or [
            "camera", "lens", "focal", "aperture", "shutter", "iso",
        ]
        parts = []
        field_map = {
            "camera": ("camera_model", None),
            "lens": ("lens_model", None),
            "focal": ("focal_length", "mm"),
            "aperture": ("aperture", None),
            "shutter": ("shutter_speed", None),
            "iso": ("iso", None),
        }
        for field in all_fields:
            if field in field_map:
                key, suffix = field_map[field]
                val = exif_data.get(key)
                if val is not None:
                    s = str(val)
                    if field == "aperture":
                        s = f"f/{val}"
                    elif field == "focal":
                        s = f"{val}mm"
                    elif field == "iso":
                        s = f"ISO {val}"
                    elif field == "shutter":
                        s = f"{val}s"
                    parts.append(s)
        if parts:
            lines.append((" \u00b7 ".join(parts), detail_font))

    if show_copyright and copyright_text:
        lines.append((copyright_text, detail_font))

    if not lines:
        return img

    # Calculate bar height
    line_heights = []
    for text, font in lines:
        bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(
            (0, 0), text, font=font,
        )
        line_heights.append(bbox[3] - bbox[1])

    total_text_h = sum(line_heights) + (len(lines) - 1) * 8  # 8px line gap
    bar_h = total_text_h + bar_padding * 2

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    if bar_mode == "append":
        # Create new image with bar appended
        new_h = img.height + bar_h
        new_img = Image.new("RGBA", (img.width, new_h), (0, 0, 0, 0))
        if bar_position == "top":
            # Bar at top, image below
            bar_y = 0
            img_y = bar_h
        else:
            # Image at top, bar below
            bar_y = img.height
            img_y = 0
        new_img.paste(img, (0, img_y))
    else:
        # Overlay mode: bar over image pixels
        new_img = img.copy()
        if bar_position == "top":
            bar_y = 0
        else:
            bar_y = img.height - bar_h

    # Draw bar background
    draw = ImageDraw.Draw(new_img)
    draw.rectangle(
        [0, bar_y, new_img.width, bar_y + bar_h],
        fill=(*bar_bg_color, 240),
    )

    # Draw text lines
    y_cursor = bar_y + bar_padding
    for i, (text, font) in enumerate(lines):
        # Last line (copyright): right-align
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        if i == len(lines) - 1 and show_copyright:
            x = new_img.width - tw - bar_padding
        else:
            x = bar_padding
        draw.text((x, y_cursor), text, font=font, fill=(*text_color, 255))
        y_cursor += line_heights[i] + 8

    return new_img


def apply_watermark_layers(
    img: Image.Image,
    layers: list[dict],
    species_cn: str = "",
    species_en: str = "",
    exif_data: Optional[dict] = None,
) -> Image.Image:
    """Apply multiple watermark layers sequentially."""
    for layer in layers:
        wm_type = layer.get("type", "text")
        if wm_type == "text":
            img = apply_text_watermark(
                img,
                text=layer.get("text", "\u00a9 YourName"),
                font_path=layer.get("font", _DEFAULT_FONT),
                font_size=layer.get("font_size", 48),
                color=tuple(layer.get("color", (255, 255, 255))),
                opacity=layer.get("opacity", 128),
                position=layer.get("position", "bottom-right"),
                margin=layer.get("margin", 40),
                shadow=layer.get("shadow", True),
                shadow_color=tuple(layer.get("shadow_color", (0, 0, 0))),
                shadow_offset=layer.get("shadow_offset", 2),
            )
        elif wm_type == "image":
            logo_path = layer.get("logo_path", "")
            if logo_path:
                img = apply_image_watermark(
                    img,
                    logo_path=logo_path,
                    logo_scale=layer.get("logo_scale", 0.1),
                    opacity=layer.get("opacity", 180),
                    position=layer.get("position", "bottom-right"),
                    margin=layer.get("margin", 40),
                )
        elif wm_type == "tiled":
            img = apply_tiled_watermark(
                img,
                text=layer.get("text", "\u00a9 YourName"),
                font_size=layer.get("font_size", 36),
                opacity=layer.get("opacity", 30),
                color=tuple(layer.get("color", (255, 255, 255))),
                rotation=layer.get("rotation", -30),
                spacing_x=layer.get("spacing_x", 300),
                spacing_y=layer.get("spacing_y", 200),
            )
        elif wm_type == "info-bar":
            img = apply_info_bar(
                img,
                species_cn=species_cn,
                species_en=species_en,
                exif_data=exif_data,
                bar_position=layer.get("bar_position", "bottom"),
                bar_mode=layer.get("bar_mode", "append"),
                bar_bg_color=tuple(layer.get("bar_bg_color", (20, 20, 20))),
                bar_padding=layer.get("bar_padding", 24),
                text_color=tuple(layer.get("text_color", (230, 230, 230))),
                title_font_size=layer.get("title_font_size", 42),
                detail_font_size=layer.get("detail_font_size", 28),
                show_species=layer.get("show_species", True),
                species_lang=layer.get("species_lang", "cn+en"),
                show_exif=layer.get("show_exif", True),
                exif_fields=layer.get("exif_fields"),
                show_copyright=layer.get("show_copyright", True),
                copyright_text=layer.get("copyright_text", "\u00a9 2026 YourName"),
            )
    return img


def get_watermark_presets() -> dict[str, dict]:
    """Return all available watermark presets."""
    return WATERMARK_PRESETS
