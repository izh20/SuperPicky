import { defineStore } from 'pinia'
import { ref } from 'vue'
import { adminAPI } from '@/api/admin'
import type { AdminTaskSummary, DashboardStats, SystemMetrics } from '@/types'

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardStats | null>(null)
  const metrics = ref<SystemMetrics | null>(null)
  const tasks = ref<AdminTaskSummary[]>([])
  const runningTasks = ref(0)
  const queuedTasks = ref(0)
  const loading = ref(false)

  async function fetchTasks(limit = 20) {
    const res = await adminAPI.listTasks(limit)
    tasks.value = res.items
    runningTasks.value = res.running
    queuedTasks.value = res.queued
  }

  async function fetchAll() {
    loading.value = true
    try {
      const [s, m, t] = await Promise.all([adminAPI.dashboard(), adminAPI.metrics(), adminAPI.listTasks()])
      stats.value = s
      metrics.value = m
      tasks.value = t.items
      runningTasks.value = t.running
      queuedTasks.value = t.queued
    } finally {
      loading.value = false
    }
  }

  async function releaseModels() {
    await adminAPI.releaseModels()
    await adminAPI.metrics().then(m => { metrics.value = m })
  }

  async function cancelTask(id: string) {
    await adminAPI.cancelTask(id)
    await fetchAll()
  }

  async function retryTask(id: string) {
    const res = await adminAPI.retryTask(id)
    await fetchAll()
    return res
  }

  return {
    stats,
    metrics,
    tasks,
    runningTasks,
    queuedTasks,
    loading,
    fetchTasks,
    fetchAll,
    releaseModels,
    cancelTask,
    retryTask,
  }
})
