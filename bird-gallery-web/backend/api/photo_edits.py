import json
import os
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from models.database import get_db
from models.schemas import (
    PhotoEditActivateResponse,
    PhotoEditAutoToneRequest,
    PhotoEditCommitRequest,
    PhotoEditCommitResponse,
    PhotoEditDiscardResponse,
    PhotoEditDraftMutationResponse,
    PhotoEditExportQueuedResponse,
    PhotoEditExportRequest,
    PhotoEditPatchDraftRequest,
    PhotoEditRenderPreviewRequest,
    PhotoEditRenderPreviewResponse,
    PhotoEditStateResponse,
)
from services.photo_edit_service import (
    DEFAULT_PREVIEW_SIZE,
    apply_auto_tone,
    activate_version,
    commit_draft,
    discard_draft_changes,
    draft_preview_url,
    get_draft_preview_file,
    get_photo_edit_state,
    get_version_export_file,
    get_version_preview_file,
    queue_export_task,
    render_draft_preview,
    update_draft_params,
    version_preview_url,
)

router = APIRouter(tags=['photo-edits'])


@router.get('/photo-edits/{photo_id}', response_model=PhotoEditStateResponse)
async def get_photo_edit(photo_id: str, db=Depends(get_db)):
    try:
        return PhotoEditStateResponse(**get_photo_edit_state(db, photo_id))
    except ValueError:
        raise HTTPException(404, 'Photo not found')


@router.post('/photo-edits/{photo_id}/draft/auto-tone', response_model=PhotoEditDraftMutationResponse)
async def auto_tone_draft(photo_id: str, req: PhotoEditAutoToneRequest, db=Depends(get_db)):
    try:
        _, draft_row = apply_auto_tone(
            db,
            photo_id,
            engine=req.engine,
            base_version_id=req.base_version_id,
        )
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    return PhotoEditDraftMutationResponse(
        draft_id=int(draft_row['id']),
        params_json=get_photo_edit_state(db, photo_id)['current_draft']['params_json'],
        params_hash=draft_row['params_hash'],
        render_revision=int(draft_row['render_revision']),
        draft_updated_at=draft_row['updated_at'],
    )


@router.patch('/photo-edits/{photo_id}/draft', response_model=PhotoEditDraftMutationResponse)
async def patch_draft(photo_id: str, req: PhotoEditPatchDraftRequest, db=Depends(get_db)):
    try:
        _, draft_row = update_draft_params(db, photo_id, req.params)
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    return PhotoEditDraftMutationResponse(
        draft_id=int(draft_row['id']),
        params_json=get_photo_edit_state(db, photo_id)['current_draft']['params_json'],
        params_hash=draft_row['params_hash'],
        render_revision=int(draft_row['render_revision']),
        draft_updated_at=draft_row['updated_at'],
    )


@router.post('/photo-edits/{photo_id}/draft/commit', response_model=PhotoEditCommitResponse)
async def commit_photo_edit_draft(photo_id: str, req: PhotoEditCommitRequest, db=Depends(get_db)):
    try:
        version_row = commit_draft(db, photo_id, set_current=req.set_current)
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    return PhotoEditCommitResponse(
        version_id=int(version_row['id']),
        version_no=int(version_row['version_no']),
        version_preview_url=version_preview_url(photo_id, int(version_row['id'])),
        current_version_changed=bool(req.set_current),
        draft_rebased=True,
    )


@router.post('/photo-edits/{photo_id}/draft/render-preview', response_model=PhotoEditRenderPreviewResponse)
async def render_preview(photo_id: str, req: PhotoEditRenderPreviewRequest, db=Depends(get_db)):
    started = time.time()
    try:
        draft_row, preview_path = render_draft_preview(
            db,
            photo_id,
            preview_size=req.preview_size,
            quality=req.quality,
            force_recompute=req.force_recompute,
        )
    except ValueError:
        raise HTTPException(404, 'Photo not found')

    return PhotoEditRenderPreviewResponse(
        status='ready',
        preview_url=draft_preview_url(photo_id, int(draft_row['render_revision']), req.preview_size) if preview_path else None,
        histogram=json.loads(draft_row['histogram_json']) if draft_row['histogram_json'] else None,
        task_id=None,
        render_mode='sync',
        render_time_ms=int((time.time() - started) * 1000),
        render_revision=int(draft_row['render_revision']),
    )


