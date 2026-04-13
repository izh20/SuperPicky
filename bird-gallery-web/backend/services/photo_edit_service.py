import hashlib
import json
import logging
import os
import shutil
import uuid

from app_config_pkg import config as app_config
from models.database import get_db_connection
from services.raw_develop_service import render_export_file, render_preview_file

logger = logging.getLogger(__name__)

RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2'}
DEFAULT_ENGINE = 'internal_linear_v1'
DEFAULT_ENGINE_VERSION = '1'
DEFAULT_PREVIEW_SIZE = 1600
DEFAULT_PREVIEW_QUALITY = 90

DEFAULT_PARAMS = {
    'exposure': 0.0,
    'contrast': 0,
    'highlights': 0,
    'shadows': 0,
    'whites': 0,
    'blacks': 0,
    'temperature': 6500,
    'tint': 0,
    'vibrance': 0,
    'saturation': 0,
}


def _json_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _json_loads(data: str | None) -> dict:
    if not data:
        return {}
    try:
        value = json.loads(data)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def params_hash(params: dict) -> str:
    return hashlib.sha256(_json_dumps(params).encode('utf-8')).hexdigest()


def normalize_params(params: dict | None) -> dict:
    merged = dict(DEFAULT_PARAMS)
    if not isinstance(params, dict):
        return merged
    for key in DEFAULT_PARAMS:
        if key in params and params[key] is not None:
            merged[key] = params[key]
    return merged


def default_params() -> dict:
    return dict(DEFAULT_PARAMS)


def is_raw_photo(filename: str | None) -> bool:
    if not filename:
        return False
    return os.path.splitext(filename)[1].lower() in RAW_EXTENSIONS


def draft_preview_url(photo_id: str, render_revision: int, preview_size: int = DEFAULT_PREVIEW_SIZE) -> str:
    return f'/api/photo-edits/{photo_id}/draft/preview?render_revision={render_revision}&preview_size={preview_size}'


def version_preview_url(photo_id: str, version_id: int, preview_size: int = DEFAULT_PREVIEW_SIZE) -> str:
    return f'/api/photo-edits/{photo_id}/versions/{version_id}/preview?preview_size={preview_size}'


def _draft_preview_path(photo_id: str, render_revision: int, preview_size: int) -> str:
    return os.path.join(
        app_config.photo_edit_drafts_dir(photo_id),
        f'draft_r{render_revision}_s{preview_size}.jpg',
    )


def _version_preview_path(photo_id: str, version_id: int, preview_size: int) -> str:
    return os.path.join(
        app_config.photo_edit_versions_dir(photo_id),
        f'version_{version_id}_s{preview_size}.jpg',
    )


def export_output_path(photo_id: str, version_id: int, export_format: str) -> str:
    return os.path.join(
        app_config.photo_edit_exports_dir(photo_id),
        f'version_{version_id}.{export_format.lower()}',
    )


def get_photo_row(db, photo_id: str):
    return db.execute(
        'SELECT id, filename, original_path FROM photos WHERE id = ?',
        (photo_id,),
    ).fetchone()


def _current_version_row(db, photo_id: str):
    return db.execute(
        'SELECT * FROM photo_edit_versions WHERE photo_id = ? AND is_current = 1',
        (photo_id,),
    ).fetchone()


def _latest_version_row(db, photo_id: str):
    return db.execute(
        'SELECT * FROM photo_edit_versions WHERE photo_id = ? ORDER BY version_no DESC LIMIT 1',
        (photo_id,),
    ).fetchone()


def _draft_row(db, photo_id: str):
    return db.execute(
        'SELECT * FROM photo_edit_drafts WHERE photo_id = ?',
        (photo_id,),
    ).fetchone()


def _version_row(db, photo_id: str, version_id: int):
    return db.execute(
        'SELECT * FROM photo_edit_versions WHERE photo_id = ? AND id = ?',
        (photo_id, version_id),
    ).fetchone()


def _next_version_no(db, photo_id: str) -> int:
    row = db.execute(
        'SELECT COALESCE(MAX(version_no), 0) AS max_version_no FROM photo_edit_versions WHERE photo_id = ?',
        (photo_id,),
    ).fetchone()
    return int(row['max_version_no']) + 1


def _params_from_row(row) -> dict:
    return normalize_params(_json_loads(row['params_json']))


