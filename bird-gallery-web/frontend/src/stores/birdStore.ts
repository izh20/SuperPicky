import { defineStore } from 'pinia'
import { ref } from 'vue'
import { birdAPI } from '@/api/birds'
import type { BirdSpecies } from '@/types'

export const useBirdStore = defineStore('birds', () => {
  const list = ref<BirdSpecies[]>([])
  const loading = ref(false)
  const searchQuery = ref('')

  async function fetchList() {
    loading.value = true
    try {
      list.value = await birdAPI.list()
    } finally {
      loading.value = false
    }
  }

  const filtered = () =>
    searchQuery.value
      ? list.value.filter(b =>
          b.species_cn.includes(searchQuery.value) ||
          b.species_en.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
          b.scientific_name.toLowerCase().includes(searchQuery.value.toLowerCase()),
        )
      : list.value

  return { list, loading, searchQuery, fetchList, filtered }
})
