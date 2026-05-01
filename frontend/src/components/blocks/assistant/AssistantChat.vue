<script setup lang="ts">
import {useChatStore} from "@/store/chat";
import {ref, watch, nextTick} from "vue";
import ChatMessage from "@/components/blocks/assistant/ChatMessage.vue";
import FetchingMessage from "@/components/blocks/assistant/FetchingMessage.vue";

const chatStore = useChatStore()

const chatContainer = ref<HTMLElement | null>(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

watch(
  () => chatStore.messages.length,
  scrollToBottom,
  {immediate: true}
)
</script>

<template>
  <div ref="chatContainer" class="assistant-chat">
    <ChatMessage v-for="(m, i) in chatStore.messages"
                 :key="i"
                 :message="m"
    />

    <FetchingMessage v-if="chatStore.isFetching" />
  </div>
</template>

<style scoped lang="scss">
.assistant-chat {
  display: flex;
  flex-direction: column;
  gap: 20px;

  flex-shrink: 1;
  flex-basis: 100%;
  overflow: auto;

  padding-top: 40px;
  padding-bottom: 24px;
}
</style>
