<script setup lang="ts">
import { ref, watch } from "vue";

const props = defineProps<{
  modelValue?: string;
}>();

const emit = defineEmits<{
  submit: [value: string];
  'update:modelValue': [value: string];
}>();

const value = ref<string>(props.modelValue ?? '');

watch(() => props.modelValue, (newVal) => {
  if (newVal !== undefined) value.value = newVal;
});

const handleSubmit = (e: Event) => {
  e.preventDefault();
  if (value.value.trim()) {
    emit('submit', value.value);
    value.value = '';
  }
};

const handleKeydown = (e: KeyboardEvent) => {
  // Отправка на Enter без модификаторов
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    handleSubmit(e);
    return;
  }

  // Перенос строки на Shift+Enter, Ctrl+Enter, Cmd+Enter
  if (e.key === 'Enter' && (e.shiftKey || e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    const start = (e.target as HTMLTextAreaElement).selectionStart;
    const end = (e.target as HTMLTextAreaElement).selectionEnd;
    value.value = value.value.slice(0, start) + '\n' + value.value.slice(end);
  }
};
</script>

<template>
  <form class="chat-text-input" @submit="handleSubmit">
    <textarea class="chat-text-input__textarea"
              placeholder="Планируй с ИИ..."
              v-model="value"
              @keydown="handleKeydown"
    />

    <div class="chat-text-input__btns">
      <button type="submit"
              :disabled="value.trim() === ''"
              class="chat-text-input__submit-btn"
      >
        <svg width="16" height="16">
          <use href="#arrow-up"></use>
        </svg>
      </button>
    </div>

  </form>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins' as *;

.chat-text-input {
  position: relative;

  &__textarea {
    width: 100%;
    height: 82px;
    resize: none;
    border: 1px solid var(--stroke-primary-invisible);
    border-radius: 8px;
    outline: none;
    background: transparent;
    display: block;
    caret-color: var(--bg-accent);
    font: var(--light-14);
    padding: 7px 8px;

    &::placeholder {
      color: var(--text-tertiary);
    }

    &:focus {
      border-color: var(--bg-accent);
    }
  }

  &__btns {
    position: absolute;
    bottom: 8px;
    right: 8px;
  }

  &__submit-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  }
}
</style>
