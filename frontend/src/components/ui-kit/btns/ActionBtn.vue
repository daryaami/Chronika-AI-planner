<script setup lang="ts">
defineProps<{
  text: string
  type?: 'primary' | 'secondary'
}>()

defineEmits<{
  (e: 'click'): void
}>()
</script>

<template>
  <button
    class="action-btn"
    :class="`action-btn--${type || 'primary'}`"
    type="button"
    @click="$emit('click')"
  >
    {{ text }}
  </button>
</template>

<style lang="scss" scoped>
.action-btn {
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;

  &--secondary {
    color: #374151;
    background: #ffffff;
    border-color: #d1d5db;
  }

  &--primary {
    color: #ffffff;
    background: #3b82f6;
    border-color: #3b82f6;
  }
}
</style>
