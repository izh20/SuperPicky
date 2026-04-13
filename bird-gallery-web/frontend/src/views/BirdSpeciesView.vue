<template>
  <div class="max-w-6xl mx-auto px-3 sm:px-5 py-4 sm:py-6">
    <!-- 导航 -->
    <div class="flex items-center gap-2 mb-3 sm:mb-4">
      <button @click="$router.back()" class="flex items-center gap-1 text-sm text-text-tertiary dark:text-text-on-dark-tertiary hover:text-text-primary dark:hover:text-text-on-dark">
        <ArrowLeft class="w-4 h-4" /> 鸟种目录
      </button>
    </div>

    <!-- 物种标题 -->
    <div class="card-apple dark:bg-surface-card-dark p-4 sm:p-5 mb-4 sm:mb-6">
      <h1 class="text-xl sm:text-2xl font-semibold text-text-primary dark:text-text-on-dark font-display">{{ species }}</h1>
      <p v-if="speciesInfo" class="text-sm text-text-secondary dark:text-text-on-dark-secondary mt-1">
        {{ speciesInfo.species_en }} · <em>{{ speciesInfo.scientific_name }}</em>
      </p>
      <p class="text-sm text-apple-blue font-medium mt-1">{{ speciesInfo?.photo_count ?? 0 }} 张照片</p>
    </div>

    <!-- 照片网格 -->
    <Spinner v-if="loading" />
    <EmptyState v-else-if="!photos.length" title="暂无照片" />
    <div v-else class="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-1.5 sm:gap-2">
      <RouterLink
        v-for="photo in photos"
        :key="photo.id"
        :to="`/photos/${photo.id}`"
        class="group relative rounded-lg overflow-hidden bg-black/5 dark:bg-white/5 shadow-sm hover:shadow-apple transition-shadow"
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
        class="btn-pill disabled:opacity-50"
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
