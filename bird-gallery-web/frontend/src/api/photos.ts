import client from './client'
import type { PhotoListResponse, PhotoDetail, PhotoFilters, Task } from '@/types'

function mapPhotoDetail(raw: any): PhotoDetail {
  const meta = raw?.metadata ?? {}
  const score = raw?.score ?? null
  return {
    id: raw.id,
    filename: raw.filename,
    original_path: raw.original_path,
    file_size: raw.file_size,
    width: raw.width,
    height: raw.height,
    created_at: raw.imported_at,
    exif_make: meta.camera_make,
    exif_model: meta.camera_model,
    exif_datetime: meta.date_taken,
    exif_iso: meta.iso,
    exif_aperture: meta.aperture,
    exif_shutter_speed: meta.shutter_speed,
    exif_focal_length: meta.focal_length,
    exif_gps_lat: meta.gps_lat,
    exif_gps_lon: meta.gps_lon,
    birds: raw.birds ?? [],
    score,
  }
}

export const photoAPI = {
  filterOptions: (confidenceMin?: number): Promise<{ species: string[]; cameras: string[]; dates: string[] }> =>
    client.get('/photos/filter-options', { params: confidenceMin != null ? { confidence_min: confidenceMin } : undefined }),

  list: (filters: PhotoFilters = {}): Promise<PhotoListResponse> =>
    client.get('/photos', { params: filters }),

  get: (id: string): Promise<PhotoDetail> =>
    client.get(`/photos/${id}`).then(mapPhotoDetail),

  upload: (formData: FormData, onProgress?: (p: number, loaded: number) => void, signal?: AbortSignal): Promise<{ photo_id: string }> =>
    client.post('/photos/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      signal,
      onUploadProgress: (e) => {
        if (!onProgress) return
        const total = e.total || e.estimated || 0
        const pct = total > 0 ? Math.round((e.loaded * 100) / total) : 0
        onProgress(pct, e.loaded)
      },
    }),

  uploadFolder: (formData: FormData): Promise<{ uploaded: number; failed: number; items: any[]; errors: any[] }> =>
    client.post('/photos/upload-folder', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  // 缩略图 URL（直接构造）
  thumbnailUrl: (id: string, size: 'sm' | 'md' | 'lg' = 'md') =>
    `/api/photos/${id}/thumbnail?size=${size}`,

  originalUrl: (id: string) => `/api/photos/${id}/original`,

  recognize: (id: string): Promise<{ photo_id: string; birds: any[]; scores: any | null }> =>
    client.post(`/photos/${id}/recognize`),

  batchRecognize: (photoIds: string[]): Promise<Task> =>
    client.post('/photos/batch-recognize', { photo_ids: photoIds }),

  delete: (id: string): Promise<{ deleted: boolean }> =>
    client.delete(`/photos/${id}`),

  batchDelete: (photoIds: string[]): Promise<{ deleted: number; ids: string[] }> =>
    client.post('/photos/batch-delete', { photo_ids: photoIds }),

  findDuplicates: (): Promise<{ groups: any[]; total_groups: number }> =>
    client.post('/photos/find-duplicates'),

  getDuplicateGroup: (groupId: string): Promise<{ group_id: string; photos: any[] }> =>
    client.get(`/photos/groups/${groupId}`),

  keepDuplicate: (groupId: string, photoId: string): Promise<{ kept: string; others: string[] }> =>
    client.post(`/photos/groups/${groupId}/keep/${photoId}`),

  deleteDuplicate: (groupId: string, photoId: string): Promise<{ deleted: string; group_id: string; remaining: number }> =>
    client.delete(`/photos/groups/${groupId}/photo/${photoId}`),

  writeExifTitle: (id: string, text: string): Promise<{ written: boolean; title: string }> =>
    client.post(`/photos/${id}/exif/write-title`, { text }),

  writeExifCaption: (id: string, text: string): Promise<{ written: boolean; caption: string }> =>
    client.post(`/photos/${id}/exif/write-caption`, { text }),

  detectBursts: (threshold = 0.25, minCount = 4): Promise<Task> =>
    client.post('/photos/detect-bursts', null, {
      params: { burst_time_threshold: threshold, burst_min_count: minCount },
    }),

  recognizeAll: (): Promise<{ id: string; task_id: string; total: number }> =>
    client.post('/photos/recognize-all'),

  ratingConfig: (): Promise<{
    config: Record<string, number>;
    defaults: Record<string, number>;
    rules: Array<{ key: string; label: string; desc: string; unit: string; min: number; max: number; step: number }>;
    scoring_logic: string[];
  }> => client.get('/photos/rating-config'),

  updateRatingConfig: (data: Record<string, number>): Promise<{ config: Record<string, number> }> =>
    client.put('/photos/rating-config', data),

  resetRatingConfig: (): Promise<{ config: Record<string, number> }> =>
    client.post('/photos/rating-config/reset'),

  recalculateRatings: (): Promise<{ id: string; task_id: string; total: number }> =>
    client.post('/photos/recalculate-ratings'),

  rescore: (): Promise<{ id: string; task_id: string; total: number }> =>
    client.post('/photos/rescore'),

  resetRecognition: (): Promise<{ deleted_birds: number; deleted_scores: number }> =>
    client.post('/photos/reset-recognition'),
}
