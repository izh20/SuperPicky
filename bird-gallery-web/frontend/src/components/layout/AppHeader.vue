<template>
  <header class="glass-nav sticky top-0 z-50 h-12 flex items-center px-5 shrink-0">
    <!-- Logo -->
    <router-link
      to="/gallery"
      class="text-white/90 font-semibold text-[14px] tracking-tight hover:text-white transition-colors mr-6 shrink-0"
    >
      Bird Gallery
    </router-link>

    <!-- 导航链接 -->
    <nav class="hidden md:flex items-center gap-1">
      <router-link
        v-for="item in mainNavItems"
        :key="item.to"
        :to="item.to"
        class="px-3 py-1 text-[12px] text-white/80 hover:text-white transition-colors rounded-md"
        active-class="!text-white bg-white/10"
      >
        {{ item.label }}
      </router-link>
    </nav>

    <div class="flex-1" />

    <!-- 右侧工具 -->
    <div class="flex items-center gap-3">
      <!-- 暗色模式切换 -->
      <button
        @click="toggle"
        class="p-1.5 rounded-full text-white/60 hover:text-white hover:bg-white/10 transition-all"
        :title="isDark ? '切换到亮色模式' : '切换到暗色模式'"
      >
        <Moon v-if="!isDark" class="w-4 h-4" />
        <Sun v-else class="w-4 h-4" />
      </button>

      <template v-if="authStore.isLoggedIn">
        <span class="text-[12px] text-white/60">{{ authStore.username }}</span>
        <button
          class="text-[12px] text-white/60 hover:text-white transition-colors"
          @click="handleLogout"
        >
          退出
        </button>
      </template>
      <router-link
        v-else
        to="/login"
        class="text-[12px] text-apple-link-dark hover:text-white transition-colors"
      >
        登录
      </router-link>

      <!-- 移动端汉堡菜单 -->
      <button
        @click="mobileMenuOpen = !mobileMenuOpen"
        class="md:hidden p-1.5 text-white/80 hover:text-white"
      >
        <X v-if="mobileMenuOpen" class="w-5 h-5" />
        <Menu v-else class="w-5 h-5" />
      </button>
    </div>

    <!-- 移动端全屏菜单 -->
    <Teleport to="body">
      <Transition name="menu-fade">
        <div
          v-if="mobileMenuOpen"
          class="fixed inset-0 z-40 glass-nav pt-14 px-6 md:hidden"
          @click.self="mobileMenuOpen = false"
        >
          <nav class="flex flex-col gap-1">
            <router-link
              v-for="item in allNavItems"
              :key="item.to"
              :to="item.to"
              class="px-4 py-3 text-[17px] text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              active-class="!text-white bg-white/10"
              @click="mobileMenuOpen = false"
            >
              {{ item.label }}
            </router-link>
          </nav>
        </div>
      </Transition>
    </Teleport>
  </header>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Moon, Sun, Menu, X } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/authStore'
import { useDarkMode } from '@/composables/useDarkMode'

const authStore = useAuthStore()
const router = useRouter()
const { isDark, toggle } = useDarkMode()
const mobileMenuOpen = ref(false)

const mainNavItems = computed(() => {
  const items = [
    { to: '/gallery', label: '照片库' },
    { to: '/videos', label: '视频' },
    { to: '/bursts', label: '连拍' },
    { to: '/birds', label: '鸟种目录' },
    { to: '/dashboard', label: '仪表盘' },
  ]
  if (authStore.isLoggedIn) {
    items.push({ to: '/upload', label: '上传' })
  }
  if (authStore.isAdmin) {
    items.push({ to: '/settings', label: '系统设置' })
  }
  return items
})

const allNavItems = computed(() => {
  const items = [
    ...mainNavItems.value,
    { to: '/duplicates', label: '重复照片' },
  ]
  if (authStore.isLoggedIn) {
    items.push({ to: '/batch-process', label: '批量处理' })
  }
  if (authStore.isAdmin) {
    items.push({ to: '/settings', label: '系统设置' })
  }
  return items
})

function handleLogout() {
  authStore.logout()
  mobileMenuOpen.value = false
  router.push('/login')
}
</script>

<style scoped>
.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 0.2s ease;
}
.menu-fade-enter-from,
.menu-fade-leave-to {
  opacity: 0;
}
</style>
