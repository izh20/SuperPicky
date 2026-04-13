"""
统一配置管理器

- media_dir: 媒体文件存储根目录（照片、视频、缩略图等）
- scan_roots: 扫描白名单目录
- 配置持久化到 config.json（与 gallery.db 同目录）
- 热重载：修改后立即生效，无需重启
"""

import json
import os
import threading
import logging

logger = logging.getLogger(__name__)

# 系统固定目录：数据库 + 配置文件所在的目录（不随 media_dir 迁移）
_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_CONFIG_PATH = os.path.join(_APP_DIR, 'config.json')


def _default_media_dir() -> str:
    return _APP_DIR


_lock = threading.Lock()
_config: dict | None = None


def _load() -> dict:
    """从磁盘加载配置，不存在则生成默认值。"""
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {}
    # 确保必要字段有默认值
    data.setdefault('media_dir', _default_media_dir())
    data.setdefault('scan_roots', [])
    return data


def _save(data: dict):
    """原子写入配置文件。"""
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    tmp = _CONFIG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _CONFIG_PATH)


def _get() -> dict:
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                _config = _load()
    return _config


def get_media_dir() -> str:
    """返回当前媒体存储根目录。"""
    return _get()['media_dir']


def get_scan_roots() -> list[str]:
    """返回扫描白名单根目录列表。"""
    return list(_get().get('scan_roots', []))


def get_all() -> dict:
    """返回所有配置项的副本。"""
    return dict(_get())


def update(updates: dict):
    """更新配置项并持久化。线程安全。"""
    with _lock:
        global _config
        cfg = _load()  # 从磁盘重新读取，防止覆盖并发写入
        cfg.update(updates)
        _save(cfg)
        _config = cfg
    logger.info("Config updated: %s", list(updates.keys()))


# ── 便捷路径函数（替代原来散落各处的 _DATA_DIR 拼接）──

def photos_upload_dir() -> str:
    d = os.path.join(get_media_dir(), 'uploads', 'photos')
    os.makedirs(d, exist_ok=True)
    return d


def videos_original_dir() -> str:
    d = os.path.join(get_media_dir(), 'videos', 'original')
    os.makedirs(d, exist_ok=True)
    return d


def videos_transcoded_dir() -> str:
    d = os.path.join(get_media_dir(), 'videos', 'transcoded')
    os.makedirs(d, exist_ok=True)
    return d


def videos_thumbnails_dir() -> str:
    d = os.path.join(get_media_dir(), 'videos', 'thumbnails')
    os.makedirs(d, exist_ok=True)
    return d


def videos_clips_dir() -> str:
    d = os.path.join(get_media_dir(), 'videos', 'clips')
    os.makedirs(d, exist_ok=True)
    return d


def frames_dir(video_id: str | None = None) -> str:
    if video_id:
        d = os.path.join(get_media_dir(), 'frames', video_id)
    else:
        d = os.path.join(get_media_dir(), 'frames')
    os.makedirs(d, exist_ok=True)
    return d


def thumbnails_dir(photo_id: str | None = None) -> str:
    if photo_id:
        d = os.path.join(get_media_dir(), 'thumbnails', photo_id)
    else:
        d = os.path.join(get_media_dir(), 'thumbnails')
    os.makedirs(d, exist_ok=True)
    return d


def chunks_dir(upload_id: str | None = None) -> str:
    if upload_id:
        d = os.path.join(get_media_dir(), 'uploads', 'chunks', upload_id)
    else:
        d = os.path.join(get_media_dir(), 'uploads', 'chunks')
    os.makedirs(d, exist_ok=True)
    return d


def gallery_by_bird_dir() -> str:
    d = os.path.join(get_media_dir(), 'gallery', 'by_bird')
    os.makedirs(d, exist_ok=True)
    return d


def burst_video_dir() -> str:
    d = os.path.join(get_media_dir(), 'videos', 'burst')
    os.makedirs(d, exist_ok=True)
    return d


def exports_dir(task_id: str | None = None) -> str:
    if task_id:
        d = os.path.join(get_media_dir(), 'exports', task_id)
    else:
        d = os.path.join(get_media_dir(), 'exports')
    os.makedirs(d, exist_ok=True)
    return d


def watermarks_dir() -> str:
    d = os.path.join(get_media_dir(), 'watermarks')
    os.makedirs(d, exist_ok=True)
    return d


def photo_edit_dir(photo_id: str | None = None) -> str:
    if photo_id:
        d = os.path.join(get_media_dir(), 'photo_edits', photo_id)
    else:
        d = os.path.join(get_media_dir(), 'photo_edits')
    os.makedirs(d, exist_ok=True)
    return d


def photo_edit_versions_dir(photo_id: str) -> str:
    d = os.path.join(photo_edit_dir(photo_id), 'versions')
    os.makedirs(d, exist_ok=True)
    return d


def photo_edit_drafts_dir(photo_id: str) -> str:
    d = os.path.join(photo_edit_dir(photo_id), 'drafts')
    os.makedirs(d, exist_ok=True)
    return d


def photo_edit_exports_dir(photo_id: str) -> str:
    d = os.path.join(photo_edit_dir(photo_id), 'exports')
    os.makedirs(d, exist_ok=True)
    return d


def ensure_media_dirs():
    """启动时确保所有必要子目录存在。"""
    get_media_dir()
    photos_upload_dir()
    videos_original_dir()
    videos_transcoded_dir()
    videos_thumbnails_dir()
    thumbnails_dir()
    chunks_dir()
    exports_dir()
    watermarks_dir()
    photo_edit_dir()
