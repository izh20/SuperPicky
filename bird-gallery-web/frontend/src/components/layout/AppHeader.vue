<template>
  <header class="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between shrink-0">
    <router-link to="/gallery" class="text-lg font-bold text-gray-800 hover:text-blue-600 transition-colors">
      Bird Gallery
    </router-link>
    <div class="flex items-center gap-3 text-sm">
      <template v-if="authStore.isLoggedIn">
        <span class="text-gray-600">{{ authStore.username }}</span>
        <button
          class="text-gray-500 hover:text-red-500 transition-colors"
          @click="handleLogout"
        >
          退出
        </button>
      </template>
      <router-link
        v-else
        to="/login"
        class="text-blue-600 hover:text-blue-800"
      >
        登录
      </router-link>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const authStore = useAuthStore()
const router = useRouter()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>
