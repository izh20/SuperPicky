<template>
  <div class="min-h-screen flex flex-col bg-gray-50">
    <Toast />
    <AppHeader />
    <div class="flex flex-1 overflow-hidden">
      <AppSidebar />
      <main class="flex-1 overflow-y-auto p-4">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import Toast from '@/components/common/Toast.vue'
</script>
