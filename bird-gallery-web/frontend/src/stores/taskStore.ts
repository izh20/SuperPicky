/**
 * 全局异步任务追踪 store
 *
 * 用于在页面切换 / 刷新时保持任务进度状态（如批量识别）。
 * 活跃任务 ID 持久化到 localStorage，刷新后自动恢复轮询。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskAPI } from '@/api/admin'
import type { Task } from '@/types'

const STORAGE_KEY = 'bg_active_task'

export interface RecognizeResultItem {
  filename?: string
  species_cn?: string | null
  rating?: number | null
  head_sharp?: number | null
  nima_score?: number | null
  elapsed?: number | null
  error?: string
}

interface RecognizePayload {
  processed?: number
  total?: number
  results?: RecognizeResultItem[]
  phase?: string
  preview_processed?: number
  preview_total?: number
}

function _parseRecognizePayload(resultJson: string | null): RecognizePayload | null {
  if (!resultJson) return null
  try {
    const payload = JSON.parse(resultJson)
    if (payload && typeof payload === 'object') return payload
  } catch {}
  return null
}

function _inferTotal(processed: number, progress: number, fallback = 0) {
  if (processed > 0 && progress > 0) {
    return Math.max(fallback, Math.ceil((processed * 100) / progress))
  }
  return fallback
}

function _saveActive(taskId: string, total: number) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ taskId, total })) } catch {}
}
function _clearActive() {
  try { localStorage.removeItem(STORAGE_KEY) } catch {}
}
function _loadActive(): { taskId: string; total: number } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const obj = JSON.parse(raw)
    if (obj && typeof obj.taskId === 'string') return obj
  } catch {}
  return null
}

export const useTaskStore = defineStore('task', () => {
  // ── 批量识别任务状态 ──
  const recognizeTaskId = ref<string | null>(null)
  const recognizing = ref(false)
  const recognizeProgress = ref(0)
  const recognizeTotal = ref(0)
  const recognizeProcessed = ref(0)
  const recognizeResults = ref<RecognizeResultItem[]>([])
  const recognizePhase = ref<string | null>(null)
  const recognizePreviewProcessed = ref(0)
  const recognizePreviewTotal = ref(0)

  let _pollTimer: ReturnType<typeof setTimeout> | null = null

  function _applyTaskSnapshot(task: Task, fallbackTotal = 0) {
    const payload = _parseRecognizePayload(task.result_json)
    const processed = typeof payload?.processed === 'number' ? payload.processed : 0
    const totalFromPayload = typeof payload?.total === 'number' ? payload.total : 0

    recognizeTaskId.value = task.id
    recognizing.value = task.status === 'pending' || task.status === 'running'
    recognizeProgress.value = task.progress ?? 0
    recognizeProcessed.value = processed
    recognizeTotal.value = totalFromPayload || _inferTotal(processed, task.progress ?? 0, fallbackTotal)
    recognizeResults.value = Array.isArray(payload?.results) ? payload.results : []
    recognizePhase.value = typeof payload?.phase === 'string' ? payload.phase : null
    recognizePreviewProcessed.value = typeof payload?.preview_processed === 'number' ? payload.preview_processed : 0
    recognizePreviewTotal.value = typeof payload?.preview_total === 'number' ? payload.preview_total : 0
    _saveActive(task.id, recognizeTotal.value)
  }

  const recognizeTitle = computed(() => {
    if (recognizeProgress.value >= 100) return '即将完成…'
    if (recognizePhase.value === 'preparing_previews') return '正在准备 RAW 预览图…'
    return '正在识别鸟类并评分…'
  })

  const recognizeStatusText = computed(() => {
    if (recognizeProgress.value >= 100) return '即将完成…'
    if (recognizePhase.value === 'preparing_previews' && recognizePreviewTotal.value > 0) {
      return `正在生成预览缓存 ${recognizePreviewProcessed.value} / ${recognizePreviewTotal.value}，完成后开始正式识别`
    }
    if (recognizeTotal.value > 0) {
      return `已处理 ${recognizeProcessed.value} / ${recognizeTotal.value} 张（每张照片需加载 AI 模型进行关键点检测和美学评分）`
    }
    return '正在提交识别任务…'
  })

  /** 开始追踪一个识别任务 */
  function startTracking(taskId: string, total: number) {
    recognizeTaskId.value = taskId
    recognizing.value = true
    recognizeProgress.value = 0
    recognizeTotal.value = total
    recognizeProcessed.value = 0
    recognizeResults.value = []
    recognizePhase.value = null
    recognizePreviewProcessed.value = 0
    recognizePreviewTotal.value = 0
    _saveActive(taskId, total)
    _poll()
  }

  /** 恢复追踪（页面刷新 / 切换回来时调用） */
  function resumeIfActive() {
    // 已经在轮询中，跳过
    if (recognizing.value && recognizeTaskId.value && _pollTimer) return

    // 先检查内存状态
    if (recognizing.value && recognizeTaskId.value) {
      _poll()
      return
    }

    // 从 localStorage 恢复
    const saved = _loadActive()
    if (saved) {
      recognizeTaskId.value = saved.taskId
      recognizeTotal.value = saved.total
      recognizing.value = true
      recognizeProgress.value = 0
      recognizeProcessed.value = 0
      recognizeResults.value = []
      recognizePhase.value = null
      recognizePreviewProcessed.value = 0
      recognizePreviewTotal.value = 0
      _poll()
    }
  }

  async function resumeLatestRecognizeAll() {
    if (recognizing.value && recognizeTaskId.value) return true
    try {
      const task = await taskAPI.getLatestByType('recognize_all')
      if (task.status !== 'pending' && task.status !== 'running') return false
      if (_pollTimer) {
        clearTimeout(_pollTimer)
        _pollTimer = null
      }
      _applyTaskSnapshot(task)
      _poll()
      return true
    } catch {
      return false
    }
  }

  /** 停止追踪 */
  function stopTracking() {
    recognizing.value = false
    recognizeTaskId.value = null
    recognizeProgress.value = 0
    recognizeTotal.value = 0
    recognizeProcessed.value = 0
    recognizeResults.value = []
    recognizePhase.value = null
    recognizePreviewProcessed.value = 0
    recognizePreviewTotal.value = 0
    _clearActive()
    if (_pollTimer) {
      clearTimeout(_pollTimer)
      _pollTimer = null
    }
  }

  /** 取消正在运行的识别任务 */
  async function cancelRecognize() {
    if (!recognizeTaskId.value) return
    try {
      await taskAPI.cancel(recognizeTaskId.value)
    } catch {
      // ignore
    }
    stopTracking()
  }

  async function _poll() {
    if (!recognizeTaskId.value) return
    try {
      const t = await taskAPI.get(recognizeTaskId.value)
      recognizeProgress.value = t.progress ?? 0

      // 解析实时结果
      const payload = _parseRecognizePayload(t.result_json)
      if (payload) {
        if (typeof payload.processed === 'number') {
          recognizeProcessed.value = payload.processed
        }
        if (typeof payload.total === 'number' && payload.total > 0) {
          recognizeTotal.value = payload.total
          _saveActive(t.id, payload.total)
        } else if (!recognizeTotal.value) {
          recognizeTotal.value = _inferTotal(recognizeProcessed.value, t.progress ?? 0, recognizeTotal.value)
        }
        if (Array.isArray(payload.results)) {
          recognizeResults.value = payload.results
        }
        recognizePhase.value = typeof payload.phase === 'string' ? payload.phase : null
        recognizePreviewProcessed.value = typeof payload.preview_processed === 'number' ? payload.preview_processed : 0
        recognizePreviewTotal.value = typeof payload.preview_total === 'number' ? payload.preview_total : 0
      } else if (t.result_json) {
        try {
          const legacyPayload = JSON.parse(t.result_json)
          if (Array.isArray(legacyPayload)) {
            recognizeResults.value = legacyPayload
          }
        } catch {}
      }

      if (t.status === 'done') {
        recognizeProgress.value = 100
        stopTracking()
        return 'done'
      }
      if (t.status === 'error') {
        stopTracking()
        return 'error'
      }
      if (t.status === 'cancelled') {
        stopTracking()
        return 'cancelled'
      }
      _pollTimer = setTimeout(() => _poll(), 1000)
      return 'running'
    } catch {
      stopTracking()
      return 'error'
    }
  }

  // ── 通用活跃任务状态（供全局浮动进度条使用）──
  const activeTaskLabel = ref<string | null>(null)
  const activeTaskProgress = ref(0)

  /** 设置全局浮动进度信息（视频分析等非识别任务使用） */
  function setActiveTask(label: string, progress: number) {
    activeTaskLabel.value = label
    activeTaskProgress.value = progress
  }

  /** 清除全局浮动进度 */
  function clearActiveTask() {
    activeTaskLabel.value = null
    activeTaskProgress.value = 0
  }

  /** 是否有任何活跃任务 */
  const hasActiveTask = computed(() => recognizing.value || !!activeTaskLabel.value)

  return {
    recognizeTaskId,
    recognizing,
    recognizeProgress,
    recognizeProcessed,
    recognizeTotal,
    recognizeResults,
    recognizePhase,
    recognizePreviewProcessed,
    recognizePreviewTotal,
    recognizeTitle,
    recognizeStatusText,
    startTracking,
    resumeIfActive,
    resumeLatestRecognizeAll,
    stopTracking,
    cancelRecognize,
    // generic active task
    activeTaskLabel,
    activeTaskProgress,
    setActiveTask,
    clearActiveTask,
    hasActiveTask,
  }
})
