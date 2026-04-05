import client from './client'
import type { BurstGroup, Task } from '@/types'

export const burstAPI = {
  list: (): Promise<BurstGroup[]> => client.get('/bursts'),

  get: (id: string): Promise<BurstGroup & { photos: any[] }> =>
    client.get(`/bursts/${id}`),

  getBest: (id: string): Promise<any> =>
    client.get(`/bursts/${id}/best`),

  recognize: (id: string): Promise<Task> =>
    client.post(`/bursts/${id}/recognize`),

  synthesize: (id: string, framerate = 20, resolution = '1920x1080'): Promise<Task> =>
    client.post(`/bursts/${id}/synthesize`, { framerate, resolution }),

  videoUrl: (id: string) => `/api/bursts/${id}/video`,
}
