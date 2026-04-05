"""管理 API — 健康检查 + 系统指标 + 系统配置"""

import os
import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models.database import get_db
from models.schemas import HealthResponse, MetricsResponse, ModelStatus
from services.model_manager import model_manager
from api.auth import require_admin
from app_config_pkg import config as app_config

router = APIRouter(tags=["admin"])


@router.get("/admin/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@router.get("/admin/metrics", response_model=MetricsResponse)
async def metrics(db=Depends(get_db)):
    """系统指标：内存、模型状态、任务统计。"""
    # 内存
    mem = psutil.virtual_memory()
    process = psutil.Process(os.getpid())
    app_mem = process.memory_info().rss / (1024 ** 3)

    memory = {
        "system_total_gb": round(mem.total / (1024 ** 3), 1),
        "system_used_gb": round(mem.used / (1024 ** 3), 1),
        "app_used_gb": round(app_mem, 2),
    }

    # 模型
    model_status_raw = model_manager.get_status()
    models = {
        name: ModelStatus(**info) for name, info in model_status_raw.items()
    }

    # 任务
    running = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE status = 'running'"
    ).fetchone()[0]
    queued = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE status = 'pending'"
    ).fetchone()[0]

    return MetricsResponse(
        memory=memory,
        models=models,
        tasks={"running": running, "queued": queued},
    )


@router.post("/admin/release-models")
async def release_models():
    """手动释放所有已加载 AI 模型。"""
    model_manager.release_all()
    return {"released": True}


# ── 系统配置 ──

class ConfigUpdate(BaseModel):
    media_dir: str | None = None
    scan_roots: list[str] | None = None


@router.get("/admin/config", dependencies=[Depends(require_admin)])
async def get_config():
    """获取当前系统配置。"""
    return app_config.get_all()


@router.put("/admin/config", dependencies=[Depends(require_admin)])
async def update_config(req: ConfigUpdate):
    """更新系统配置（仅管理员）。"""
    updates = {}

    if req.media_dir is not None:
        path = os.path.abspath(req.media_dir)
        # 安全：禁止指向系统关键目录
        forbidden = ('/', '/bin', '/usr', '/etc', '/sbin', '/var', '/System')
        if path in forbidden:
            raise HTTPException(400, f"不允许将媒体目录设置为 {path}")
        # 检查目录是否可写（目录不存在则尝试创建）
        try:
            os.makedirs(path, exist_ok=True)
            if not os.access(path, os.W_OK):
                raise HTTPException(400, f"目录 {path} 不可写")
        except OSError as e:
            raise HTTPException(400, f"无法创建目录 {path}: {e}")
        updates['media_dir'] = path

    if req.scan_roots is not None:
        # 校验每个路径存在且是目录
        for p in req.scan_roots:
            rp = os.path.abspath(p)
            if not os.path.isdir(rp):
                raise HTTPException(400, f"扫描路径不存在或不是目录: {rp}")
        updates['scan_roots'] = [os.path.abspath(p) for p in req.scan_roots]

    if not updates:
        raise HTTPException(400, "没有要更新的配置项")

    app_config.update(updates)

    # 如果更新了 media_dir，确保子目录存在
    if 'media_dir' in updates:
        app_config.ensure_media_dirs()

    return app_config.get_all()
