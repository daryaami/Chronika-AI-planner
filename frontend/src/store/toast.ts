import { ref } from 'vue'
import { defineStore } from 'pinia'

interface Toast {
  id: string
  message: string
  duration?: number
}

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])
  const defaultDuration = 4000

  const addToast = (message: string, duration?: number) => {
    const id = crypto.randomUUID()
    const toast: Toast = {
      id,
      message,
      duration: duration ?? defaultDuration
    }

    toasts.value.push(toast)

    if (toast.duration && toast.duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, toast.duration)
    }

    return id
  }

  const removeToast = (id: string) => {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index !== -1) {
      toasts.value.splice(index, 1)
    }
  }

  return {
    toasts,
    addToast,
    removeToast
  }
})
