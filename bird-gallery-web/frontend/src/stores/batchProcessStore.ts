/**
 * 批处理任务 store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskAPI } from '@/api/admin'
import * as batchApi from '@/api/batchProcess'
import type {
  BatchProcessConfig,
  BatchProcessOptions,
  BatchProcessResultsResponse,
} from '@/types'

const STORAGE_KEY = 'bg_batch_task'

function _saveActive(taskId: string) {
  try { localStorage.setItem(STORAGE_KEY, taskId) } catch {}
}
function _clearActive() {
  try { localStorage.removeItem(STORAGE_KEY) } catch {}
}
function _loadActive(): string | null {
  try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
}

export const useBatchProcessStore = defineStore('batchProcess', () => {
  const taskId = ref<string | null>(null)
  const running = ref(false)
  const progress = ref(0)
  const currentPhase = ref('')
  const currentFile = ref('')
  const phaseProgress = ref<Record<string, number>>({})
  const total = ref(0)
  const completed = ref(0)
  const failed = ref(0)
  const errorMsg = ref<string | null>(null)
  const status = ref<string>('idle')

  const options = ref<BatchProcessOptions | null>(null)
  const results = ref<BatchProcessResultsResponse | null>(null)

  let _pollTimer: ReturnType<typeof setTimeout> | null = null

  const statusText = computed(() => {
    if (status.value === 'done') return '处理完成'
    if (status.value === 'error') return errorMsg.value || '处理失败'
    if (status.value === 'cancelled') return '已取消'
    if (!running.value) return ''
    const phaseLabels: Record<string, string> = {
      filter: '筛选中', denoise: '降噪中',
      tone: '调色中', crop: '裁切/水印中',
    }
    const label = phaseLabels[currentPhase.value] || currentPhase.value
    return currentFile.value
      ? `${label} — ${currentFile.value}`
      : label
  })

  async function fetchOptions() {
    options.value = await batchApi.getOptions()
  }

  async function start(config: BatchProcessConfig) {
    const res = await batchApi.startBatchProcess(config)
    taskId.value = res.task_id
    total.value = res.filtered_photos
    running.value = true
    status.value = 'running'
    errorMsg.value = null
    _saveActive(res.task_id)
    _startPolling()
  }

  async function cancel() {
    if (!taskId.value) return
    try {
      await taskAPI.cancel(taskId.value)
    } catch {}
  }

  async function fetchResults() {
    if (!taskId.value) return
    results.value = await batchApi.getResults(taskId.value)
  }

  function _startPolling() {
    _stopPolling()
    _poll()
  }

  function _stopPolling() {
    if (_pollTimer) {
      clearTimeout(_pollTimer)
      _pollTimer = null
    }
  }

  async function _poll() {
    if (!taskId.value) return
    try {
      const task = await taskAPI.get(taskId.value)
      progress.value = task.progress
      status.value = task.status

      if (task.result_json) {
        try {
          const data = typeof task.result_json === 'string'
            ? JSON.parse(task.result_json) : task.result_json
          currentPhase.value = data.current_phase || ''
          currentFile.value = data.current_file || ''
          phaseProgress.value = data.phase_progress || {}
          if (data.total) total.value = data.total
          if (data.completed !== undefined) completed.value = data.completed
          if (data.failed !== undefined) failed.value = data.failed
        } catch {}
      }

      if (task.status === 'error') {
        errorMsg.value = task.error_msg || 'Unknown error'
        running.value = false
        _clearActive()
        return
      }
      if (task.status === 'done' || task.status === 'cancelled') {
        running.value = false
        _clearActive()
        await fetchResults()
        return
      }

      _pollTimer = setTimeout(_poll, 3000)
    } catch {
      _pollTimer = setTimeout(_poll, 5000)
    }
  }

  function tryRestore() {
    const saved = _loadActive()
    if (saved) {
      taskId.value = saved
      running.value = true
      status.value = 'running'
      _startPolling()
    }
  }

  /** Load the latest completed batch task and its results for display. */
  async function loadLatestDone() {
    if (taskId.value || running.value) return
    try {
      const res = await taskAPI.getLatestByType('batch_process')
      if (res && (res.status === 'done' || res.status === 'error')) {
        taskId.value = res.id
        status.value = res.status
        progress.value = res.progress
        errorMsg.value = res.error_msg || null
        if (res.result_json) {
          const data = typeof res.result_json === 'string'
            ? JSON.parse(res.result_json) : res.result_json
          completed.value = data.completed ?? 0
          failed.value = data.failed ?? 0
          total.value = data.total ?? 0
        }
        if (res.status === 'done') {
          await fetchResults()
        }
      }
    } catch {}
  }

  return {
    taskId, running, progress, currentPhase, currentFile,
    phaseProgress, total, completed, failed, errorMsg,
    status, options, results, statusText,
    fetchOptions, start, cancel, fetchResults, tryRestore, loadLatestDone,
  }
})
