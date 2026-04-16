<script setup lang="ts">
import AssistantIcon from "@/components/blocks/assistant/AssistantIcon.vue";
import { ref, onMounted, onUnmounted } from "vue";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import { useClickOutside } from "@/components/composables/useClickOutside";
import ChatTextInput from "@/components/ui-kit/inputs/ChatTextInput.vue";

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

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <div class="assistant-window"
       ref="bodyRef"
       :class="`${isOpen ? 'is-open' : ''}`" >

    <div class="assistant-window__body">
      <IconBtn class="assistant-window__close"
          icon="hide"
          size="s"
          @click="isOpen = false"
      />
      <div>
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

      <ChatTextInput class="assistant-window__input" />
    </div>
    <AssistantIcon class="assistant-window__icon"
                   @click="isOpen = true" />

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
  }

  &__close {
    position: absolute;
    top: 26px;
    right: 20px;
  }

  &__title {
    font: var(--bold-18);

    margin-top: 138px;
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
