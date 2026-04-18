import {defineStore} from "pinia";
import {ref} from "vue";
import {ChatMessageType} from "@/types/chat";

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessageType[]>([]);
  const isFetching = ref(false);

  const createUserMessage = (message: string): ChatMessageType => {
    return {
      text: message,
      role: 'user',
      type: 'text',
    }
  }

  const sendMessage = (text: string) => {
    const userMessage = createUserMessage(text)


    messages.value.push(userMessage)

    isFetching.value = true;

    setTimeout(() => {
      isFetching.value = false;
    }, 2000)
  }

  return {
    messages,
    sendMessage
  }
})
