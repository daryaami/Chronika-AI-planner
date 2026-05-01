<script setup lang="ts">
import AssistantIcon from "@/components/blocks/assistant/AssistantIcon.vue";
import { ref, onMounted, onUnmounted } from "vue";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import { useClickOutside } from "@/components/composables/useClickOutside";
import ChatTextInput from "@/components/ui-kit/inputs/ChatTextInput.vue";
import {useChatStore} from "@/store/chat";
import AssistantChat from "@/components/blocks/assistant/AssistantChat.vue";
import IconText from "@/components/ui-kit/links/IconText.vue";

const isOpen = ref<boolean>(false);
const bodyRef = ref<HTMLElement | null>(null);

useClickOutside(bodyRef, () => {
  if (isOpen.value) isOpen.value = false;
});

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === "Escape" && isOpen.value) {
    isOpen.value = false;
  }
};


const open = () => {
  if (isOpen.value) return;

  isOpen.value = true;

  if (!chatStore.messages.length) {
    chatStore.fetchHistory().then()
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
});

// Chat
const chatStore = useChatStore()

const messageSubmitHandler = (message: string) => {
  chatStore.sendMessage(message);
}
</script>

<template>
  <div class="assistant-window"
       ref="bodyRef"
       :class="`${isOpen ? 'is-open' : ''}`" >

    <div class="assistant-window__body">
      <div class="assistant-window__body-header">
        <IconText leftIcon="cross"
                  variant="tertiary"
                  size="s"
                  text="Очистить чат"
                  v-if="chatStore.messages.length"
                  @click="chatStore.clearHistory"
        />

        <IconBtn class="assistant-window__close"
                 icon="hide"
                 size="s"
                 @click="isOpen = false"
        />
      </div>

      <div v-if="!chatStore.messages.length">
        <span class="assistant-window__title">Твой ассистент на связи!</span>
        <div class="assistant-window__examples">
          <div class="assistant-window__example">
            <svg width="18" height="18">
              <use href="#task"></use>
            </svg>
            <span class="assistant-window__example-text">Создай задачу</span>
          </div>

          <div class="assistant-window__example">
            <svg width="18" height="18">
              <use href="#calendar"></use>
            </svg>
            <span class="assistant-window__example-text">Запланируй встречу</span>
          </div>

          <div class="assistant-window__example">
            <svg width="18" height="18">
              <use href="#clock"></use>
            </svg>
            <span class="assistant-window__example-text">Перенеси на другое время</span>
          </div>

          <div class="assistant-window__example">
            <svg width="18" height="18">
              <use href="#delete"></use>
            </svg>
            <span class="assistant-window__example-text">Удали задачу</span>
          </div>
        </div>
      </div>

      <AssistantChat v-else />

      <ChatTextInput class="assistant-window__input"
                     @submit="messageSubmitHandler"
      />
    </div>
    <AssistantIcon class="assistant-window__icon"
                   :class="isOpen && chatStore.messages.length ? 'hidden' : ''"
                   @click="open"
    />

  </div>
</template>

<style scoped lang="scss">
.assistant-window {
  &.is-open {
    opacity: 1;

    & .assistant-window__body {
      opacity: 1;
      width: 460px;
      height: 460px;
    }

    & .assistant-window__icon {
      right: 386px;
      bottom: 320px;
      cursor: default;
      animation: float 3s ease-in-out infinite;
    }
  }

  &__body {
    opacity: 0;
    transition: 0.3s;
    width: 0;
    height: 0;

    background-color: var(--bg-primary);
    box-shadow: 0 0 6px 0 rgba(0, 0, 0, 0.07);

    overflow: hidden;
    border-radius: 15px;

    padding: 20px;

    position: relative;

    display: flex;
    flex-direction: column;
  }

  &__icon {
    position: absolute;
    right: 0;
    bottom: 0;

    transition: right .3s, bottom .3s;

    &.hidden {
      opacity: 0;
      pointer-events: none;
    }
  }

  &__body-header {
    display: flex;
    align-items: center;

    margin-bottom: 20px;
    padding-left: 12px;
  }

  &__close {
    margin-left: auto;
  }

  &__title {
    font: var(--bold-18);

    margin-top: 100px;
    margin-bottom: 18px;
    display: block;
  }

  &__examples {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  &__example {
    display: flex;
    gap: 6px;
    align-items: center;

    & svg {
      display: block;

      font: var(--light-14);
    }
  }

  &__input {
    margin-top: auto;
  }
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}
</style>
