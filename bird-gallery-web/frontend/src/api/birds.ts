import client from './client'
import type { BirdSpecies, PhotoListResponse, Task } from '@/types'

export const birdAPI = {
  list: (): Promise<BirdSpecies[]> => client.get('/birds'),

  photos: (species: string, page = 1, pageSize = 50): Promise<PhotoListResponse> =>
    client.get(`/birds/${encodeURIComponent(species)}/photos`, {
      params: { page, page_size: pageSize },
    }).then((res: any) => ({ ...res, items: res.photos ?? res.items ?? [] })),

  stats: (species: string): Promise<any> =>
    client.get(`/birds/${encodeURIComponent(species)}/stats`),

  organize: (): Promise<Task> => client.post('/birds/organize'),
}
