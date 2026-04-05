<template>
  <div class="max-w-5xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold text-gray-800">连拍组</h1>
      <button
        @click="detectBursts"
        :disabled="detecting"
        class="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
      >
        <Zap class="w-4 h-4" />
        {{ detecting ? '检测中…' : '检测连拍' }}
      </button>
    </div>

    <Spinner v-if="burstStore.loading" />
    <EmptyState
      v-else-if="!burstStore.list.length"
      title="暂无连拍组"
      description="点击「检测连拍」按钮自动分组时间相近的照片"
      :icon="Layers"
    />
    <div v-else class="grid gap-4" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));">
      <RouterLink
        v-for="b in burstStore.list"
        :key="b.id"
        :to="`/bursts/${b.id}`"
        class="bg-white rounded-xl overflow-hidden border border-gray-100 hover:shadow-md transition-shadow p-3"
      >
        <!-- 叠加缩略图效果 -->
        <div class="relative h-28 mb-3">
          <div class="absolute inset-0 bg-gray-200 rounded-lg" />
          <div class="absolute inset-0 translate-x-1 translate-y-1 bg-gray-300 rounded-lg" />
          <div class="absolute inset-0 translate-x-2 translate-y-2 bg-gray-200 rounded-lg flex items-center justify-center">
            <Layers class="w-8 h-8 text-gray-400" />
          </div>
          <div class="absolute top-1 right-1 bg-primary-600 text-white text-xs px-1.5 py-0.5 rounded-full font-bold">
            {{ b.photo_count }}
          </div>
        </div>
        <p class="text-sm font-medium text-gray-700 truncate">{{ b.species_cn || '未识别' }}</p>
        <p class="text-xs text-gray-400 mt-0.5">{{ formatDate(b.first_shot_at) }}</p>
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { Zap, Layers } from 'lucide-vue-next'
import { ref } from 'vue'
import { useBurstStore } from '@/stores/burstStore'
import { useToastStore } from '@/stores/toastStore'
import { photoAPI } from '@/api/photos'
import { taskAPI } from '@/api/admin'
import Spinner from '@/components/common/Spinner.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const burstStore = useBurstStore()
const toast = useToastStore()
const detecting = ref(false)

onMounted(() => burstStore.fetchList())

async function detectBursts() {
  detecting.value = true
  try {
    const task = await photoAPI.detectBursts()
    toast.info('连拍检测任务已提交')
    await taskAPI.poll((task as any).task_id ?? task.id)
    toast.success('检测完成')
    await burstStore.fetchList()
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    detecting.value = false
  }
}

function formatDate(s: string | null | undefined) {
  if (!s) return ''
  return s.slice(0, 16).replace('T', ' ')
}
</script>
