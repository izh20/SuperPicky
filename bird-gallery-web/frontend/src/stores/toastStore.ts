import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ToastItem {
  id: string
  message: string
  type: 'info' | 'success' | 'error'
}

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<ToastItem[]>([])

  function add(message: string, type: ToastItem['type'] = 'info', duration = 3000) {
    const id = crypto.randomUUID()
    toasts.value.push({ id, message, type })
    if (duration > 0) setTimeout(() => remove(id), duration)
    return id
  }

  function remove(id: string) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  const success = (msg: string) => add(msg, 'success')
  const error = (msg: string) => add(msg, 'error', 5000)
  const info = (msg: string) => add(msg, 'info')

  return { toasts, add, remove, success, error, info }
})
