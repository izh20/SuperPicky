"""管理 API — 健康检查 + 系统指标 + 任务管理 + 系统配置"""

import os
import json
import uuid
import psutil
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from models.database import get_db
from models.schemas import (
    AdminTaskListResponse,
    AdminTaskSummary,
    HealthResponse,
    MetricsResponse,
    ModelStatus,
)
from services.model_manager import model_manager
from api.auth import require_admin
from app_config_pkg import config as app_config

router = APIRouter(tags=["admin"])

_RETRYABLE_TASK_TYPES = {
    "analyze",
    "batch-analyze",
    "recognize_all",
    "recognize",
    "rescore",
    "recalculate",
    "scan",
    "detect_bursts",
}


@router.get("/admin/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@router.get("/admin/metrics", response_model=MetricsResponse, dependencies=[Depends(require_admin)])
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


def _parse_json_blob(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _is_interrupted_task(data: dict) -> bool:
    if data.get("status") == "cancelled":
        return True
    if data.get("status") != "error":
        return False
    err = str(data.get("error_msg") or "")
    return "服务重启" in err or "任务被中断" in err


def _can_retry_task(task_type: str, config: dict | None, data: dict) -> bool:
    if not _is_interrupted_task(data):
        return False
    if task_type not in _RETRYABLE_TASK_TYPES:
        return False
    if task_type in ("recognize_all", "rescore", "recalculate", "detect_bursts"):
        return True
    if task_type == "scan":
        return bool(config and config.get("path"))
    if task_type == "recognize":
        return bool(config and isinstance(config.get("photo_ids"), list) and config.get("photo_ids"))
    if task_type == "analyze":
        return bool(config and config.get("video_id"))
    if task_type == "batch-analyze":
        return bool(config and isinstance(config.get("video_ids"), list) and config.get("video_ids"))
    return False


def _build_task_summary(row, db) -> AdminTaskSummary:
    data = dict(row)
    payload = _parse_json_blob(data.get("result_json"))
    config = _parse_json_blob(data.get("config_json"))
    target_id = None
    target_name = None
    detail = None

    task_type = data.get("type")
    status = data.get("status")

    if task_type in ("recognize_all", "recognize_all_bursts", "recognize") and isinstance(payload, dict):
        processed = payload.get("processed")
        total = payload.get("total")
        if isinstance(processed, int) and isinstance(total, int) and total > 0:
            detail = f"已处理 {processed}/{total}"
    elif task_type == "batch_process":
        if isinstance(payload, dict):
            total = payload.get("total")
            completed = payload.get("completed")
            failed = payload.get("failed")
            if isinstance(total, int):
                detail = f"完成 {completed or 0}/{total}，失败 {failed or 0}"
        if isinstance(config, dict):
            output_format = config.get("output_format")
            min_rating = config.get("min_rating")
            if output_format:
                suffix = f"输出 {str(output_format).upper()}"
                detail = f"{detail}，{suffix}" if detail else suffix
            if min_rating is not None:
                prefix = f"最低评分 {min_rating} 星"
                detail = f"{prefix}，{detail}" if detail else prefix
    elif task_type == "scan":
        if isinstance(payload, dict):
            imported = payload.get("imported")
            skipped = payload.get("skipped")
            if imported is not None or skipped is not None:
                detail = f"导入 {imported or 0}，跳过 {skipped or 0}"
        if isinstance(config, dict) and config.get("path"):
            target_name = str(config["path"])
    elif task_type in ("analyze", "batch-analyze"):
        if isinstance(config, dict):
            if config.get("video_id"):
                target_id = str(config["video_id"])
            if config.get("filename"):
                target_name = str(config["filename"])
            strategy = config.get("strategy")
            interval = config.get("interval")
            parts = []
            if strategy:
                parts.append(f"策略 {strategy}")
            if interval:
                parts.append(f"间隔 {interval}s")
            if parts:
                detail = "，".join(parts)
            if task_type == "batch-analyze" and not detail and config.get("total"):
                detail = f"共 {config['total']} 个视频"
        if task_type == "analyze" and not target_name and status in ("pending", "running"):
            active_video = db.execute(
                "SELECT id, filename FROM videos WHERE status IN ('analyzing', 'transcoding') "
                "ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if active_video:
                target_id = active_video["id"]
                target_name = active_video["filename"]
    elif task_type == "scan" and isinstance(config, dict):
        target_name = config.get("path")
        detail = "递归扫描" if config.get("recursive", True) else "仅当前目录"
    elif task_type == "detect_bursts" and isinstance(config, dict):
        detail = f"阈值 {config.get('burst_time_threshold', 2.0)}s，最少 {config.get('burst_min_count', 3)} 张"
    elif task_type == "recognize" and isinstance(config, dict) and isinstance(config.get("photo_ids"), list):
        detail = f"共 {len(config['photo_ids'])} 张照片"

    return AdminTaskSummary(
        id=data["id"],
        type=data["type"],
        status=data["status"],
        progress=data.get("progress") or 0,
        result_json=data.get("result_json"),
        error_msg=data.get("error_msg"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        target_id=target_id,
        target_name=target_name,
        detail=detail,
        can_cancel=data["status"] in ("pending", "running"),
        can_retry=_can_retry_task(task_type, config if isinstance(config, dict) else None, data),
    )


def _enqueue_retry_task(task_row, background_tasks: BackgroundTasks, db):
    from api.photos import _batch_recognize_task, _recalculate_ratings_task, _rescore_task
    from api.library import _scan_task
    from api.bursts import _detect_bursts_task
    from api.videos import _analyze_task, _batch_analyze_task

    data = dict(task_row)
    task_type = data["type"]
    config = _parse_json_blob(data.get("config_json")) or {}

    if task_type == "recognize_all":
        rows = db.execute(
            """SELECT p.id FROM photos p
               LEFT JOIN photo_scores ps ON ps.photo_id = p.id
               WHERE ps.photo_id IS NULL AND p.filename NOT LIKE '%.thumbnails_%'"""
        ).fetchall()
        photo_ids = [r["id"] for r in rows]
        if not photo_ids:
            return None, 0
        new_task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status) VALUES (?, 'recognize_all', 'pending')",
            (new_task_id,),
        )
        db.commit()
        background_tasks.add_task(_batch_recognize_task, new_task_id, photo_ids)
        return new_task_id, len(photo_ids)

    if task_type == "recognize":
        photo_ids = config.get("photo_ids") if isinstance(config.get("photo_ids"), list) else []
        if not photo_ids:
            raise HTTPException(400, "该任务缺少可重试的照片上下文")
        new_task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'recognize', 'pending', ?)",
            (new_task_id, json.dumps({"photo_ids": photo_ids}, ensure_ascii=False)),
        )
        db.commit()
        background_tasks.add_task(_batch_recognize_task, new_task_id, photo_ids)
        return new_task_id, len(photo_ids)

    if task_type == "rescore":
        rows = db.execute(
            """SELECT ps.photo_id, p.original_path, pb.detection_box
               FROM photo_scores ps
               JOIN photos p ON p.id = ps.photo_id
               JOIN photo_birds pb ON pb.photo_id = ps.photo_id AND pb.rank = 1
               WHERE ps.rating != -1
                 AND (ps.head_sharp = 0 OR ps.head_sharp IS NULL)
                 AND (ps.nima_score IS NULL)"""
        ).fetchall()
        if not rows:
            return None, 0
        rescore_data = [
            {"photo_id": r["photo_id"], "image_path": r["original_path"], "detection_box": r["detection_box"]}
            for r in rows
        ]
        new_task_id = str(uuid.uuid4())
        db.execute("INSERT INTO tasks (id, type, status) VALUES (?, 'rescore', 'pending')", (new_task_id,))
        db.commit()
        background_tasks.add_task(_rescore_task, new_task_id, rescore_data)
        return new_task_id, len(rescore_data)

    if task_type == "recalculate":
        rows = db.execute(
            """SELECT ps.photo_id, ps.head_sharp, ps.nima_score, pm.iso
               FROM photo_scores ps
               LEFT JOIN photo_metadata pm ON pm.photo_id = ps.photo_id
               WHERE ps.rating != -1"""
        ).fetchall()
        if not rows:
            return None, 0
        score_data = [
            {"photo_id": r["photo_id"], "head_sharp": r["head_sharp"], "nima_score": r["nima_score"], "iso": r["iso"]}
            for r in rows
        ]
        new_task_id = str(uuid.uuid4())
        db.execute("INSERT INTO tasks (id, type, status) VALUES (?, 'recalculate', 'pending')", (new_task_id,))
        db.commit()
        background_tasks.add_task(_recalculate_ratings_task, new_task_id, score_data)
        return new_task_id, len(score_data)

    if task_type == "scan":
        scan_path = config.get("path")
        recursive = bool(config.get("recursive", True))
        if not scan_path:
            raise HTTPException(400, "该扫描任务缺少路径信息")
        new_task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'scan', 'pending', ?)",
            (new_task_id, json.dumps({"path": scan_path, "recursive": recursive}, ensure_ascii=False)),
        )
        db.commit()
        background_tasks.add_task(_scan_task, new_task_id, scan_path, recursive)
        return new_task_id, None

    if task_type == "detect_bursts":
        threshold = float(config.get("burst_time_threshold", 2.0))
        min_count = int(config.get("burst_min_count", 3))
        new_task_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'detect_bursts', 'pending', ?)",
            (new_task_id, json.dumps({"burst_time_threshold": threshold, "burst_min_count": min_count}, ensure_ascii=False)),
        )
        db.commit()
        background_tasks.add_task(_detect_bursts_task, new_task_id, threshold, min_count)
        return new_task_id, None

    if task_type == "analyze":
        video_id = config.get("video_id")
        strategy = config.get("strategy", "interval")
        interval = int(config.get("interval", 10))
        filename = config.get("filename")
        if not video_id:
            raise HTTPException(400, "该视频任务缺少 video_id，无法自动重试")
        new_task_id = str(uuid.uuid4())
        new_config = json.dumps({
            "video_id": video_id,
            "filename": filename,
            "strategy": strategy,
            "interval": interval,
        })
        db.execute(
            "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'analyze', 'pending', ?)",
            (new_task_id, new_config),
        )
        db.commit()
        background_tasks.add_task(_analyze_task, new_task_id, video_id, strategy, interval)
        return new_task_id, 1

    if task_type == "batch-analyze":
        strategy = config.get("strategy", "interval")
        interval = int(config.get("interval", 10))
        video_ids = config.get("video_ids") if isinstance(config.get("video_ids"), list) else None
        if not video_ids:
            raise HTTPException(400, "该批量视频任务缺少视频列表，无法自动重试")
        new_task_id = str(uuid.uuid4())
        new_config = json.dumps({
            "strategy": strategy,
            "interval": interval,
            "total": len(video_ids),
            "video_ids": video_ids,
        })
        db.execute(
            "INSERT INTO tasks (id, type, status, config_json) VALUES (?, 'batch-analyze', 'pending', ?)",
            (new_task_id, new_config),
        )
        db.commit()
        background_tasks.add_task(_batch_analyze_task, new_task_id, video_ids, strategy, interval)
        return new_task_id, len(video_ids)

    raise HTTPException(400, f"任务类型 {task_type} 暂不支持重试")


