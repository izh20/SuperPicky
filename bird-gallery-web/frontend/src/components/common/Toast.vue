<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-50 flex flex-col gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="t in toastStore.toasts"
          :key="t.id"
          class="px-4 py-3 rounded-lg shadow-lg text-white text-sm max-w-sm cursor-pointer"
          :class="bgClass(t.type)"
          @click="toastStore.remove(t.id)"
        >
          {{ t.message }}
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToastStore } from '@/stores/toastStore'

const toastStore = useToastStore()

function bgClass(type: string) {
  if (type === 'success') return 'bg-green-600'
  if (type === 'error') return 'bg-red-600'
  return 'bg-gray-700'
}
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(40px);
}
</style>
