<template>
  <div class="max-w-6xl mx-auto">
    <!-- 导航 -->
    <div class="flex items-center gap-2 mb-4">
      <button @click="$router.back()" class="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
        <ArrowLeft class="w-4 h-4" /> 鸟种目录
      </button>
    </div>

    <!-- 物种标题 -->
    <div class="bg-white rounded-xl p-5 border border-gray-100 mb-6">
      <h1 class="text-2xl font-bold text-gray-800">{{ species }}</h1>
      <p v-if="speciesInfo" class="text-sm text-gray-500 mt-1">
        {{ speciesInfo.species_en }} · <em>{{ speciesInfo.scientific_name }}</em>
      </p>
      <p class="text-sm text-primary-600 font-medium mt-1">{{ speciesInfo?.photo_count ?? 0 }} 张照片</p>
    </div>

    <!-- 照片网格 -->
    <Spinner v-if="loading" />
    <EmptyState v-else-if="!photos.length" title="暂无照片" />
    <div v-else class="grid gap-2" style="grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));">
      <RouterLink
        v-for="photo in photos"
        :key="photo.id"
        :to="`/photos/${photo.id}`"
        class="group relative rounded-lg overflow-hidden bg-gray-100 shadow-sm hover:shadow-md transition-shadow"
      >
        <div class="aspect-square overflow-hidden">
          <img
            :src="`/api/photos/${photo.id}/thumbnail?size=sm`"
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
          />
        </div>
        <div class="absolute top-1 right-1">
          <StarRating :rating="photo.rating" />
        </div>
      </RouterLink>
    </div>

    <!-- 加载更多 -->
    <div v-if="hasMore" class="flex justify-center mt-6">
      <button
        @click="loadMore"
        :disabled="loading"
        class="px-6 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
      >加载更多</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import { birdAPI } from '@/api/birds'
import { useBirdStore } from '@/stores/birdStore'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import StarRating from '@/components/common/StarRating.vue'
import type { PhotoListItem } from '@/types'

const route = useRoute()
const birdStore = useBirdStore()

const species = computed(() => decodeURIComponent(route.params.species as string))
const speciesInfo = computed(() => birdStore.list.find(b => b.species_cn === species.value))
const photos = ref<PhotoListItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const hasMore = computed(() => photos.value.length < total.value)

onMounted(async () => {
  if (!birdStore.list.length) await birdStore.fetchList()
  await fetchPage(true)
})

async function fetchPage(reset = false) {
  if (reset) { page.value = 1; photos.value = [] }
  loading.value = true
  try {
    const res = await birdAPI.photos(species.value, page.value)
    photos.value.push(...res.items)
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  page.value++
  await fetchPage(false)
}
</script>
