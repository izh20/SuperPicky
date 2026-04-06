/**
 * 全局异步任务追踪 store
 *
 * 用于在页面切换 / 刷新时保持任务进度状态（如批量识别）。
 * 活跃任务 ID 持久化到 localStorage，刷新后自动恢复轮询。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskAPI } from '@/api/admin'

const STORAGE_KEY = 'bg_active_task'

export interface RecognizeResultItem {
  filename?: string
  species_cn?: string | null
  rating?: number | null
  head_sharp?: number | null
  nima_score?: number | null
  error?: string
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

  let _pollTimer: ReturnType<typeof setTimeout> | null = null

  const recognizeStatusText = computed(() => {
    if (recognizeProgress.value >= 100) return '即将完成…'
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
      _poll()
    }
  }

  /** 停止追踪 */
  function stopTracking() {
    recognizing.value = false
    recognizeTaskId.value = null
    recognizeProgress.value = 0
    recognizeTotal.value = 0
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
      if (t.result_json) {
        try {
          const payload = JSON.parse(t.result_json)
          if (payload && typeof payload.processed === 'number') {
            recognizeProcessed.value = payload.processed
            recognizeResults.value = payload.results ?? []
          } else if (Array.isArray(payload)) {
            // 兼容旧格式
            recognizeResults.value = payload
          }
        } catch { /* ignore parse error */ }
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

  return {
    recognizeTaskId,
    recognizing,
    recognizeProgress,
    recognizeProcessed,
    recognizeTotal,
    recognizeResults,
    recognizeStatusText,
    startTracking,
    resumeIfActive,
    stopTracking,
    cancelRecognize,
  }
})
