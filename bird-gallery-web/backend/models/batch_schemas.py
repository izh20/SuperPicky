"""Pydantic 模型 — RAW 批量处理管线"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal


class CropConfig(BaseModel):
    aspect_ratio: Literal[
        "16:9", "4:3", "3:2", "1:1", "21:9", "9:16", "original"
    ] = "16:9"
    output_size: Optional[tuple[int, int]] = (3840, 2160)
    composition: Literal[
        "center", "rule-of-thirds", "tight", "environmental"
    ] = "center"
    bird_padding: float = Field(default=1.3, ge=1.2)


class WatermarkConfig(BaseModel):
    type: Literal["text", "image", "tiled", "info-bar"] = "text"

    # --- 通用 ---
    opacity: int = 128
    position: Literal[
        "top-left", "top-center", "top-right",
        "center-left", "center", "center-right",
        "bottom-left", "bottom-center", "bottom-right",
    ] = "bottom-right"
    margin: int = 40

    # --- text 专用 ---
    text: str = "\u00a9 YourName"
    font: str = "/System/Library/Fonts/PingFang.ttc"
    font_size: int = 48
    color: tuple[int, int, int] = (255, 255, 255)
    shadow: bool = True
    shadow_color: tuple[int, int, int] = (0, 0, 0)
    shadow_offset: int = 2

    # --- image 专用 ---
    logo_path: Optional[str] = None
    logo_scale: float = 0.1

    # --- tiled 专用 ---
    rotation: int = -30
    spacing_x: int = 300
    spacing_y: int = 200

    # --- info-bar 专用 ---
    bar_position: Literal["bottom", "top"] = "bottom"
    bar_mode: Literal["append", "overlay"] = "append"
    bar_bg_color: tuple[int, int, int] = (20, 20, 20)
    bar_padding: int = 24
    text_color: tuple[int, int, int] = (230, 230, 230)
    title_font_size: int = 42
    detail_font_size: int = 28
    show_species: bool = True
    species_lang: Literal["cn", "en", "cn+en", "scientific"] = "cn+en"
    show_exif: bool = True
    exif_fields: Optional[list[str]] = None
    show_copyright: bool = True
    copyright_text: str = "\u00a9 2026 YourName"


class BatchProcessConfig(BaseModel):
    # --- 筛选 ---
    min_rating: Literal[0, 1, 2, 3] = 2

    # --- 降噪 ---
    denoise_enabled: bool = True
    denoise_algorithm: Literal["DeepPRIME_3", "DeepPRIME_XD3"] = "DeepPRIME_XD3"
    denoise_luminance: int = 40
    denoise_chrominance: int = 50

    # --- 调色 ---
    auto_tone_enabled: bool = True
    tone_mode: Literal["reference_version", "legacy_auto"] = "reference_version"
    reference_photo_id: Optional[str] = None
    reference_version_id: Optional[int] = None
    tone_params: Optional[dict] = None
    auto_tone_tool: Literal["lightroom", "darktable"] = "lightroom"

    # --- 裁切 ---
    crop_preset: str = "4k_wallpaper"
    crop_config: Optional[CropConfig] = None

    # --- 水印 ---
    watermark_preset: str = "simple_copyright"
    watermark_layers: Optional[list[WatermarkConfig]] = None

    # --- 输出 ---
    output_format: Literal["jpeg", "tiff", "png"] = "jpeg"
    output_quality: int = 95
    output_dir: str = ""


class BatchProcessStartResponse(BaseModel):
    task_id: str
    total_photos: int
    filtered_photos: int
    estimated_time_minutes: int


class BatchTonePresetSummary(BaseModel):
    photo_id: str
    filename: str
    version_id: int
    version_no: int
    is_current: bool
    is_auto_tone: bool
    preview_url: Optional[str] = None
    created_at: Optional[str] = None


class BatchProcessResultItem(BaseModel):
    photo_id: str
    filename: str
    phase: str
    final_output: Optional[str] = None
    error_msg: Optional[str] = None


class BatchProcessResultsResponse(BaseModel):
    task_id: str
    total: int
    completed: int
    failed: int
    items: list[BatchProcessResultItem]
