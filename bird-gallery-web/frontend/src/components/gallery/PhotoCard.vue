<template>
  <div
    class="relative rounded-[5px] overflow-hidden bg-surface-light dark:bg-surface-card-dark cursor-pointer group transition-all duration-300 hover:scale-[1.02] hover:shadow-apple"
    @click="emit('click')"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <div class="aspect-square">
      <img
        :src="`/api/photos/${photo.id}/thumbnail?size=sm`"
        :alt="photo.filename"
        class="w-full h-full object-cover"
        loading="lazy"
      />
    </div>
    <!-- 星级评分（始终显示，右下角） -->
    <div class="absolute bottom-6 right-1 z-10 pointer-events-none">
      <StarRating :rating="photo.rating" />
    </div>
    <!-- 评分详情（hover 显示） -->
    <div v-show="hovered && hasInfo" class="absolute z-10 top-0 left-0 right-0 bg-black/60 px-2 py-1.5 text-[10px] text-white/90 leading-relaxed pointer-events-none">
      <p v-if="photo.species_cn" class="font-medium text-[11px]">{{ photo.species_cn }}</p>
      <p v-if="photo.confidence != null">置信度 {{ photo.confidence.toFixed(1) }}%</p>
      <p v-if="photo.head_sharp != null">锐度 {{ photo.head_sharp.toFixed(1) }}</p>
      <p v-if="photo.nima_score != null">美学 {{ photo.nima_score.toFixed(2) }}</p>
    </div>
    <div
      v-if="selectable"
      class="absolute top-1 left-1"
      @click.stop="emit('toggle-select', photo.id)"
    >
      <div
        class="w-5 h-5 rounded border-2 flex items-center justify-center text-white text-xs"
        :class="selected ? 'bg-apple-blue border-apple-blue' : 'bg-white/70 border-gray-400'"
      >
        <span v-if="selected">✓</span>
      </div>
    </div>
    <div class="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/60 to-transparent px-2 py-1.5">
      <p class="text-xs text-white truncate">{{ photo.species_cn || photo.species_en || '未识别' }}</p>
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
const hasInfo = computed(() =>
  props.photo.species_cn != null || props.photo.confidence != null || props.photo.head_sharp != null || props.photo.nima_score != null,
)
</script>
