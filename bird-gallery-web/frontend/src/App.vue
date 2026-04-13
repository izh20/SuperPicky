<template>
  <div class="min-h-screen flex flex-col bg-surface-light dark:bg-surface-dark transition-colors">
    <Toast />
    <ProgressOverlay />
    <AppHeader />
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import AppHeader from '@/components/layout/AppHeader.vue'
import Toast from '@/components/common/Toast.vue'
import ProgressOverlay from '@/components/common/ProgressOverlay.vue'
</script>
