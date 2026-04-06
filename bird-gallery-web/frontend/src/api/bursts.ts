import client from './client'
import type { BurstGroup, Task } from '@/types'

export interface BurstFilters {
  species?: string
  camera?: string
  rating_min?: number
  min_photos?: number
  has_flying?: boolean
  flying_min_count?: number
}

export const burstAPI = {
  list: (filters?: BurstFilters): Promise<{ total: number; groups: BurstGroup[] }> =>
    client.get('/bursts', { params: { page_size: 10000, ...filters } }),

  get: (id: string): Promise<BurstGroup & { photos: any[] }> =>
    client.get(`/bursts/${id}`),

  getBest: (id: string): Promise<any> =>
    client.get(`/bursts/${id}/best`),

  recognize: (id: string): Promise<Task> =>
    client.post(`/bursts/${id}/recognize`),

  recognizeAll: (): Promise<{ id: string; task_id: string; total: number }> =>
    client.post('/bursts/recognize-all'),

  synthesize: (id: string, framerate = 20, resolution = '1920x1080'): Promise<Task> =>
    client.post(`/bursts/${id}/synthesize`, { framerate, resolution }),

  videoUrl: (id: string) => `/api/bursts/${id}/video`,

  filterOptions: (confidenceMin = 70): Promise<{ species: string[]; cameras: string[] }> =>
    client.get('/bursts/filter-options', { params: { confidence_min: confidenceMin } }),

  batchDelete: (groupIds: string[]): Promise<{ deleted_groups: number; deleted_photos: number }> =>
    client.post('/bursts/batch-delete', { group_ids: groupIds }),
}