@router.get("/admin/tasks", response_model=AdminTaskListResponse, dependencies=[Depends(require_admin)])
async def list_admin_tasks(limit: int = Query(20, ge=1, le=100), db=Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM tasks "
        "ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, "
        "updated_at DESC, created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    running = db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
    queued = db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
    return AdminTaskListResponse(
        items=[_build_task_summary(row, db) for row in rows],
        running=running,
        queued=queued,
    )


@router.post("/admin/tasks/{task_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_admin_task(task_id: str, db=Depends(get_db)):
    row = db.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    if row["status"] not in ("pending", "running"):
        return {"message": "Task already finished"}
    db.execute(
        "UPDATE tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (task_id,),
    )
    db.commit()
    return {"message": "Task cancelled"}


@router.post("/admin/tasks/{task_id}/retry", dependencies=[Depends(require_admin)])
async def retry_admin_task(task_id: str, background_tasks: BackgroundTasks, db=Depends(get_db)):
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    if not _build_task_summary(row, db).can_retry:
        raise HTTPException(400, "该任务当前不可重试")
    new_task_id, total = _enqueue_retry_task(row, background_tasks, db)
    return {"message": "Task retried", "task_id": new_task_id, "total": total}


@router.post("/admin/release-models", dependencies=[Depends(require_admin)])
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
