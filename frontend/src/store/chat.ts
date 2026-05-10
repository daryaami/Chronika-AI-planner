import {defineStore} from "pinia";
import {ref} from "vue";
import {ChatMessageType, ChatMessageBlock} from "@/types/chat";
import {useAuthStore} from "@/store/auth";
import {BASE_API_URL} from "@/config";
import {useToastStore} from "@/store/toast";
import {applyAssistantMutationResults} from "@/utils/assistantMutations";

function normalizeAssistantResponse(data: Record<string, unknown>): ChatMessageType {
  const blocks = Array.isArray(data.blocks) ? data.blocks as ChatMessageBlock[] : undefined
  const textBlock = blocks?.find((b) => b.type === 'text')
  const content =
    typeof data.content === 'string' ? data.content : (textBlock?.text ?? '')
  return {
    message_id: String(data.message_id ?? ''),
    role: data.role === 'user' || data.role === 'assistant' ? data.role : 'assistant',
    content,
    created_at: data.created_at as Date | undefined,
    blocks,
    state: typeof data.state === 'string' ? data.state : undefined,
    result: Array.isArray(data.result) ? data.result as ChatMessageType['result'] : undefined,
  }
}

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
    const lastAssistantMsg = [...messages.value].reverse().find(
      (m) => m.role === 'assistant' && m.message_id && m.message_id !== 'message_id'
    )

    const userMessage = createUserMessage(text)

    messages.value.push(userMessage)
    isFetching.value = true;

    const payload: Record<string, unknown> = {message: text}
    if (lastAssistantMsg) {
      payload.client_context = {message_id: lastAssistantMsg.message_id}
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
      const responseData = normalizeAssistantResponse(await response.json() as Record<string, unknown>)
      messages.value.push(responseData)
      applyAssistantMutationResults(responseData.result)
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
      const responseData = normalizeAssistantResponse(await response.json() as Record<string, unknown>)
      messages.value.push(responseData)
      applyAssistantMutationResults(responseData.result)
    } else {
      toastStore.addToast('Произошла ошибка при обработке сообщения😔 Попробуйте ещё раз', 3000)
    }
  }

  const updateEntity = async (messageId: string, contextId: string, fields: Record<string, any>) => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/action/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message_id: messageId,
          action: {
            type: 'entity_update',
            payload: {
              context_id: contextId,
              fields
            }
          }
        })
      })

    isFetching.value = true;

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    isFetching.value = false;
    if (response.ok) {
      const responseData = normalizeAssistantResponse(await response.json() as Record<string, unknown>)
      messages.value.push(responseData)
      applyAssistantMutationResults(responseData.result)
    } else {
      toastStore.addToast('Произошла ошибка при обновлении события😔 Попробуйте ещё раз', 3000)
    }
  }

  const selectEntity = async (messageId: string, contextIds: string[]) => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/action/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message_id: messageId,
          action: {
            type: 'select_entity',
            payload: {
              context_ids: contextIds
            }
          }
        })
      })

    isFetching.value = true;

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    isFetching.value = false;
    if (response.ok) {
      const responseData = normalizeAssistantResponse(await response.json() as Record<string, unknown>)
      messages.value.push(responseData)
      applyAssistantMutationResults(responseData.result)
    } else {
      toastStore.addToast('Произошла ошибка при выборе события😔 Попробуйте ещё раз', 3000)
    }
  }

  const selectTimeSlot = async (messageId: string, contextId: string, slot: { start: string, end: string }) => {
    const fetchFn = () =>
      fetch(`${BASE_API_URL}/assistant/action/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message_id: messageId,
          action: {
            type: 'select_time_slot',
            payload: {
              context_id: contextId,
              slot
            }
          }
        })
      })

    isFetching.value = true;

    const response = await authStore.ensureAuthorizedRequest(fetchFn)

    isFetching.value = false;
    if (response.ok) {
      const responseData = normalizeAssistantResponse(await response.json() as Record<string, unknown>)
      messages.value.push(responseData)
      applyAssistantMutationResults(responseData.result)
    } else {
      toastStore.addToast('Произошла ошибка при выборе времени😔 Попробуйте ещё раз', 3000)
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
    updateEntity,
    selectEntity,
    selectTimeSlot,
    clearHistory,
  }
})
