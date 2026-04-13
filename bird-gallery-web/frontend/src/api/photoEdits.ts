import client from './client'
import type { PhotoEditParams, PhotoEditRenderPreviewResponse, PhotoEditState } from '@/types'

interface DraftMutationResponse {
  draft_id: number
  params_json: PhotoEditParams
  params_hash?: string | null
  render_revision: number
  draft_updated_at?: string | null
}

interface CommitResponse {
  version_id: number
  version_no: number
  version_preview_url?: string | null
  current_version_changed: boolean
  draft_rebased: boolean
}

interface DiscardResponse {
  draft_id: number
  base_version_id?: number | null
  params_json: PhotoEditParams
  render_revision: number
  preview_url?: string | null
}

interface ActivateResponse {
  current_version_id: number
  current_version_preview_url?: string | null
  draft_id: number
  draft_reset: boolean
}

interface ExportQueuedResponse {
  task_id: string
  status: string
}

type ExportFormat = 'jpeg' | 'jpg' | 'png' | 'tiff' | 'tif'

export const photoEditAPI = {
  getState: (photoId: string): Promise<PhotoEditState> =>
    client.get(`/photo-edits/${photoId}`),

  autoTone: (photoId: string, baseVersionId?: number): Promise<DraftMutationResponse> =>
    client.post(`/photo-edits/${photoId}/draft/auto-tone`, {
      base_version_id: baseVersionId ?? null,
    }),

  patchDraft: (photoId: string, params: Partial<PhotoEditParams>): Promise<DraftMutationResponse> =>
    client.patch(`/photo-edits/${photoId}/draft`, { params }),

  renderPreview: (photoId: string, options?: { preview_size?: number; quality?: number; force_recompute?: boolean }): Promise<PhotoEditRenderPreviewResponse> =>
    client.post(`/photo-edits/${photoId}/draft/render-preview`, {
      preview_size: options?.preview_size ?? 1600,
      quality: options?.quality ?? 90,
      force_recompute: options?.force_recompute ?? false,
    }),

  commitDraft: (photoId: string, setCurrent = true): Promise<CommitResponse> =>
    client.post(`/photo-edits/${photoId}/draft/commit`, {
      set_current: setCurrent,
    }),

  discardDraft: (photoId: string): Promise<DiscardResponse> =>
    client.post(`/photo-edits/${photoId}/draft/discard`),

  activateVersion: (photoId: string, versionId: number): Promise<ActivateResponse> =>
    client.post(`/photo-edits/${photoId}/versions/${versionId}/activate`),

  exportVersion: (
    photoId: string,
    versionId: number,
    format: ExportFormat,
    options?: { quality?: number; write_xmp?: boolean },
  ): Promise<ExportQueuedResponse> =>
    client.post(`/photo-edits/${photoId}/versions/${versionId}/export`, {
      format,
      quality: options?.quality ?? (format === 'jpeg' || format === 'jpg' ? 92 : 95),
      write_xmp: options?.write_xmp ?? true,
    }),

  exportDownloadUrl: (photoId: string, versionId: number, format?: ExportFormat): string => {
    const params = new URLSearchParams()
    if (format) params.set('format', format)
    const query = params.toString()
    return `/api/photo-edits/${photoId}/versions/${versionId}/exported-file${query ? `?${query}` : ''}`
  },
}