<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';

interface Props {
  placeholder?: string;
  modelValue?: string;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: 'Добавьте описание'
});

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>();

const textareaRef = ref<HTMLTextAreaElement | null>(null);

const resize = () => {
  const el = textareaRef.value;
  if (!el) return;

  el.style.height = 'auto';
  const height = el.scrollHeight;

  if (height > 0) {
    el.style.height = `${height}px`;
  }

  el.style.overflow = 'hidden';
};

const onInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement;
  emit('update:modelValue', target.value);
  nextTick(() => resize());
};

onMounted(() => {
  nextTick(() => resize());
});
</script>

<template>
  <label class="text-field">
    <svg class="text-field__icon" width="16" height="16">
      <use href="#description" />
    </svg>

    <textarea
      ref="textareaRef"
      :value="modelValue"
      @input="onInput"
      rows="1"
      class="text-field__textarea"
      :placeholder="placeholder"
    />
  </label>
</template>

<style scoped lang="scss">
.text-field {
  display: flex;
  gap: 8px;

  &:has(:placeholder-shown) {
    & .text-field__icon {
      color: var(--text-primary-disabled);
    }
  }

  &__icon {
    color: var(--text-primary);
  }

  &__textarea {
    width: 100%;
    padding: 0;
    border: none;
    outline: none;
    resize: none;

    font: var(--light-14);
    line-height: 20px;

    box-sizing: border-box;
    overflow: hidden;

    max-height: 130px;

    &::placeholder {
      color: var(--text-primary-disabled);
    }
  }
}
</style>
