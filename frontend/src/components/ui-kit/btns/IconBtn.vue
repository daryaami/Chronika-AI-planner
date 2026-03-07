<script setup lang="ts">
import {UISize} from "@/types/UISize";

withDefaults(defineProps<{
  icon?: string,
  size?: UISize,
  disabled?: boolean,
  variant?: 'accent' | null,
}>(), {
  icon: 'placeholder',
  size: 'm',
  disabled: false,
  variant: null,
})

</script>

<template>
<button class="icon-button"
        :class="`icon-button--${size}${variant ? ` icon-button--${variant}` : ''}`"
        :disabled="disabled">
  <svg width="24" height="24">
    <use :href="`#${icon}`"></use>
  </svg>
</button>
</template>

<style lang="scss">
@use '@/assets/scss/mixins/resets' as *;
@use '@/assets/scss/mixins/mixins' as *;

.icon-button {
  @include reset-button;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--icon-primary);
  transition: .15s;

  @include hover {
    color: var(--bg-accent-secondary);
  }

  & svg {
    display: block;
    width: 100%;
    height: 100%;
  }

  &--l {
    width: 32px;
    height: 32px;
  }

  &--m {
    width: 24px;
    height: 24px;
  }

  &--s {
    width: 18px;
    height: 18px;
  }

  &--xs {
    width: 16px;
    height: 16px;
  }

  &--xxs {
    width: 12px;
    height: 12px;
  }

  &--accent {
    color: var(--icon-hover);
  }

  &:disabled {
    color: var(--icon-disabled);
    cursor: default;
  }
}
</style>
