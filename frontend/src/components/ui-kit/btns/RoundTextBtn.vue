<script setup lang="ts">
defineProps({
  text: {
    type: String,
  },
  icon: {
    type: String,
  },
  type: {
    type: String,
    default: 'button',
  }
})
</script>

<template>
<button class="round-text-btn">
  <span class="round-text-btn__text">{{ text }}</span>
  <svg v-if="icon" class="round-text-btn__icon" width="14" height="14">
    <use :href="`#${icon}`"></use>
  </svg>
</button>

</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/resets' as *;
@use '@/assets/scss/mixins/mixins' as *;

.round-text-btn {
  @include reset-button;
  font: var(--bold-14);
  color: var(--text-primary-muted);
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 20px;
  height: 40px;
  padding: 0 15px;
  border: 1px solid var(--bg-primary-hover);
  background-color: var(--bg-highlight);
  transition: .15s;

  @include hover {
    border-color: var(--bg-primary-hover);
    background-color: var(--bg-primary-hover);
  }

  & span {
    display: block;
  }

  & svg {
    display: block;
    width: 14px;
    height: 14px;
  }
}
</style>
