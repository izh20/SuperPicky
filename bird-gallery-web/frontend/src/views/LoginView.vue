<template>
  <div class="min-h-[calc(100vh-48px)] flex items-center justify-center">
    <div class="card-apple dark:bg-[#1c1c1e] rounded-xl p-8 w-full max-w-sm">
      <div class="flex items-center justify-center gap-2 mb-6">
        <Bird class="w-8 h-8 text-apple-blue" />
        <h1 class="text-xl font-bold text-text-primary dark:text-text-on-dark">Bird Gallery</h1>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">用户名</label>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            required
            class="w-full px-3 py-2 bg-surface-light dark:bg-white/10 rounded-lg border-none outline-none focus:ring-2 focus:ring-apple-blue/30 text-text-primary dark:text-text-on-dark"
            placeholder="请输入用户名"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">密码</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="w-full px-3 py-2 bg-surface-light dark:bg-white/10 rounded-lg border-none outline-none focus:ring-2 focus:ring-apple-blue/30 text-text-primary dark:text-text-on-dark"
            placeholder="请输入密码"
          />
        </div>

        <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>

        <button
          type="submit"
          :disabled="loading"
          class="btn-primary w-full"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Bird } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await authStore.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/gallery'
    router.replace(redirect)
  } catch (e: any) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>
