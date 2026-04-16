<script setup lang="ts">

import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import {ref} from "vue";

const value = ref<string>('')
</script>

<template>
  <div class="chat-text-input">
    <textarea class="chat-text-input__textarea"
              placeholder="Планируй с ИИ..."
              v-model="value"
    />

    <div class="chat-text-input__btns">
      <IconBtn icon="arrow-up"
               size="xs"
               :disabled="value === ''"
      />
    </div>

  </div>
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
}
</style>
