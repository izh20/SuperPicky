"""
SQLite 数据库连接池 + Schema 初始化

规则：
- WAL 模式，支持并发读
- 每请求通过 get_db() 依赖注入获取独立连接
- BackgroundTasks 中禁止共享连接，需独立调用 get_db_connection()
"""

import sqlite3
import os
import hashlib
import hmac
import secrets
import threading
import logging

_logger = logging.getLogger(__name__)

# gallery.db 存放路径
_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'database')
_DB_PATH = os.path.join(_DB_DIR, 'gallery.db')

_init_lock = threading.Lock()
_initialized = False

SCHEMA_SQL = """
-- 照片索引
CREATE TABLE IF NOT EXISTS photos (
    id           TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    filename     TEXT NOT NULL,
    file_hash    TEXT,
    width        INTEGER,
    height       INTEGER,
    file_size    INTEGER,
    imported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- EXIF 元数据
CREATE TABLE IF NOT EXISTS photo_metadata (
    photo_id     TEXT PRIMARY KEY REFERENCES photos(id),
    camera_make  TEXT, camera_model TEXT, lens_model TEXT,
    iso          INTEGER, shutter_speed TEXT, aperture REAL,
    focal_length REAL, focal_length_35mm REAL,
    gps_lat      REAL, gps_lon REAL, gps_altitude REAL,
    date_taken   DATETIME, timezone TEXT
);

-- 鸟类识别结果（一张照片可有多只鸟，多个候选）
CREATE TABLE IF NOT EXISTS photo_birds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        TEXT REFERENCES photos(id),
    species_cn      TEXT, species_en TEXT, scientific_name TEXT,
    confidence      REAL, rank INTEGER,
    detection_box   TEXT
);

-- 评分数据
CREATE TABLE IF NOT EXISTS photo_scores (
    photo_id     TEXT PRIMARY KEY REFERENCES photos(id),
    rating       INTEGER,
    head_sharp   REAL,
    nima_score   REAL,
    is_flying    INTEGER,
    focus_status TEXT,
    exposure_status TEXT,
    keypoints_json TEXT
);

-- 视频
CREATE TABLE IF NOT EXISTS videos (
    id           TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    filename     TEXT,
    duration     REAL,
    fps          REAL,
    frame_count  INTEGER,
    status       TEXT DEFAULT 'pending',
    imported_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 视频帧分析结果
CREATE TABLE IF NOT EXISTS video_frames (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     TEXT REFERENCES videos(id),
    frame_number INTEGER,
    timestamp    REAL,
    bird_detected INTEGER,
    species_cn   TEXT, species_en TEXT,
    confidence   REAL,
    detection_box TEXT,
    frame_path   TEXT
);

-- 视频鸟种出现时段汇总
CREATE TABLE IF NOT EXISTS video_bird_segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     TEXT REFERENCES videos(id),
    species_cn   TEXT, species_en TEXT,
    start_time   REAL,
    end_time     REAL,
    max_confidence REAL,
    best_frame_number INTEGER,
    best_frame_path   TEXT
);

-- 连拍组
CREATE TABLE IF NOT EXISTS burst_groups (
    id              TEXT PRIMARY KEY,
    photo_count     INTEGER,
    best_photo_id   TEXT REFERENCES photos(id),
    avg_rating      REAL,
    species_cn      TEXT, species_en TEXT,
    max_confidence  REAL,
    video_path      TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 连拍组-照片关联
CREATE TABLE IF NOT EXISTS burst_group_photos (
    group_id     TEXT REFERENCES burst_groups(id),
    photo_id     TEXT REFERENCES photos(id),
    position     INTEGER,
    PRIMARY KEY (group_id, photo_id)
);

-- 用户标签
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS photo_tags (
    photo_id TEXT REFERENCES photos(id),
    tag_id   INTEGER REFERENCES tags(id),
    PRIMARY KEY (photo_id, tag_id)
);

-- 去重分组
CREATE TABLE IF NOT EXISTS duplicate_groups (
    group_id   TEXT NOT NULL,
    photo_id   TEXT REFERENCES photos(id),
    hash_type  TEXT,
    similarity REAL,
    PRIMARY KEY (group_id, photo_id)
);

-- 分块上传会话追踪
CREATE TABLE IF NOT EXISTS upload_sessions (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    file_size       INTEGER,
    chunk_count     INTEGER,
    chunk_size      INTEGER DEFAULT 10485760,
    status          TEXT DEFAULT 'uploading',
    uploaded_chunks TEXT,
    file_hash       TEXT,
    file_type       TEXT,
    error_msg       TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 异步任务
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    progress    INTEGER DEFAULT 0,
    result_json TEXT,
    error_msg   TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 用户
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 批处理任务逐张跟踪
CREATE TABLE IF NOT EXISTS batch_process_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    photo_id        TEXT NOT NULL,
    phase           TEXT DEFAULT 'pending',
    denoise_output  TEXT,
    tone_output     TEXT,
    final_output    TEXT,
    error_msg       TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    UNIQUE(task_id, photo_id)
);

-- 最终处理成品
CREATE TABLE IF NOT EXISTS processed_photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    crop_preset     TEXT,
    watermark_preset TEXT,
    config_json     TEXT,
    width           INTEGER,
    height          INTEGER,
    file_size       INTEGER,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS photo_edit_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'raw',
    version_no      INTEGER NOT NULL,
    is_current      INTEGER NOT NULL DEFAULT 0,
    is_auto_tone    INTEGER NOT NULL DEFAULT 0,
    base_version_id INTEGER,
    params_json     TEXT NOT NULL,
    params_hash     TEXT NOT NULL,
    render_status   TEXT NOT NULL DEFAULT 'ready',
    preview_path    TEXT,
    export_path     TEXT,
    histogram_json  TEXT,
    engine          TEXT,
    engine_version  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    FOREIGN KEY (base_version_id) REFERENCES photo_edit_versions(id),
    UNIQUE(photo_id, version_no)
);

CREATE TABLE IF NOT EXISTS photo_edit_drafts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        TEXT NOT NULL UNIQUE,
    base_version_id INTEGER,
    params_json     TEXT NOT NULL,
    params_hash     TEXT NOT NULL,
    render_revision INTEGER NOT NULL DEFAULT 0,
    preview_path    TEXT,
    histogram_json  TEXT,
    render_status   TEXT NOT NULL DEFAULT 'idle',
    last_task_id    TEXT,
    engine          TEXT,
    engine_version  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    FOREIGN KEY (base_version_id) REFERENCES photo_edit_versions(id),
    FOREIGN KEY (last_task_id) REFERENCES tasks(id)
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_photos_hash ON photos(file_hash);
CREATE INDEX IF NOT EXISTS idx_metadata_camera ON photo_metadata(camera_model);
CREATE INDEX IF NOT EXISTS idx_metadata_lens ON photo_metadata(lens_model);
CREATE INDEX IF NOT EXISTS idx_metadata_date ON photo_metadata(date_taken);
CREATE INDEX IF NOT EXISTS idx_scores_rating ON photo_scores(rating);
CREATE INDEX IF NOT EXISTS idx_photo_birds_photo ON photo_birds(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_birds_species_cn ON photo_birds(species_cn);
CREATE INDEX IF NOT EXISTS idx_photo_birds_species_en ON photo_birds(species_en);
CREATE INDEX IF NOT EXISTS idx_video_frames_video ON video_frames(video_id);
CREATE INDEX IF NOT EXISTS idx_video_frames_species ON video_frames(species_cn);
CREATE INDEX IF NOT EXISTS idx_video_bird_segments_video ON video_bird_segments(video_id);
CREATE INDEX IF NOT EXISTS idx_burst_groups_created ON burst_groups(created_at);
CREATE INDEX IF NOT EXISTS idx_burst_group_photos_group ON burst_group_photos(group_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_duplicate_groups_hash ON duplicate_groups(hash_type);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_status ON upload_sessions(status);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_created ON upload_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_bpi_task_id ON batch_process_items(task_id);
CREATE INDEX IF NOT EXISTS idx_bpi_photo_id ON batch_process_items(photo_id);
CREATE INDEX IF NOT EXISTS idx_pp_task_id ON processed_photos(task_id);
CREATE INDEX IF NOT EXISTS idx_pp_photo_id ON processed_photos(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_edit_versions_photo_id ON photo_edit_versions(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_edit_drafts_photo_id ON photo_edit_drafts(photo_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_photo_edit_current
ON photo_edit_versions(photo_id, is_current)
WHERE is_current = 1;
"""


