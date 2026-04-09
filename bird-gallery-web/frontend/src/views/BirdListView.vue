<template>
  <div class="max-w-5xl mx-auto px-5 py-6">
    <h1 class="text-xl font-semibold text-text-primary dark:text-text-on-dark mb-4 font-display">鸟种目录</h1>

    <!-- 搜索 -->
    <div class="relative mb-6 max-w-xs">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary dark:text-text-on-dark-tertiary" />
      <input
        v-model="birdStore.searchQuery"
        type="text"
        placeholder="搜索鸟种名称…"
        class="w-full pl-9 pr-4 py-1.5 text-sm bg-surface-light dark:bg-white/10 border-0 rounded-full focus:outline-none focus:ring-2 focus:ring-apple-blue/40 dark:text-text-on-dark"
      />
    </div>

    <Spinner v-if="birdStore.loading" />
    <EmptyState
      v-else-if="!birdStore.list.length"
      title="暂无鸟种记录"
      description="识别照片后将在此显示鸟种统计"
      :icon="Bird"
    />
    <div v-else class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));">
      <RouterLink
        v-for="b in birdStore.filtered()"
        :key="b.species_cn"
        :to="`/birds/${encodeURIComponent(b.species_cn)}`"
        class="card-apple dark:bg-surface-card-dark p-4 hover:shadow-apple transition-shadow flex flex-col gap-1"
      >
        <div class="flex items-start justify-between">
          <div class="min-w-0">
            <p class="font-semibold text-text-primary dark:text-text-on-dark truncate">{{ b.species_cn }}</p>
            <p class="text-xs text-text-secondary dark:text-text-on-dark-secondary truncate">{{ b.species_en }}</p>
            <p class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary italic truncate">{{ b.scientific_name }}</p>
          </div>
          <span class="shrink-0 ml-2 text-sm font-bold text-apple-blue">{{ b.photo_count }}</span>
        </div>
        <div class="flex items-center gap-1 mt-1">
          <div class="flex-1 h-1 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden">
            <div
              class="h-full bg-apple-blue rounded-full"
              :style="{ width: `${Math.min(b.max_confidence, 100).toFixed(0)}%` }"
            />
          </div>
          <span class="text-xs text-text-tertiary dark:text-text-on-dark-tertiary">{{ b.max_confidence.toFixed(0) }}%</span>
        </div>
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { Search, Bird } from 'lucide-vue-next'
import { useBirdStore } from '@/stores/birdStore'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const birdStore = useBirdStore()
onMounted(() => birdStore.fetchList())
</script>