@router.get('/photo-edits/{photo_id}/draft/preview')
async def get_draft_preview(photo_id: str, render_revision: int = Query(..., ge=0), preview_size: int = Query(DEFAULT_PREVIEW_SIZE, ge=200, le=4000), db=Depends(get_db)):
    try:
        preview_path = get_draft_preview_file(db, photo_id, render_revision, preview_size=preview_size)
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    if not preview_path:
        raise HTTPException(404, 'Draft preview not found')
    return FileResponse(preview_path, media_type='image/jpeg')


@router.get('/photo-edits/{photo_id}/versions/{version_id}/preview')
async def get_saved_version_preview(photo_id: str, version_id: int, preview_size: int = Query(DEFAULT_PREVIEW_SIZE, ge=200, le=4000), db=Depends(get_db)):
    try:
        preview_path = get_version_preview_file(db, photo_id, version_id, preview_size=preview_size)
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    if not preview_path:
        raise HTTPException(404, 'Version preview not found')
    return FileResponse(preview_path, media_type='image/jpeg')


@router.post('/photo-edits/{photo_id}/draft/discard', response_model=PhotoEditDiscardResponse)
async def discard_draft(photo_id: str, db=Depends(get_db)):
    try:
        draft_row = discard_draft_changes(db, photo_id)
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    state = get_photo_edit_state(db, photo_id)
    return PhotoEditDiscardResponse(
        draft_id=int(draft_row['id']),
        base_version_id=int(draft_row['base_version_id']) if draft_row['base_version_id'] else None,
        params_json=state['current_draft']['params_json'],
        render_revision=int(draft_row['render_revision']),
        preview_url=state['current_draft']['preview_url'],
    )


@router.post('/photo-edits/{photo_id}/versions/{version_id}/activate', response_model=PhotoEditActivateResponse)
async def activate_saved_version(photo_id: str, version_id: int, db=Depends(get_db)):
    try:
        version_row, draft_row = activate_version(db, photo_id, version_id)
    except ValueError as exc:
        if str(exc) == 'version_not_found':
            raise HTTPException(404, 'Version not found')
        raise HTTPException(404, 'Photo not found')
    return PhotoEditActivateResponse(
        current_version_id=int(version_row['id']),
        current_version_preview_url=version_preview_url(photo_id, int(version_row['id'])),
        draft_id=int(draft_row['id']),
        draft_reset=True,
    )


@router.post('/photo-edits/{photo_id}/versions/{version_id}/export', response_model=PhotoEditExportQueuedResponse)
async def export_saved_version(photo_id: str, version_id: int, req: PhotoEditExportRequest, background_tasks: BackgroundTasks, db=Depends(get_db)):
    try:
        task_id = queue_export_task(
            db,
            background_tasks,
            photo_id,
            version_id,
            req.format,
            req.quality,
            req.write_xmp,
        )
    except ValueError as exc:
        if str(exc) == 'unsupported_format':
            raise HTTPException(400, 'Unsupported export format')
        raise HTTPException(404, 'Version not found')
    return PhotoEditExportQueuedResponse(task_id=task_id, status='pending')


@router.get('/photo-edits/{photo_id}/versions/{version_id}/exported-file')
async def get_saved_version_export_file(photo_id: str, version_id: int, format: str | None = Query(None), db=Depends(get_db)):
    try:
        export_path = get_version_export_file(db, photo_id, version_id, export_format=format)
    except ValueError:
        raise HTTPException(404, 'Photo not found')
    if not export_path:
        raise HTTPException(404, 'Export file not found')

    ext = os.path.splitext(export_path)[1].lower()
    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.tif': 'image/tiff',
        '.tiff': 'image/tiff',
    }
    download_name = os.path.basename(export_path)
    return FileResponse(export_path, media_type=media_types.get(ext, 'application/octet-stream'), filename=download_name)