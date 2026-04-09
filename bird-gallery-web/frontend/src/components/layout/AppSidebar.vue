<template>
  <aside class="w-48 bg-white border-r border-gray-200 overflow-y-auto shrink-0">
    <nav class="flex flex-col py-2">
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
        active-class="bg-blue-50 text-blue-700 font-medium"
      >
        {{ item.label }}
      </router-link>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'

const authStore = useAuthStore()

const navItems = computed(() => {
  const items = [
    { to: '/gallery', label: '照片库' },
    { to: '/videos', label: '视频' },
    { to: '/bursts', label: '连拍' },
    { to: '/birds', label: '鸟种目录' },
    { to: '/dashboard', label: '仪表盘' },
    { to: '/duplicates', label: '重复照片' },
  ]
  if (authStore.isLoggedIn) {
    items.push({ to: '/upload', label: '上传' })
    items.push({ to: '/batch-process', label: '批量处理' })
  }
  if (authStore.isAdmin) {
    items.push({ to: '/settings', label: '系统设置' })
  }
  return items
})
</script>
