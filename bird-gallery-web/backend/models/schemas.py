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


class AdminTaskSummary(BaseModel):
    id: str
    type: str
    status: str
    progress: int = 0
    result_json: Optional[str] = None
    error_msg: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    detail: Optional[str] = None
    can_cancel: bool = False
    can_retry: bool = False


class AdminTaskListResponse(BaseModel):
    items: list[AdminTaskSummary] = Field(default_factory=list)
    running: int = 0
    queued: int = 0


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


class PhotoEditVersionSummary(BaseModel):
    version_id: int
    version_no: int
    is_current: bool = False
    is_auto_tone: bool = False
    preview_url: Optional[str] = None
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    created_at: Optional[datetime] = None


class PhotoEditCurrentVersion(BaseModel):
    version_id: int
    version_no: int
    preview_url: Optional[str] = None
    is_auto_tone: bool = False
    engine: Optional[str] = None
    engine_version: Optional[str] = None


class PhotoEditDraftState(BaseModel):
    draft_id: int
    base_version_id: Optional[int] = None
    params_json: dict = Field(default_factory=dict)
    params_hash: str
    render_revision: int = 0
    render_status: str = "idle"
    preview_url: Optional[str] = None
    last_task_id: Optional[str] = None
    engine: Optional[str] = None
    engine_version: Optional[str] = None


class PhotoEditStateResponse(BaseModel):
    photo_id: str
    is_raw: bool = False
    has_auto_tone_result: bool = False
    current_version: PhotoEditCurrentVersion
    current_draft: PhotoEditDraftState
    versions: list[PhotoEditVersionSummary] = Field(default_factory=list)


class PhotoEditAutoToneRequest(BaseModel):
    engine: str = "internal_v1"
    base_version_id: Optional[int] = None
    force_recompute: bool = False


class PhotoEditPatchDraftRequest(BaseModel):
    params: dict = Field(default_factory=dict)


class PhotoEditCommitRequest(BaseModel):
    set_current: bool = True


class PhotoEditRenderPreviewRequest(BaseModel):
    preview_size: int = 1600
    quality: int = 90
    force_recompute: bool = False


class PhotoEditRenderPreviewResponse(BaseModel):
    status: str
    preview_url: Optional[str] = None
    histogram: Optional[dict] = None
    task_id: Optional[str] = None
    render_mode: str
    render_time_ms: Optional[int] = None
    render_revision: int


class PhotoEditDraftMutationResponse(BaseModel):
    draft_id: int
    params_json: dict = Field(default_factory=dict)
    params_hash: Optional[str] = None
    render_revision: int
    draft_updated_at: Optional[datetime] = None


class PhotoEditCommitResponse(BaseModel):
    version_id: int
    version_no: int
    version_preview_url: Optional[str] = None
    current_version_changed: bool = True
    draft_rebased: bool = True


class PhotoEditDiscardResponse(BaseModel):
    draft_id: int
    base_version_id: Optional[int] = None
    params_json: dict = Field(default_factory=dict)
    render_revision: int
    preview_url: Optional[str] = None


class PhotoEditActivateResponse(BaseModel):
    current_version_id: int
    current_version_preview_url: Optional[str] = None
    draft_id: int
    draft_reset: bool = True


class PhotoEditExportRequest(BaseModel):
    format: str = "tiff"
    quality: int = 95
    write_xmp: bool = True


class PhotoEditExportQueuedResponse(BaseModel):
    task_id: str
    status: str

