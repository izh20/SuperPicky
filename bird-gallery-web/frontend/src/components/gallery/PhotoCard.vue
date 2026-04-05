<template>
  <div
    class="group relative rounded-lg overflow-hidden bg-gray-100 cursor-pointer"
    @click="emit('click')"
  >
    <div class="aspect-square">
      <img
        :src="`/api/photos/${photo.id}/thumbnail?size=sm`"
        :alt="photo.filename"
        class="w-full h-full object-cover"
        loading="lazy"
      />
    </div>
    <div class="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <StarRating :rating="photo.rating" />
    </div>
    <!-- hover 详情 -->
    <div class="absolute top-0 left-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity bg-black/60 px-2 py-1.5 text-[10px] text-white/90 leading-relaxed pointer-events-none">
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
        :class="selected ? 'bg-blue-600 border-blue-600' : 'bg-white/70 border-gray-400'"
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
import type { PhotoListItem } from '@/types'
import StarRating from '@/components/common/StarRating.vue'

defineProps<{
  photo: PhotoListItem
  selectable?: boolean
  selected?: boolean
}>()

const emit = defineEmits<{
  (e: 'click'): void
  (e: 'toggle-select', id: string): void
}>()
</script>
