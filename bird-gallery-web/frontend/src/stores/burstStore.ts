import { defineStore } from 'pinia'
import { ref } from 'vue'
import { burstAPI, type BurstFilters } from '@/api/bursts'
import type { BurstGroup } from '@/types'

export const useBurstStore = defineStore('bursts', () => {
  const list = ref<BurstGroup[]>([])
  const current = ref<(BurstGroup & { photos: any[] }) | null>(null)
  const loading = ref(false)
  const filters = ref<BurstFilters>({})

  async function fetchList() {
    loading.value = true
    try {
      const cleanFilters: BurstFilters = {}
      if (filters.value.species) cleanFilters.species = filters.value.species
      if (filters.value.camera) cleanFilters.camera = filters.value.camera
      if (filters.value.rating_min != null) cleanFilters.rating_min = filters.value.rating_min
      if (filters.value.min_photos != null && filters.value.min_photos > 1)
        cleanFilters.min_photos = filters.value.min_photos
      if (filters.value.has_flying) {
        cleanFilters.has_flying = true
        if (filters.value.flying_min_count != null && filters.value.flying_min_count > 1)
          cleanFilters.flying_min_count = filters.value.flying_min_count
      }
      const res = await burstAPI.list(cleanFilters)
      list.value = (res as any).groups ?? res
    } finally {
      loading.value = false
    }
  }

  async function fetchBurst(id: string) {
    current.value = await burstAPI.get(id)
  }

  function updateFilter(key: string, value: any) {
    ;(filters.value as any)[key] = value
    fetchList()
  }

  function resetFilters() {
    filters.value = {}
    fetchList()
  }

  return { list, current, loading, filters, fetchList, fetchBurst, updateFilter, resetFilters }
})
