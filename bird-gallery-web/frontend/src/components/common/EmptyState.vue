<template>
  <div class="flex flex-col items-center justify-center py-16 text-gray-400">
    <component :is="icon" v-if="icon" class="w-12 h-12 mb-4" />
    <p class="text-lg font-medium text-gray-500">{{ title }}</p>
    <p v-if="description" class="mt-1 text-sm text-gray-400">{{ description }}</p>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  title: string
  description?: string
  icon?: Component
}>()
</script>