def _ensure_version_preview(db, photo_row, version_row, preview_size: int = DEFAULT_PREVIEW_SIZE) -> str | None:
    version_id = int(version_row['id'])
    target_path = _version_preview_path(photo_row['id'], version_id, preview_size)
    if not os.path.exists(target_path):
        histogram = render_preview_file(
            photo_row['original_path'],
            _params_from_row(version_row),
            target_path,
            preview_size=preview_size,
            quality=DEFAULT_PREVIEW_QUALITY,
        )
        if preview_size == DEFAULT_PREVIEW_SIZE:
            db.execute(
                'UPDATE photo_edit_versions SET histogram_json = ? WHERE id = ?',
                (_json_dumps(histogram), version_id),
            )

    if preview_size == DEFAULT_PREVIEW_SIZE and version_row['preview_path'] != target_path:
        db.execute(
            'UPDATE photo_edit_versions SET preview_path = ?, render_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (target_path, 'ready', version_id),
        )
        db.commit()
    return target_path


def _ensure_draft_preview(db, photo_row, draft_row, preview_size: int = DEFAULT_PREVIEW_SIZE, quality: int = DEFAULT_PREVIEW_QUALITY) -> str | None:
    render_revision = int(draft_row['render_revision'])
    target_path = _draft_preview_path(photo_row['id'], render_revision, preview_size)
    if not os.path.exists(target_path):
        histogram = render_preview_file(
            photo_row['original_path'],
            _params_from_row(draft_row),
            target_path,
            preview_size=preview_size,
            quality=quality,
        )
        if preview_size == DEFAULT_PREVIEW_SIZE:
            db.execute(
                'UPDATE photo_edit_drafts SET histogram_json = ? WHERE id = ?',
                (_json_dumps(histogram), int(draft_row['id'])),
            )

    if preview_size == DEFAULT_PREVIEW_SIZE and draft_row['preview_path'] != target_path:
        db.execute(
            'UPDATE photo_edit_drafts SET preview_path = ?, render_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (target_path, 'ready', int(draft_row['id'])),
        )
        db.commit()
    return target_path


def _create_initial_version(db, photo_row):
    params = default_params()
    params_json = _json_dumps(params)
    current_engine = DEFAULT_ENGINE
    current_engine_version = DEFAULT_ENGINE_VERSION
    cursor = db.execute(
        '''
        INSERT INTO photo_edit_versions (
            photo_id, source_type, version_no, is_current, is_auto_tone,
            base_version_id, params_json, params_hash, render_status,
            preview_path, export_path, histogram_json, engine, engine_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            photo_row['id'],
            'raw' if is_raw_photo(photo_row['filename']) else 'image',
            1,
            1,
            0,
            None,
            params_json,
            params_hash(params),
            'ready',
            None,
            None,
            None,
            current_engine,
            current_engine_version,
        ),
    )
    db.commit()
    version_id = int(cursor.lastrowid)
    row = _version_row(db, photo_row['id'], version_id)
    _ensure_version_preview(db, photo_row, row)
    return _version_row(db, photo_row['id'], version_id)


def ensure_current_version(db, photo_row):
    row = _current_version_row(db, photo_row['id'])
    if row:
        _ensure_version_preview(db, photo_row, row)
        return _version_row(db, photo_row['id'], int(row['id']))

    latest = _latest_version_row(db, photo_row['id'])
    if latest:
        db.execute('UPDATE photo_edit_versions SET is_current = 0 WHERE photo_id = ?', (photo_row['id'],))
        db.execute(
            'UPDATE photo_edit_versions SET is_current = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (int(latest['id']),),
        )
        db.commit()
        latest = _version_row(db, photo_row['id'], int(latest['id']))
        _ensure_version_preview(db, photo_row, latest)
        return latest

    return _create_initial_version(db, photo_row)


def ensure_draft(db, photo_row, current_version_row):
    row = _draft_row(db, photo_row['id'])
    if row:
        _ensure_draft_preview(db, photo_row, row)
        return _draft_row(db, photo_row['id'])

    params_json = current_version_row['params_json']
    cursor = db.execute(
        '''
        INSERT INTO photo_edit_drafts (
            photo_id, base_version_id, params_json, params_hash,
            render_revision, preview_path, histogram_json, render_status,
            last_task_id, engine, engine_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            photo_row['id'],
            int(current_version_row['id']),
            params_json,
            current_version_row['params_hash'],
            0,
            None,
            None,
            'ready',
            None,
            current_version_row['engine'],
            current_version_row['engine_version'],
        ),
    )
    db.commit()
    draft_id = int(cursor.lastrowid)
    row = db.execute('SELECT * FROM photo_edit_drafts WHERE id = ?', (draft_id,)).fetchone()
    _ensure_draft_preview(db, photo_row, row)
    return _draft_row(db, photo_row['id'])


