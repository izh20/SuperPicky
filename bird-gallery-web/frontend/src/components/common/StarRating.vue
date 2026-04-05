<template>
  <div class="inline-flex items-center gap-0.5 text-sm">
    <span
      v-for="i in 5"
      :key="i"
      class="text-base"
      :class="i <= stars ? 'text-yellow-400' : 'text-gray-300'"
    >★</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  rating?: number | null
}>()

const stars = computed(() => Math.round(props.rating ?? 0))
</script>
