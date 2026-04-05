import client from './client'
import type { UploadSession } from '@/types'

export const uploadAPI = {
  init: (filename: string, fileSize: number, fileType: 'photo' | 'video' = 'photo'): Promise<UploadSession> =>
    client.post('/upload/init', null, {
      params: { filename, file_size: fileSize, file_type: fileType },
    }),

  uploadChunk: (
    uploadId: string,
    chunkIndex: number,
    data: Blob,
    onProgress?: (p: number) => void,
    signal?: AbortSignal,
  ): Promise<{ chunk_index: number; received: number }> => {
    const form = new FormData()
    form.append('file', data)
    return client.post(`/upload/${uploadId}/chunk`, form, {
      params: { index: chunkIndex },
      headers: { 'Content-Type': 'multipart/form-data' },
      signal,
      onUploadProgress: (e) => {
        if (!onProgress) return
        const total = e.total || e.estimated || 0
        onProgress(total > 0 ? Math.round((e.loaded * 100) / total) : 0)
      },
    })
  },

  status: (uploadId: string): Promise<UploadSession> =>
    client.get(`/upload/${uploadId}/status`),

  complete: (uploadId: string, sha256?: string): Promise<{ photo_id?: string; video_id?: string }> =>
    client.post(`/upload/${uploadId}/complete`, null, {
      params: sha256 ? { expected_sha256: sha256 } : undefined,
    }),
}
