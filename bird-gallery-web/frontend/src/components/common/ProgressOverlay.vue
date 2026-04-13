<template>
  <Teleport to="body">
    <Transition name="progress-slide">
      <div
        v-if="visible"
        class="fixed top-12 left-0 right-0 z-[90] flex justify-center pointer-events-none px-3"
      >
        <div
          class="pointer-events-auto w-full max-w-md bg-black/85 dark:bg-white/15 backdrop-blur-xl
                 rounded-2xl px-4 py-3 shadow-2xl flex items-center gap-3"
        >
          <!-- 环形进度 -->
          <div class="relative w-10 h-10 shrink-0">
            <svg class="w-10 h-10 -rotate-90" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="3" />
              <circle
                cx="18" cy="18" r="15" fill="none"
                stroke="#34d399" stroke-width="3" stroke-linecap="round"
                :stroke-dasharray="circumference"
                :stroke-dashoffset="circumference - (circumference * progress / 100)"
                class="transition-all duration-500"
              />
            </svg>
            <span class="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white tabular-nums">
              {{ Math.round(progress) }}%
            </span>
          </div>

          <!-- 文字 -->
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-white truncate">{{ title }}</p>
            <p class="text-[12px] text-white/60 truncate">{{ subtitle }}</p>
          </div>

          <!-- 闪烁圆点表示活跃 -->
          <div class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0"></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTaskStore } from '@/stores/taskStore'

const taskStore = useTaskStore()
const circumference = 2 * Math.PI * 15 // r=15

const visible = computed(() => taskStore.hasActiveTask)

const progress = computed(() => {
  if (taskStore.recognizing) return taskStore.recognizeProgress
  return taskStore.activeTaskProgress
})

const title = computed(() => {
  if (taskStore.recognizing) {
    return taskStore.recognizeTitle
  }
  return taskStore.activeTaskLabel ?? '处理中…'
})

const subtitle = computed(() => {
  if (taskStore.recognizing) {
    if (taskStore.recognizePhase === 'preparing_previews' && taskStore.recognizePreviewTotal > 0) {
      return `预览图 ${taskStore.recognizePreviewProcessed} / ${taskStore.recognizePreviewTotal}`
    }
    if (taskStore.recognizeTotal > 0 && taskStore.recognizeProcessed > 0) {
      return `${taskStore.recognizeProcessed} / ${taskStore.recognizeTotal} 张`
    }
    if (taskStore.recognizeTotal > 0) {
      return `共 ${taskStore.recognizeTotal} 张待识别`
    }
    return '处理中…'
  }
  return `${Math.round(taskStore.activeTaskProgress)}% 完成`
})
</script>

<style scoped>
.progress-slide-enter-active,
.progress-slide-leave-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.progress-slide-enter-from {
  opacity: 0;
  transform: translateY(-20px);
}
.progress-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>
