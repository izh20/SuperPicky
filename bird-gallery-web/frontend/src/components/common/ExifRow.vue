<template>
  <tr v-if="value">
    <td class="py-1 pr-4 text-sm text-gray-500 whitespace-nowrap">{{ label }}</td>
    <td class="py-1 text-sm text-gray-800">{{ value }}</td>
  </tr>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value?: string | null
}>()
</script>
