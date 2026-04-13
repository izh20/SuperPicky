<template>
  <div
    class="photo-card group relative cursor-pointer"
    @click="emit('click')"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <!-- 图片容器 -->
    <div class="aspect-[4/3] overflow-hidden rounded-lg bg-black/5 dark:bg-white/5">
      <img
        :src="`/api/photos/${photo.id}/thumbnail?size=sm`"
        :alt="photo.filename"
        class="w-full h-full object-cover transition-transform duration-500 ease-out will-change-transform group-hover:scale-[1.05]"
        loading="lazy"
      />
    </div>

    <!-- 浮层：渐变底部信息 -->
    <div class="absolute inset-0 rounded-lg overflow-hidden pointer-events-none">
      <!-- 底部渐变 — 始终存在，hover 时加深 -->
      <div class="absolute bottom-0 inset-x-0 h-2/3 bg-gradient-to-t from-black/70 via-black/20 to-transparent transition-opacity duration-300"
           :class="hovered ? 'opacity-100' : 'opacity-80'" />
    </div>

    <!-- 信息层 -->
    <div class="absolute bottom-0 inset-x-0 z-10 p-2.5 sm:p-3">
      <!-- 鸟种名 -->
      <p class="text-[13px] sm:text-[14px] font-semibold text-white truncate leading-tight tracking-tight"
         style="letter-spacing: -0.224px;">
        {{ photo.species_cn || '未识别' }}
      </p>
      <!-- 副信息行：学名 + 置信度 -->
      <div class="flex items-center gap-1.5 mt-0.5">
        <span v-if="photo.species_en" class="text-[11px] text-white/60 truncate italic">{{ photo.species_en }}</span>
        <span v-if="photo.confidence != null" class="text-[11px] text-white/50 shrink-0">{{ photo.confidence.toFixed(0) }}%</span>
      </div>
      <!-- hover 详情 -->
      <Transition name="detail-fade">
        <div v-if="hovered && hasDetail" class="flex items-center gap-2 mt-1.5 text-[11px] text-white/70">
          <span v-if="photo.head_sharp != null">锐度 {{ photo.head_sharp.toFixed(1) }}</span>
          <span v-if="photo.nima_score != null">美学 {{ photo.nima_score.toFixed(2) }}</span>
        </div>
      </Transition>
    </div>

    <!-- 星级评分 — 右上角 -->
    <div v-if="photo.rating != null && photo.rating >= 0" class="absolute top-2 right-2 z-10 pointer-events-none">
      <StarRating :rating="photo.rating" />
    </div>

    <!-- 选择复选框 -->
    <div
      v-if="selectable"
      class="absolute top-2 left-2 z-20"
      @click.stop="emit('toggle-select', photo.id)"
    >
      <div
        class="w-6 h-6 rounded-full flex items-center justify-center transition-all duration-200 pointer-events-auto"
        :class="selected
          ? 'bg-apple-blue shadow-lg scale-110'
          : 'bg-black/30 backdrop-blur-sm hover:bg-black/50'"
      >
        <svg v-if="selected" class="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PhotoListItem } from '@/types'
import StarRating from '@/components/common/StarRating.vue'

const props = defineProps<{
  photo: PhotoListItem
  selectable?: boolean
  selected?: boolean
}>()

const emit = defineEmits<{
  (e: 'click'): void
  (e: 'toggle-select', id: string): void
}>()

const hovered = ref(false)
const hasDetail = computed(() =>
  props.photo.head_sharp != null || props.photo.nima_score != null,
)
</script>

<style scoped>
.photo-card {
  transition: transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94),
              box-shadow 0.3s ease;
}
.photo-card:hover {
  transform: translateY(-2px);
  box-shadow: rgba(0, 0, 0, 0.15) 0px 8px 24px 0px;
}
.detail-fade-enter-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.detail-fade-leave-active { transition: opacity 0.15s ease; }
.detail-fade-enter-from { opacity: 0; transform: translateY(4px); }
.detail-fade-leave-to { opacity: 0; }
</style>
