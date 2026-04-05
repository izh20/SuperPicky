import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { photoAPI } from '@/api/photos'
import type { PhotoListItem, PhotoListResponse, PhotoFilters } from '@/types'

export const usePhotoStore = defineStore('photos', () => {
  const items = ref<PhotoListItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const filters = reactive<PhotoFilters>({
    page: 1,
    page_size: 60,
  })

  async function fetchPhotos(reset = false) {
    if (reset) {
      filters.page = 1
      items.value = []
    }
    loading.value = true
    error.value = null
    try {
      const res: PhotoListResponse = await photoAPI.list({ ...filters })
      if (reset || filters.page === 1) {
        items.value = res.items
      } else {
        items.value.push(...res.items)
      }
      total.value = res.total
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function setFilter<K extends keyof PhotoFilters>(key: K, val: PhotoFilters[K]) {
    filters[key] = val
  }

  function resetFilters() {
    Object.assign(filters, {
      q: undefined, species: undefined, camera: undefined,
      rating_min: undefined, rating_max: undefined,
      date_from: undefined, date_to: undefined,
      page: 1, page_size: 60,
    })
  }

  function nextPage() {
    filters.page = (filters.page ?? 1) + 1
  }

  async function deletePhoto(id: string) {
    await photoAPI.delete(id)
    items.value = items.value.filter(p => p.id !== id)
    total.value = Math.max(0, total.value - 1)
  }

  return { items, total, loading, error, filters, fetchPhotos, setFilter, resetFilters, nextPage, deletePhoto }
})
