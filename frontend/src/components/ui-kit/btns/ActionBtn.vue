<script setup lang="ts">
defineProps<{
  text: string
  variant?: 'primary' | 'secondary'
  type?: 'button' | 'submit' | 'reset'
}>()

defineEmits<{
  (e: 'click'): void
}>()
</script>

<template>
  <button
    class="action-btn"
    :class="`action-btn--${variant || 'primary'}`"
    :type="type || 'button'"
    @click="$emit('click')"
  >
    {{ text }}
  </button>
</template>

<style lang="scss" scoped>
@use '@/assets/scss/mixins/mixins' as *;

.action-btn {
  padding: 5px 12px;

  font: var(--light-16);

  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;

  &--secondary {
    color: #374151;
    background: #ffffff;
    border-color: #d1d5db;

    @include hover {
      background: var(--bg-primary-hover);
    }
  }

  &--primary {
    color: #ffffff;
    background: #3b82f6;
    border-color: #3b82f6;

    &[disabled] {
      opacity: .4;
      cursor: default;
    }
  }
}
</style>
