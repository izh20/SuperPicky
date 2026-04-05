import { defineStore } from 'pinia'
import { ref } from 'vue'
import { adminAPI } from '@/api/admin'
import type { DashboardStats, SystemMetrics } from '@/types'

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardStats | null>(null)
  const metrics = ref<SystemMetrics | null>(null)
  const loading = ref(false)

  async function fetchAll() {
    loading.value = true
    try {
      const [s, m] = await Promise.all([adminAPI.dashboard(), adminAPI.metrics()])
      stats.value = s
      metrics.value = m
    } finally {
      loading.value = false
    }
  }

  async function releaseModels() {
    await adminAPI.releaseModels()
    await adminAPI.metrics().then(m => { metrics.value = m })
  }

  return { stats, metrics, loading, fetchAll, releaseModels }
})
