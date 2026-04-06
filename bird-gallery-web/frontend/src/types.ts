// 共享类型定义

export interface Photo {
  id: string
  filename: string
  original_path: string
  file_size: number
  width: number | null
  height: number | null
  created_at: string

  // EXIF
  exif_make?: string
  exif_model?: string
  exif_datetime?: string
  exif_iso?: number
  exif_aperture?: number
  exif_shutter_speed?: string
  exif_focal_length?: number
  exif_gps_lat?: number
  exif_gps_lon?: number

  // 识别结果（嵌入 DetailView 时展开）
  birds?: BirdResult[]
  score?: PhotoScore
}

export interface PhotoListItem {
  id: string
  filename: string
  file_size: number
  created_at: string
  exif_datetime?: string
  species_cn?: string
  species_en?: string
  rating?: number
  confidence?: number
  head_sharp?: number
  nima_score?: number
}

export interface PhotoListResponse {
  total: number
  page: number
  page_size: number
  items: PhotoListItem[]
}

export interface BirdResult {
  rank: number
  species_cn: string
  species_en: string
  scientific_name: string
  confidence: number
  detection_box?: number[] | null
}

export interface PhotoScore {
  rating: number | null
  head_sharp?: number | null
  nima_score?: number | null
}

export interface PhotoDetail extends Photo {
  birds: BirdResult[]
  score: PhotoScore
}

// 视频
export interface Video {
  id: string
  filename: string
  original_path: string
  file_size: number
  duration_seconds: number | null
  width: number | null
  height: number | null
  fps: number | null
  status: 'uploaded' | 'transcoding' | 'ready' | 'analyzing' | 'done' | 'error'
  created_at: string
}

export interface VideoFrame {
  id: string
  video_id: string
  frame_index: number
  timestamp_sec: number
  file_path: string
  sharpness?: number
  birds?: BirdResult[]
}

export interface BirdSegment {
  species_cn: string
  species_en?: string
  start_seconds: number
  end_seconds: number
  max_confidence: number
}

// 连拍
export interface BurstGroup {
  id: string
  photo_count: number
  best_photo_id: string | null
  first_shot_at: string | null
  species_cn?: string
  created_at: string
}

// 鸟种
export interface BirdSpecies {
  species_cn: string
  species_en: string
  scientific_name: string
  photo_count: number
  max_confidence: number
}

// 任务
export interface Task {
  id: string
  type: string
  status: 'pending' | 'running' | 'done' | 'error' | 'cancelled'
  progress: number
  result_json: string | null
  error_msg: string | null
  created_at: string
  updated_at: string | null
}

// 系统
export interface SystemMetrics {
  memory: {
    system_total_gb: number
    system_used_gb: number
    app_used_gb: number
  }
  models: Record<string, {
    loaded: boolean
    memory_mb?: number | null
    last_used: string | null
  }>
  tasks: {
    running: number
    queued: number
  }
}

export interface DashboardStats {
  photos: number
  videos: number
  species: number
  bursts: number
  recent_photos: Array<{
    id: string
    filename: string
    imported_at: string
  }>
}

// 上传会话
export interface UploadSession {
  upload_id: string
  filename: string
  total_chunks: number
  uploaded_chunks: number[]
  status: 'uploading' | 'completed' | 'error'
}

// 去重
export interface DuplicateGroup {
  group_id: string
  hash_type: string
  photos: {
    photo_id: string
    filename: string
    similarity: number
    rating: number | null
  }[]
}

// 筛选
export interface PhotoFilters {
  q?: string
  species?: string
  camera?: string
  rating_min?: number
  rating_max?: number
  date_from?: string
  date_to?: string
  iso_min?: number
  iso_max?: number
  aperture_min?: number
  aperture_max?: number
  shutter_speed?: string
  has_gps?: boolean
  has_flying?: boolean
  recognized?: string
  confidence_min?: number
  page?: number
  page_size?: number
}
