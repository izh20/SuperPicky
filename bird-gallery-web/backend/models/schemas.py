"""Pydantic 请求/响应模型 — Phase 1: 照片管理"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── 照片 ──

class PhotoBase(BaseModel):
    id: str
    filename: str
    original_path: str
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    imported_at: Optional[datetime] = None


class PhotoMetadata(BaseModel):
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    iso: Optional[int] = None
    shutter_speed: Optional[str] = None
    aperture: Optional[float] = None
    focal_length: Optional[float] = None
    focal_length_35mm: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    gps_altitude: Optional[float] = None
    # EXIF 常见格式为 YYYY:MM:DD HH:MM:SS，不保证是 ISO datetime
    date_taken: Optional[str] = None
    timezone: Optional[str] = None


class BirdResult(BaseModel):
    species_cn: Optional[str] = None
    species_en: Optional[str] = None
    scientific_name: Optional[str] = None
    confidence: Optional[float] = None
    rank: Optional[int] = None
    detection_box: Optional[str] = None  # JSON string


class PhotoScore(BaseModel):
    rating: Optional[int] = None
    head_sharp: Optional[float] = None
    nima_score: Optional[float] = None
    is_flying: Optional[int] = None
    focus_status: Optional[str] = None
    exposure_status: Optional[str] = None


class PhotoDetail(PhotoBase):
    """照片详情：含 EXIF + 识别结果 + 评分"""
    metadata: Optional[PhotoMetadata] = None
    birds: list[BirdResult] = Field(default_factory=list)
    score: Optional[PhotoScore] = None


class PhotoListItem(BaseModel):
    """照片列表项（轻量，不含完整 EXIF）"""
    id: str
    filename: str
    rating: Optional[int] = None
    species_cn: Optional[str] = None
    # 供列表展示的参考指标
    confidence: Optional[float] = None
    head_sharp: Optional[float] = None
    nima_score: Optional[float] = None
    # 列表接口直接返回数据库原始字符串，避免 EXIF 日期格式校验失败
    date_taken: Optional[str] = None
    imported_at: Optional[datetime] = None


class PhotoListResponse(BaseModel):
    items: list[PhotoListItem]
    total: int
    page: int
    page_size: int


# ── 识别 ──

class RecognizeResponse(BaseModel):
    photo_id: str
    birds: list[BirdResult]
    score: Optional[PhotoScore] = None


class BatchRecognizeRequest(BaseModel):
    photo_ids: list[str]


# ── 任务 ──

class TaskResponse(BaseModel):
    id: str
    type: str
    status: str  # pending / running / done / error
    progress: int = 0
    result_json: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── 管理 ──

class ModelStatus(BaseModel):
    loaded: bool
    memory_mb: Optional[int] = None
    last_used: Optional[str] = None


class MetricsResponse(BaseModel):
    memory: dict
    models: dict[str, ModelStatus]
    tasks: dict


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
