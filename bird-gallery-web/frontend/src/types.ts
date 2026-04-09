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

// 批处理
export interface CropConfig {
  aspect_ratio: '16:9' | '4:3' | '3:2' | '1:1' | '21:9' | '9:16' | 'original'
  output_size: [number, number] | null
  composition: 'center' | 'rule-of-thirds' | 'tight' | 'environmental'
  bird_padding: number
}

export interface WatermarkConfig {
  type: 'text' | 'image' | 'tiled' | 'info-bar'
  opacity?: number
  position?: string
  margin?: number
  text?: string
  font?: string
  font_size?: number
  color?: [number, number, number]
  shadow?: boolean
  shadow_color?: [number, number, number]
  shadow_offset?: number
  logo_path?: string
  logo_scale?: number
  rotation?: number
  spacing_x?: number
  spacing_y?: number
  bar_position?: 'bottom' | 'top'
  bar_mode?: 'append' | 'overlay'
  bar_bg_color?: [number, number, number]
  bar_padding?: number
  text_color?: [number, number, number]
  title_font_size?: number
  detail_font_size?: number
  show_species?: boolean
  species_lang?: 'cn' | 'en' | 'cn+en' | 'scientific'
  show_exif?: boolean
  exif_fields?: string[]
  show_copyright?: boolean
  copyright_text?: string
}

export interface BatchProcessConfig {
  min_rating: 0 | 1 | 2 | 3
  denoise_enabled: boolean
  denoise_algorithm: 'DeepPRIME_3' | 'DeepPRIME_XD3'
  denoise_luminance: number
  denoise_chrominance: number
  auto_tone_enabled: boolean
  auto_tone_tool: 'lightroom' | 'darktable'
  crop_preset: string
  crop_config?: CropConfig
  watermark_preset: string
  watermark_layers?: WatermarkConfig[]
  output_format: 'jpeg' | 'tiff' | 'png'
  output_quality: number
  output_dir?: string
}

export interface BatchProcessStartResponse {
  task_id: string
  total_photos: number
  filtered_photos: number
  estimated_time_minutes: number
}

export interface BatchProcessResultItem {
  photo_id: string
  filename: string
  phase: string
  final_output: string | null
  error_msg: string | null
}

export interface BatchProcessResultsResponse {
  task_id: string
  total: number
  completed: number
  failed: number
  items: BatchProcessResultItem[]
}

export interface BatchProcessOptions {
  crop_presets: Record<string, { label: string; aspect_ratio: string; composition: string }>
  watermark_presets: Record<string, { label: string }>
  denoise_algorithms: string[]
  auto_tone_tools: string[]
  output_formats: string[]
  aspect_ratios: string[]
  compositions: string[]
}
