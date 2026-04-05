import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import authAPI from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref('')
  const role = ref('')
  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => role.value === 'admin')

  async function login(user: string, pass: string) {
    const res = await authAPI.login(user, pass)
    token.value = res.token
    username.value = res.username
    role.value = res.role
    localStorage.setItem('token', res.token)
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = ''
    localStorage.removeItem('token')
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const res = await authAPI.me()
      username.value = res.username
      role.value = res.role
    } catch {
      logout()
    }
  }

  // 启动时尝试恢复用户信息
  if (token.value) {
    fetchMe()
  }

  return { token, username, role, isLoggedIn, isAdmin, login, logout, fetchMe }
})
