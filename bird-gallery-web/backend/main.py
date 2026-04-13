"""
FastAPI 应用入口

规则：
- sys.path.insert 必须在所有模块 import 之前
- 单 Uvicorn worker + asyncio.Lock 串行化 MPS 推理
- shutdown 事件中关闭 ExifToolManager 和 ModelManager
"""

import sys
import os

# ── sys.path 设置（必须在所有 SuperPicky 模块 import 之前）──
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio
import threading
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from models.database import init_db
from services.model_manager import model_manager
from app_config_pkg import config as app_config

logger = logging.getLogger("bird-gallery")

# ── 推理串行化锁 ──
inference_lock = asyncio.Lock()
# BackgroundTasks 在线程池中运行，asyncio.Lock 不适用于线程；
# 使用 threading.Lock 保护后台推理任务。
inference_thread_lock = threading.Lock()


# ── 僵尸分片清理 ──
def _cleanup_stale_chunks(max_age_hours: int = 24):
    """启动时清理超过 max_age_hours 的残留分片目录。"""
    import time, shutil
    chunks_root = app_config.chunks_dir()
    if not os.path.isdir(chunks_root):
        return
    now = time.time()
    cutoff = now - max_age_hours * 3600
    cleaned = 0
    for name in os.listdir(chunks_root):
        d = os.path.join(chunks_root, name)
        if os.path.isdir(d):
            try:
                mtime = os.path.getmtime(d)
                if mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    cleaned += 1
            except OSError:
                pass
    if cleaned:
        logger.info("Cleaned %d stale chunk directories", cleaned)


def _cleanup_orphan_tasks():
    """启动时将上次运行中被杀死的 running/pending 任务标记为 error。"""
    from models.database import get_db_connection
    db = get_db_connection()
    try:
        rows = db.execute(
            "SELECT id, type, status FROM tasks WHERE status IN ('running', 'pending')"
        ).fetchall()
        if rows:
            db.execute(
                "UPDATE tasks SET status = 'error', error_msg = '服务重启，任务被中断', "
                "updated_at = CURRENT_TIMESTAMP WHERE status IN ('running', 'pending')"
            )
            db.commit()
            logger.warning("Cleaned %d orphan tasks: %s",
                           len(rows), [f"{r['id'][:8]}({r['status']})" for r in rows])
    finally:
        db.close()


# ── 生命周期 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Initializing database...")
    init_db()
    logger.info("Initializing config & media dirs...")
    app_config.ensure_media_dirs()
    _cleanup_stale_chunks()
    _cleanup_orphan_tasks()
    logger.info("Starting ModelManager...")
    model_manager.start()
    logger.info("Bird Gallery Web API ready")

    yield

    # shutdown
    logger.info("Shutting down ModelManager...")
    model_manager.stop()

    # 关闭 ExifToolManager（如果已启动）
    try:
        from tools.exiftool_manager import get_exiftool_manager
        etm = get_exiftool_manager()
        etm.shutdown()
        logger.info("ExifToolManager shut down")
    except Exception as e:
        logger.warning("ExifToolManager shutdown error: %s", e)

    logger.info("Bird Gallery Web API stopped")


# ── FastAPI 实例 ──
app = FastAPI(
    title="Bird Gallery Web API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──
_env = os.environ.get("ENV", "production")
_cors_origins = []
if _env == "dev":
    _cors_origins.append("http://localhost:5173")
_ddns_domain = os.environ.get("DDNS_DOMAIN")
if _ddns_domain:
    _cors_origins.append(f"http://{_ddns_domain}")

if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── 认证中间件 ──
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """非 GET/HEAD/OPTIONS 请求需要 JWT 认证（登录接口除外）。"""
    from api.auth import verify_token, AUTH_EXEMPT_PATHS

    # 安全方法和豁免路径跳过认证
    if request.method in ("GET", "HEAD", "OPTIONS"):
        # GET 请求也尝试解析 token（供 /auth/me 使用）
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = verify_token(auth_header[7:])
            if payload:
                request.state.user = payload
        return await call_next(request)

    if request.url.path in AUTH_EXEMPT_PATHS:
        return await call_next(request)

    # 验证 JWT
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "未登录"})

    payload = verify_token(auth_header[7:])
    if not payload:
        return JSONResponse(status_code=401, content={"detail": "登录已过期，请重新登录"})

    request.state.user = payload
    return await call_next(request)


# ── 注册路由 ──
from api.auth import router as auth_router
from api.photos import router as photos_router
from api.tasks import router as tasks_router
from api.admin import router as admin_router
from api.upload import router as upload_router
from api.library import router as library_router
from api.birds import router as birds_router
from api.duplicates import router as duplicates_router
from api.videos import router as videos_router
from api.bursts import router as bursts_router
from api.batch_process import router as batch_process_router
from api.logs import router as logs_router
from api.identify import router as identify_router
from api.photo_edits import router as photo_edits_router

app.include_router(auth_router, prefix="/api")
app.include_router(photos_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(library_router, prefix="/api")
app.include_router(birds_router, prefix="/api")
app.include_router(duplicates_router, prefix="/api")
app.include_router(videos_router, prefix="/api")
app.include_router(bursts_router, prefix="/api")
app.include_router(batch_process_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(identify_router, prefix="/api")
app.include_router(photo_edits_router, prefix="/api")
