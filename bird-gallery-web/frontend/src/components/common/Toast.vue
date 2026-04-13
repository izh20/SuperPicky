<template>
  <Teleport to="body">
    <!-- 桌面端：右上角 -->
    <div class="hidden sm:flex fixed top-14 right-4 z-[100] flex-col gap-2">
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
    <!-- 移动端：底部居中，更醒目 -->
    <div class="sm:hidden fixed bottom-6 left-4 right-4 z-[100] flex flex-col items-center gap-2">
      <TransitionGroup name="toast-mobile">
        <div
          v-for="t in toastStore.toasts"
          :key="t.id"
          class="w-full px-4 py-3.5 rounded-2xl text-white text-[15px] text-center font-medium cursor-pointer font-text backdrop-blur-lg"
          :class="bgClassMobile(t.type)"
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

function bgClassMobile(type: string) {
  if (type === 'success') return 'bg-emerald-600/95'
  if (type === 'error') return 'bg-red-600/95'
  return 'bg-black/80 dark:bg-white/20'
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

.toast-mobile-enter-active,
.toast-mobile-leave-active {
  transition: all 0.3s ease;
}
.toast-mobile-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.toast-mobile-leave-to {
  opacity: 0;
  transform: translateY(20px);
}
</style>
