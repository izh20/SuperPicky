import { defineStore } from 'pinia'
import { ref } from 'vue'
import { burstAPI } from '@/api/bursts'
import type { BurstGroup } from '@/types'

export const useBurstStore = defineStore('bursts', () => {
  const list = ref<BurstGroup[]>([])
  const current = ref<(BurstGroup & { photos: any[] }) | null>(null)
  const loading = ref(false)

  async function fetchList() {
    loading.value = true
    try {
      list.value = await burstAPI.list()
    } finally {
      loading.value = false
    }
  }

  async function fetchBurst(id: string) {
    current.value = await burstAPI.get(id)
  }

  return { list, current, loading, fetchList, fetchBurst }
})
