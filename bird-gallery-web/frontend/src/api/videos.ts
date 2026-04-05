import client from './client'
import type { Video, VideoFrame, BirdSegment, Task } from '@/types'

function mapVideo(raw: any): Video {
  return {
    id: raw.id,
    filename: raw.filename,
    original_path: raw.original_path,
    file_size: raw.file_size ?? 0,
    duration_seconds: raw.duration ?? null,
    width: raw.width ?? null,
    height: raw.height ?? null,
    fps: raw.fps ?? null,
    status: raw.status ?? 'uploaded',
    created_at: raw.imported_at,
  }
}

export const videoAPI = {
  list: (): Promise<Video[]> =>
    client.get('/videos').then((res: any) => (res.items ?? []).map(mapVideo)),

  get: (id: string): Promise<Video> => client.get(`/videos/${id}`).then(mapVideo),

  upload: (formData: FormData, onProgress?: (p: number, loaded: number) => void, signal?: AbortSignal): Promise<{ video_id: string }> =>
    client.post('/videos/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      signal,
      onUploadProgress: (e) => {
        if (!onProgress) return
        const total = e.total || e.estimated || 0
        const pct = total > 0 ? Math.round((e.loaded * 100) / total) : 0
        onProgress(pct, e.loaded)
      },
    }),

  streamUrl: (id: string) => `/api/videos/${id}/stream`,

  analyze: (id: string, strategy = 'interval'): Promise<Task> =>
    client.post(`/videos/${id}/analyze?strategy=${strategy}`),

  batchAnalyze: (): Promise<{ task_id: string; total: number }> =>
    client.post('/videos/batch-analyze'),

  frames: (id: string): Promise<{ frames: VideoFrame[] }> =>
    client.get(`/videos/${id}/frames`),

  timeline: (id: string): Promise<{ segments: BirdSegment[] }> =>
    client.get(`/videos/${id}/timeline`),

  highlights: (id: string): Promise<{ highlights: VideoFrame[] }> =>
    client.get(`/videos/${id}/highlights`),

  exportClip: (id: string, startTime: number, endTime: number): Promise<Blob> =>
    client.post(`/videos/${id}/export-clip`, null, {
      params: { start_time: startTime, end_time: endTime },
      responseType: 'blob',
    }),

  delete: (id: string) => client.delete(`/videos/${id}`),

  batchDelete: (ids: string[]) => client.post('/videos/batch-delete', { ids }),

  thumbnailUrl: (id: string) => `/api/videos/${id}/thumbnail`,
}