def ensure_state(db, photo_id: str):
    photo_row = get_photo_row(db, photo_id)
    if not photo_row:
        raise ValueError('photo_not_found')
    current_version = ensure_current_version(db, photo_row)
    current_draft = ensure_draft(db, photo_row, current_version)
    return photo_row, current_version, current_draft


def _build_auto_tone_params(db, photo_id: str) -> dict:
    params = default_params()
    score_row = db.execute(
        'SELECT rating, head_sharp, nima_score, exposure_status FROM photo_scores WHERE photo_id = ?',
        (photo_id,),
    ).fetchone()
    params.update({
        'contrast': 8,
        'highlights': -18,
        'shadows': 20,
        'vibrance': 12,
        'saturation': 4,
    })
    if not score_row:
        return params

    exposure_status = (score_row['exposure_status'] or '').lower()
    if 'under' in exposure_status or '欠曝' in exposure_status:
        params['exposure'] = 0.35
        params['shadows'] = 28
        params['blacks'] = 6
    elif 'over' in exposure_status or '过曝' in exposure_status:
        params['exposure'] = -0.3
        params['highlights'] = -35
        params['whites'] = -10

    rating = score_row['rating'] or 0
    if rating >= 4:
        params['contrast'] = 10
        params['vibrance'] = 14

    return params


def apply_auto_tone(db, photo_id: str, engine: str = 'internal_v1', base_version_id: int | None = None):
    photo_row, current_version, existing_draft = ensure_state(db, photo_id)
    target_version = current_version
    if base_version_id is not None:
        requested_version = _version_row(db, photo_id, base_version_id)
        if requested_version:
            target_version = requested_version

    new_params = _build_auto_tone_params(db, photo_id)
    new_hash = params_hash(new_params)
    next_revision = int(existing_draft['render_revision']) + 1
    db.execute(
        '''
        UPDATE photo_edit_drafts
        SET base_version_id = ?, params_json = ?, params_hash = ?, render_revision = ?,
            preview_path = NULL, histogram_json = NULL, render_status = ?, last_task_id = NULL,
            engine = ?, engine_version = ?, updated_at = CURRENT_TIMESTAMP
        WHERE photo_id = ?
        ''',
        (
            int(target_version['id']),
            _json_dumps(new_params),
            new_hash,
            next_revision,
            'idle',
            engine,
            DEFAULT_ENGINE_VERSION,
            photo_id,
        ),
    )
    db.commit()
    return photo_row, _draft_row(db, photo_id)


def update_draft_params(db, photo_id: str, patch_params: dict):
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    current_params = normalize_params(_json_loads(draft_row['params_json']))
    merged = normalize_params({**current_params, **(patch_params or {})})
    if merged == current_params:
        return photo_row, draft_row

    next_revision = int(draft_row['render_revision']) + 1
    db.execute(
        '''
        UPDATE photo_edit_drafts
        SET params_json = ?, params_hash = ?, render_revision = ?, preview_path = NULL,
            histogram_json = NULL, render_status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE photo_id = ?
        ''',
        (
            _json_dumps(merged),
            params_hash(merged),
            next_revision,
            'idle',
            photo_id,
        ),
    )
    db.commit()
    return photo_row, _draft_row(db, photo_id)


def render_draft_preview(db, photo_id: str, preview_size: int = DEFAULT_PREVIEW_SIZE, quality: int = DEFAULT_PREVIEW_QUALITY, force_recompute: bool = False):
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    if force_recompute:
        next_revision = int(draft_row['render_revision']) + 1
        db.execute(
            'UPDATE photo_edit_drafts SET render_revision = ?, preview_path = NULL, render_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (next_revision, 'idle', int(draft_row['id'])),
        )
        db.commit()
        draft_row = _draft_row(db, photo_id)

    preview_path = _ensure_draft_preview(db, photo_row, draft_row, preview_size=preview_size, quality=quality)
    draft_row = _draft_row(db, photo_id)
    return draft_row, preview_path


