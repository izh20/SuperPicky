import client from './client'
import type {
  BatchProcessConfig,
  BatchProcessStartResponse,
  BatchProcessResultsResponse,
  BatchProcessOptions,
} from '@/types'

export async function getOptions(): Promise<BatchProcessOptions> {
  return client.get('/batch-process/options')
}

export async function startBatchProcess(
  config: BatchProcessConfig,
): Promise<BatchProcessStartResponse> {
  return client.post('/batch-process/start', config)
}

export async function getResults(
  taskId: string,
): Promise<BatchProcessResultsResponse> {
  return client.get(`/batch-process/${taskId}/results`)
}

export async function previewCrop(
  photoId: string,
  cropConfig: Record<string, unknown>,
): Promise<Blob> {
  const res = await client.post(
    '/batch-process/preview-crop',
    { photo_id: photoId, crop_config: cropConfig },
    { responseType: 'blob', transformResponse: [(data: Blob) => data] },
  )
  return res as unknown as Blob
}

export async function previewWatermark(
  photoId: string,
  layers: Record<string, unknown>[],
): Promise<Blob> {
  const res = await client.post(
    '/batch-process/preview-watermark',
    { photo_id: photoId, watermark_layers: layers },
    { responseType: 'blob', transformResponse: [(data: Blob) => data] },
  )
  return res as unknown as Blob
}
