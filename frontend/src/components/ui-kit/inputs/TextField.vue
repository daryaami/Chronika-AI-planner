<script setup lang="ts">
import { useAutoHeightTextarea } from "@/components/composables/useAutoHeightTextarea";

interface Props {
  placeholder?: string;
}

withDefaults(defineProps<Props>(), {
  placeholder: 'Добавьте описание'
});

const { textareaRef, value, resize } = useAutoHeightTextarea();
</script>

<template>
  <label class="text-field">
    <svg class="text-field__icon" width="16" height="16">
      <use href="#description" />
    </svg>

    <textarea
      ref="textareaRef"
      v-model="value"
      rows="1"
      class="text-field__textarea"
      :placeholder="placeholder"
      @input="resize"
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