def commit_draft(db, photo_id: str, set_current: bool = True):
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    if set_current:
        db.execute('UPDATE photo_edit_versions SET is_current = 0 WHERE photo_id = ?', (photo_id,))

    next_version_no = _next_version_no(db, photo_id)
    cursor = db.execute(
        '''
        INSERT INTO photo_edit_versions (
            photo_id, source_type, version_no, is_current, is_auto_tone,
            base_version_id, params_json, params_hash, render_status,
            preview_path, export_path, histogram_json, engine, engine_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            photo_id,
            'raw' if is_raw_photo(photo_row['filename']) else 'image',
            next_version_no,
            1 if set_current else 0,
            1 if (draft_row['engine'] or '').startswith('internal') else 0,
            int(draft_row['base_version_id']) if draft_row['base_version_id'] else int(current_version['id']),
            draft_row['params_json'],
            draft_row['params_hash'],
            'ready',
            None,
            None,
            draft_row['histogram_json'],
            draft_row['engine'],
            draft_row['engine_version'],
        ),
    )
    db.commit()
    version_id = int(cursor.lastrowid)
    version_row = _version_row(db, photo_id, version_id)
    version_preview = _ensure_version_preview(db, photo_row, version_row)

    if not draft_row['preview_path'] or not os.path.exists(draft_row['preview_path']):
        draft_preview_path = _draft_preview_path(photo_id, int(draft_row['render_revision']), DEFAULT_PREVIEW_SIZE)
        if version_preview:
            shutil.copyfile(version_preview, draft_preview_path)
            db.execute(
                'UPDATE photo_edit_drafts SET preview_path = ?, histogram_json = ?, render_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (draft_preview_path, version_row['histogram_json'], 'ready', int(draft_row['id'])),
            )

    db.execute(
        'UPDATE photo_edit_drafts SET base_version_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (version_id, int(draft_row['id'])),
    )
    db.commit()
    return _version_row(db, photo_id, version_id)


def discard_draft_changes(db, photo_id: str):
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    current_params = normalize_params(_json_loads(current_version['params_json']))
    next_revision = int(draft_row['render_revision']) + 1
    draft_preview_path = _draft_preview_path(photo_id, next_revision, DEFAULT_PREVIEW_SIZE)
    version_preview = _ensure_version_preview(db, photo_row, current_version)
    preview_path = None
    if version_preview:
        shutil.copyfile(version_preview, draft_preview_path)
        preview_path = draft_preview_path

    db.execute(
        '''
        UPDATE photo_edit_drafts
        SET base_version_id = ?, params_json = ?, params_hash = ?, render_revision = ?,
            preview_path = ?, histogram_json = ?, render_status = ?, last_task_id = NULL,
            engine = ?, engine_version = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''',
        (
            int(current_version['id']),
            _json_dumps(current_params),
            current_version['params_hash'],
            next_revision,
            preview_path,
            current_version['histogram_json'],
            'ready' if preview_path else 'idle',
            current_version['engine'],
            current_version['engine_version'],
            int(draft_row['id']),
        ),
    )
    db.commit()
    return _draft_row(db, photo_id)


def activate_version(db, photo_id: str, version_id: int):
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    version_row = _version_row(db, photo_id, version_id)
    if not version_row:
        raise ValueError('version_not_found')

    db.execute('UPDATE photo_edit_versions SET is_current = 0 WHERE photo_id = ?', (photo_id,))
    db.execute(
        'UPDATE photo_edit_versions SET is_current = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (version_id,),
    )
    db.commit()

    refreshed_version = _version_row(db, photo_id, version_id)
    _ensure_version_preview(db, photo_row, refreshed_version)
    reset_draft = discard_draft_changes(db, photo_id)
    return refreshed_version, reset_draft


def serialize_version_summary(photo_id: str, row) -> dict:
    return {
        'version_id': int(row['id']),
        'version_no': int(row['version_no']),
        'is_current': bool(row['is_current']),
        'is_auto_tone': bool(row['is_auto_tone']),
        'preview_url': version_preview_url(photo_id, int(row['id'])),
        'engine': row['engine'],
        'engine_version': row['engine_version'],
        'created_at': row['created_at'],
    }


def get_photo_edit_state(db, photo_id: str) -> dict:
    photo_row, current_version, current_draft = ensure_state(db, photo_id)
    versions = db.execute(
        'SELECT * FROM photo_edit_versions WHERE photo_id = ? ORDER BY version_no DESC',
        (photo_id,),
    ).fetchall()
    return {
        'photo_id': photo_id,
        'is_raw': is_raw_photo(photo_row['filename']),
        'has_auto_tone_result': any(bool(row['is_auto_tone']) for row in versions),
        'current_version': {
            'version_id': int(current_version['id']),
            'version_no': int(current_version['version_no']),
            'preview_url': version_preview_url(photo_id, int(current_version['id'])),
            'is_auto_tone': bool(current_version['is_auto_tone']),
            'engine': current_version['engine'],
            'engine_version': current_version['engine_version'],
        },
        'current_draft': {
            'draft_id': int(current_draft['id']),
            'base_version_id': int(current_draft['base_version_id']) if current_draft['base_version_id'] else None,
            'params_json': normalize_params(_json_loads(current_draft['params_json'])),
            'params_hash': current_draft['params_hash'],
            'render_revision': int(current_draft['render_revision']),
            'render_status': current_draft['render_status'],
            'preview_url': draft_preview_url(photo_id, int(current_draft['render_revision'])),
            'last_task_id': current_draft['last_task_id'],
            'engine': current_draft['engine'],
            'engine_version': current_draft['engine_version'],
        },
        'versions': [serialize_version_summary(photo_id, row) for row in versions],
    }


def get_draft_preview_file(db, photo_id: str, render_revision: int, preview_size: int = DEFAULT_PREVIEW_SIZE) -> str | None:
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    if int(draft_row['render_revision']) != int(render_revision):
        return None
    return _ensure_draft_preview(db, photo_row, draft_row, preview_size=preview_size)


def get_version_preview_file(db, photo_id: str, version_id: int, preview_size: int = DEFAULT_PREVIEW_SIZE) -> str | None:
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    version_row = _version_row(db, photo_id, version_id)
    if not version_row:
        return None
    return _ensure_version_preview(db, photo_row, version_row, preview_size=preview_size)


def get_version_export_file(db, photo_id: str, version_id: int, export_format: str | None = None) -> str | None:
    photo_row, current_version, draft_row = ensure_state(db, photo_id)
    version_row = _version_row(db, photo_id, version_id)
    if not version_row:
        return None

    if export_format:
        normalized_format = export_format.lower()
        if normalized_format == 'jpg':
            normalized_format = 'jpeg'
        if normalized_format == 'tif':
            normalized_format = 'tiff'
        candidate = export_output_path(photo_id, version_id, normalized_format)
        if os.path.exists(candidate):
            return candidate

    export_path = version_row['export_path']
    if export_path and os.path.exists(export_path):
        return export_path
    return None


def _run_export_task(task_id: str, photo_id: str, version_id: int, export_format: str, quality: int, write_xmp: bool):
    db = get_db_connection()
    try:
        db.execute(
            "UPDATE tasks SET status = 'running', progress = 10, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        version_row = _version_row(db, photo_id, version_id)
        if not version_row:
            raise ValueError('version_not_found')

        db.execute(
            "UPDATE tasks SET progress = 60, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        db.commit()

        export_path = export_output_path(photo_id, version_id, export_format)
        histogram = render_export_file(
            get_photo_row(db, photo_id)['original_path'],
            _params_from_row(version_row),
            export_path,
            export_format,
            quality=quality,
        )

        db.execute(
            'UPDATE photo_edit_versions SET export_path = ?, histogram_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (export_path, _json_dumps(histogram), version_id),
        )
        db.execute(
            "UPDATE tasks SET status = 'done', progress = 100, result_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (
                json.dumps({
                    'photo_id': photo_id,
                    'version_id': version_id,
                    'export_path': export_path,
                    'write_xmp_applied': False if write_xmp else False,
                }, ensure_ascii=False),
                task_id,
            ),
        )
        db.commit()
    except Exception as exc:
        logger.exception('photo edit export failed: %s', exc)
        db.execute(
            "UPDATE tasks SET status = 'error', error_msg = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(exc), task_id),
        )
        db.commit()
    finally:
        db.close()


def queue_export_task(db, background_tasks, photo_id: str, version_id: int, export_format: str, quality: int, write_xmp: bool) -> str:
    export_format = export_format.lower()
    if export_format not in {'jpeg', 'jpg', 'png', 'tiff', 'tif'}:
        raise ValueError('unsupported_format')
    version_row = _version_row(db, photo_id, version_id)
    if not version_row:
        raise ValueError('version_not_found')
    task_id = str(uuid.uuid4())
    db.execute(
        'INSERT INTO tasks (id, type, status, progress, config_json) VALUES (?, ?, ?, ?, ?)',
        (
            task_id,
            'photo_edit_export',
            'pending',
            0,
            json.dumps({
                'photo_id': photo_id,
                'version_id': version_id,
                'format': export_format,
                'quality': quality,
                'write_xmp': write_xmp,
            }, ensure_ascii=False),
        ),
    )
    db.commit()
    background_tasks.add_task(
        _run_export_task,
        task_id,
        photo_id,
        version_id,
        export_format,
        quality,
        write_xmp,
    )
    return task_id