def _ensure_db_dir():
    os.makedirs(_DB_DIR, exist_ok=True)


def get_db_connection() -> sqlite3.Connection:
    """创建一个新的 SQLite 连接（WAL 模式，外键启用）。

    每个调用方持有独立连接，用完需 close()。
    BackgroundTasks 中应直接调用此函数获取独立连接。
    """
    _ensure_db_dir()
    conn = sqlite3.connect(_DB_PATH, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def init_db():
    """初始化数据库 schema（幂等，仅首次执行建表）。"""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = get_db_connection()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.executescript(INDEX_SQL)
            # 迁移：给已有 users 表增加 role 列
            _migrate_add_role_column(conn)
            _migrate_add_keypoints_column(conn)
            _migrate_add_config_json_column(conn)
            conn.commit()
            _ensure_admin_user(conn)
        finally:
            conn.close()
        _initialized = True


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """PBKDF2-SHA256 密码哈希，返回 (hex_hash, salt)。"""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    ).hex()
    return hashed, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """验证密码。"""
    check, _ = _hash_password(password, salt)
    return hmac.compare_digest(check, password_hash)


def _migrate_add_role_column(conn: sqlite3.Connection):
    """迁移：给已有 users 表增加 role 列（幂等）。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        # 将已有的 admin 用户提升为管理员
        conn.execute("UPDATE users SET role = 'admin' WHERE username = 'admin'")
        _logger.info("已迁移 users 表：添加 role 列")


def _migrate_add_keypoints_column(conn: sqlite3.Connection):
    """迁移：给已有 photo_scores 表增加 keypoints_json 列（幂等）。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(photo_scores)").fetchall()]
    if "keypoints_json" not in cols:
        conn.execute("ALTER TABLE photo_scores ADD COLUMN keypoints_json TEXT")
        _logger.info("已迁移 photo_scores 表：添加 keypoints_json 列")


def _migrate_add_config_json_column(conn: sqlite3.Connection):
    """迁移：给已有 tasks 表增加 config_json 列（幂等）。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    if "config_json" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN config_json TEXT")
        _logger.info("已迁移 tasks 表：添加 config_json 列")


def _ensure_admin_user(conn: sqlite3.Connection):
    """如果没有任何用户，创建默认管理员账户。"""
    row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    if row[0] > 0:
        return
    import uuid
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
    password_hash, salt = _hash_password(admin_password)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, salt, role) VALUES (?, ?, ?, ?, 'admin')",
        (str(uuid.uuid4()), "admin", password_hash, salt),
    )
    conn.commit()
    if admin_password == "admin":
        _logger.warning(
            "默认管理员账户已创建 (admin/admin)，请尽快通过 ADMIN_PASSWORD 环境变量或修改密码接口更改密码"
        )
    else:
        _logger.info("管理员账户已创建 (admin)")


def get_db():
    """FastAPI 依赖注入用的生成器。

    用法：
        def my_endpoint(db = Depends(get_db)):
            db.execute(...)
    """
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
