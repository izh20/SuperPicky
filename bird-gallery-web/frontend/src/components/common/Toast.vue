<template>
  <Teleport to="body">
    <div class="fixed top-14 right-4 z-50 flex flex-col gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="t in toastStore.toasts"
          :key="t.id"
          class="px-4 py-3 rounded-xl text-white text-sm max-w-sm cursor-pointer font-text"
          :class="bgClass(t.type)"
          style="box-shadow: rgba(0, 0, 0, 0.22) 3px 5px 30px 0px;"
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
  if (type === 'success') return 'bg-emerald-600'
  if (type === 'error') return 'bg-red-600'
  return 'bg-text-primary dark:bg-surface-card-dark'
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
