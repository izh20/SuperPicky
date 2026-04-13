import client from './client'

export interface IdentifyResult {
  species_cn: string
  species_en: string
  scientific_name: string
  confidence: number
  rank: number
}

export interface IdentifyResponse {
  success: boolean
  birds: IdentifyResult[]
  detection_box: number[] | null
}

export const identifyAPI = {
  recognize: (file: File): Promise<IdentifyResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/identify', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    })
  },
}
