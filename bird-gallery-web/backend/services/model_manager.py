"""
AI 模型生命周期管理器

按需加载 + 空闲超时自动释放（TTL 5 分钟）。
释放时调用 torch.mps.empty_cache() + gc.collect() 归还统一内存。
通过 threading.Event 支持优雅退出。
"""

import time
import threading
import gc
import logging
import os

logger = logging.getLogger(__name__)

# TTL 可通过环境变量覆盖（单位：分钟）
_TTL_MINUTES = int(os.environ.get("MODEL_TTL_MINUTES", "5"))


class ModelManager:
    """模型按需加载 + 空闲超时释放"""

    TTL_SECONDS = _TTL_MINUTES * 60

    def __init__(self):
        self._models: dict = {}           # name → model instance
        self._last_used: dict = {}        # name → timestamp
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cleanup_thread: threading.Thread | None = None

    def start(self):
        """启动清理线程。必须在 FastAPI startup 中调用。"""
        if self._cleanup_thread is not None:
            return
        self._stop_event.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="model-cleanup"
        )
        self._cleanup_thread.start()
        logger.info("ModelManager cleanup thread started (TTL=%ds)", self.TTL_SECONDS)

    def stop(self):
        """优雅停止清理线程并释放所有模型。FastAPI shutdown 中调用。"""
        self._stop_event.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None
        self._release_all()
        logger.info("ModelManager stopped, all models released")

    def get(self, name: str, loader_fn):
        """获取模型实例，未加载则调用 loader_fn 按需加载。"""
        with self._lock:
            if name not in self._models:
                logger.info("Loading model: %s", name)
                t0 = time.time()
                self._models[name] = loader_fn()
                logger.info("Model %s loaded in %.1fs", name, time.time() - t0)
            self._last_used[name] = time.time()
            return self._models[name]

    def is_loaded(self, name: str) -> bool:
        with self._lock:
            return name in self._models

    def get_status(self) -> dict:
        """返回所有模型状态，供 /api/admin/metrics 使用。"""
        # 检查 birdid 通过 LazyRegistry 加载的模型（yolo、osea）
        birdid_loaded = {}
        try:
            from config import get_lazy_registry
            registry = get_lazy_registry()
            birdid_loaded["yolo"] = registry.get("birdid.yolo_detector") is not None
            birdid_loaded["osea"] = registry.get("birdid.classifier") is not None
        except Exception:
            pass

        with self._lock:
            status = {}
            for name in ("yolo", "topiq", "keypoint", "osea"):
                managed_loaded = name in self._models
                external_loaded = birdid_loaded.get(name, False)
                is_loaded = managed_loaded or external_loaded

                if is_loaded:
                    status[name] = {
                        "loaded": True,
                        "last_used": time.strftime(
                            "%Y-%m-%dT%H:%M:%S",
                            time.localtime(self._last_used.get(name, 0)),
                        ) if self._last_used.get(name) else None,
                    }
                else:
                    last = self._last_used.get(name)
                    status[name] = {
                        "loaded": False,
                        "last_used": (
                            time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(last))
                            if last
                            else None
                        ),
                    }
            return status

    def release(self, name: str):
        """手动释放指定模型。"""
        with self._lock:
            self._release_model(name)

    def release_all(self):
        """手动释放所有已加载模型。"""
        self._release_all()

    # ── internal ──

    def _cleanup_loop(self):
        """每 60 秒检查一次，释放超过 TTL 的模型。"""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=60)
            if self._stop_event.is_set():
                break
            self._cleanup()

    def _cleanup(self):
        now = time.time()
        with self._lock:
            # OOM 保护：系统可用内存 < 2GB 时强制释放所有模型
            if self._check_low_memory():
                names = list(self._models.keys())
                if names:
                    logger.warning("Low memory detected (<2GB free), releasing all models: %s", names)
                    for name in names:
                        self._release_model(name)
                    self._empty_cache()
                return

            expired = [
                k
                for k, t in self._last_used.items()
                if k in self._models and now - t > self.TTL_SECONDS
            ]
            for name in expired:
                self._release_model(name)
            if expired:
                self._empty_cache()
                logger.info("Cleaned up expired models: %s", expired)

    def _release_model(self, name: str):
        """在 _lock 持有状态下释放单个模型。"""
        if name in self._models:
            del self._models[name]
            logger.info("Released model: %s", name)

    @staticmethod
    def _check_low_memory(threshold_gb: float = 2.0) -> bool:
        """检查系统可用内存是否低于阈值。"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            return available_gb < threshold_gb
        except ImportError:
            return False

    def _release_all(self):
        with self._lock:
            names = list(self._models.keys())
            for name in names:
                self._release_model(name)
            if names:
                self._empty_cache()

    @staticmethod
    def _empty_cache():
        try:
            import torch
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass
        gc.collect()


# 全局单例
model_manager = ModelManager()
