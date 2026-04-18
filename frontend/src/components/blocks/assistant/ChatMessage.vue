<script setup lang="ts">
import {ChatMessageType} from "@/types/chat";

defineProps<{
  message: ChatMessageType
}>()
</script>

<template>
  <div class="chat-message"
       :class="`chat-message--${message.role}`"
  >
    <div>

      <span>{{ message.text }}</span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.chat-message {
  border-radius: 20px;
  padding: 6px 12px;
  max-width: 274px;

  &--user {
    margin-left: auto;
    background: var(--robot-gray);
  }
}
</style>
