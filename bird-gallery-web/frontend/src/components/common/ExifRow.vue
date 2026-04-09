<template>
  <tr v-if="value">
    <td class="py-1 pr-4 text-[14px] text-text-tertiary dark:text-text-on-dark-tertiary whitespace-nowrap">{{ label }}</td>
    <td class="py-1 text-[14px] text-text-primary dark:text-text-on-dark">{{ value }}</td>
  </tr>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value?: string | null
}>()
</script>
