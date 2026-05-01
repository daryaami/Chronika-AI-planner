<script setup lang="ts">
import {ChatMessageType} from "@/types/chat";
import {formatDueDate} from "@/components/js/time-utils";
import ActionBtn from "@/components/ui-kit/btns/ActionBtn.vue";
import {useChatStore} from "@/store/chat";

const props = defineProps<{
  message: ChatMessageType
}>()

const chatStore = useChatStore()

const getTextForEvent = (fields: any) => {
  return `<b>${fields.summary}</b><br>${formatDueDate(new Date(fields.start))} — ${new Date(fields.end).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;
}

const confirmMessage = () => {
  chatStore.confirmMessage(props.message.message_id)
}
</script>

<template>
  <div class="chat-message"
       :class="`chat-message--${message.role}`"
  >
    <div
         v-if="message.blocks?.length"
         v-for="(b, i) in message.blocks"
         :key="i">
      <span class="chat-message__block"
            v-if="b.type === 'text'">{{ b.text }}</span>

      <div class="chat-message__block"
           v-if="b.type === 'entity' && b.entity_type === 'event'">
        <span v-html="getTextForEvent(b.fields)"></span>

        <div class="chat-message__buttons"
             v-if="b.mode === 'editable'">
          <ActionBtn text="Да"
                     variant="secondary"
                     type="button"
                     @click="confirmMessage"
          />

          <ActionBtn text="Изменить"
                     variant="secondary"
                     type="button"
          />
        </div>
      </div>

    </div>

    <div v-else>
      <span>{{ message.content }}</span>
    </div>

  </div>
</template>

<style scoped lang="scss">
.chat-message {
  border-radius: 20px;
  padding: 6px 12px;
  max-width: 274px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 24px;

  &:not(:last-child) {
    & .chat-message__buttons {
      display: none;
    }
  }

  &__buttons {
    display: flex;
    gap: 10px;

    margin-top: 24px;
  }

  &--user {
    margin-left: auto;
    background: var(--robot-gray);
  }
}
</style>
