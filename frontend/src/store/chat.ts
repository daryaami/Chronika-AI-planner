import {defineStore} from "pinia";
import {ref} from "vue";
import {ChatMessageType} from "@/types/chat";
import {useAuthStore} from "@/store/auth";
import {BASE_API_URL} from "@/config";
import {useToastStore} from "@/store/toast";

export const useChatStore = defineStore('chat', () => {
  const authStore = useAuthStore()
  const toastStore = useToastStore()

  const messages = ref<ChatMessageType[]>([]);
  const isFetching = ref(false);

  const fetchHistory = async () => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/history/`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
        }
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    if (response.ok) {
      const data = await response.json()
      messages.value = data.messages as ChatMessageType[];
    } else {
      toastStore.addToast('Не удалось загрузить историю сообщений😔', 3000)
    }
  }

  const createUserMessage = (message: string): ChatMessageType => {
    return {
      message_id: 'message_id',
      content: message,
      role: 'user',
      blocks: [
        {
          type: 'text',
          text: message,
        }
      ]
    }
  }

  const sendMessage = async (text: string) => {
    const userMessage = createUserMessage(text)

    messages.value.push(userMessage)
    isFetching.value = true;

    const payload = {
      message: text
    }

    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/message/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    isFetching.value = false;

    if (response.ok) {
      const responseData = await response.json() as ChatMessageType
      messages.value.push(responseData)
    } else {
      toastStore.addToast('Произошла ошибка при обработке сообщения😔 Попробуйте ещё раз', 3000)
    }
  }

  const confirmMessage = async (id: string) => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/action/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body:JSON.stringify({
          message_id: id,
          action: {
            type: 'confirm'
          }
        })
      })

    isFetching.value = true;

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    isFetching.value = false;
    if (response.ok) {
      const responseData = await response.json() as ChatMessageType
      messages.value.push(responseData)
    } else {
      toastStore.addToast('Произошла ошибка при обработке сообщения😔 Попробуйте ещё раз', 3000)
    }
  }

  const clearHistory = async () => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/clear/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    if (response.ok) {
      messages.value = [];
    } else {
      toastStore.addToast('Произошла ошибка при очистке истории😔 Попробуйте ещё раз', 3000)
    }
  }

  return {
    isFetching,
    messages,
    sendMessage,
    fetchHistory,
    confirmMessage,
    clearHistory,
  }
})
