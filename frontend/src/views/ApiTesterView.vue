<script setup lang="ts">
import { ref } from 'vue'
import { BASE_API_URL } from '../config'
import { useAuthStore } from '../store/auth'

const authStore = useAuthStore()

const method = ref('POST')
const endpoint = ref('/assistant/message/')
const requestBody = ref('{\n  "message": ""\n}')
const isLoading = ref(false)

const response = ref<{
  status: number
  statusText: string
  time: number
  data: unknown
} | null>(null)

const error = ref<string | null>(null)

const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

const getStatusClass = (status: number) => {
  if (status >= 200 && status < 300) return 'api-tester__status--success'
  if (status >= 300 && status < 400) return 'api-tester__status--redirect'
  if (status >= 400 && status < 500) return 'api-tester__status--client-error'
  if (status >= 500) return 'api-tester__status--server-error'
  return 'api-tester__status--info'
}

const formatJson = (data: unknown): string => {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

const sendRequest = async () => {
  isLoading.value = true
  error.value = null
  response.value = null

  const url = `${BASE_API_URL}${endpoint.value.startsWith('/') ? endpoint.value : '/' + endpoint.value}`
  const startTime = performance.now()

  try {
    const fetchOptions: RequestInit = {
      method: method.value,
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include'
    }

    const token = authStore.getAccessToken()
    if (token) {
      fetchOptions.headers = {
        ...fetchOptions.headers,
        'Authorization': `JWT ${token}`
      }
    }

    if (requestBody.value.trim()) {
      fetchOptions.body = requestBody.value
    }

    const res = await fetch(url, fetchOptions)
    const endTime = performance.now()
    const time = Math.round(endTime - startTime)

    let data: unknown
    const contentType = res.headers.get('content-type')
    if (contentType && contentType.includes('application/json')) {
      data = await res.json()
    } else {
      data = await res.text()
    }

    response.value = {
      status: res.status,
      statusText: res.statusText,
      time,
      data
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error occurred'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="api-tester">
    <h1 class="api-tester__title">API Tester</h1>

    <form class="api-tester__form" @submit.prevent="sendRequest">
      <div class="api-tester__row">
        <select v-model="method" class="api-tester__method">
          <option v-for="m in methods" :key="m" :value="m">{{ m }}</option>
        </select>
        <input
          v-model="endpoint"
          type="text"
          class="api-tester__endpoint"
          placeholder="/endpoint/path/"
          required
        >
      </div>

      <div>
        <label class="api-tester__label">Request Body (JSON)</label>
        <textarea
          v-model="requestBody"
          class="api-tester__body"
          placeholder='{ "key": "value" }'
        ></textarea>
      </div>

      <button type="submit" class="api-tester__submit" :disabled="isLoading">
        {{ isLoading ? 'Sending...' : 'Send Request' }}
      </button>
    </form>

    <div v-if="error" class="api-tester__error">
      Error: {{ error }}
    </div>

    <div v-if="response" class="api-tester__response">
      <div class="api-tester__response-header">
        <span :class="['api-tester__status', getStatusClass(response.status)]">
          {{ response.status }} {{ response.statusText }}
        </span>
        <span class="api-tester__time">{{ response.time }}ms</span>
      </div>
      <div class="api-tester__response-body">
        <pre>{{ formatJson(response.data) }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import '../assets/api-tester.css';
</style>
