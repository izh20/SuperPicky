<template>
  <div class="flex flex-col items-center justify-center py-16 text-text-tertiary dark:text-text-on-dark-tertiary">
    <component :is="icon" v-if="icon" class="w-12 h-12 mb-4" />
    <p class="text-lg font-medium text-text-secondary dark:text-text-on-dark-secondary">{{ title }}</p>
    <p v-if="description" class="mt-1 text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary">{{ description }}</p>
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
