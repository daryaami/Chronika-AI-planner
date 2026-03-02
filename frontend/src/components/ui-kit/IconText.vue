<script setup lang="ts">
import {UISize} from "@/types/UISize";
import {UIWeight} from "@/types/UIWeight";
withDefaults(defineProps<{
  size?: UISize,
  tag?: 'button' | 'a',
  weight?: UIWeight,
  leftIcon?: string,
  text?: string,
  rightIcon?: string
  type?: 'accent' | null,
}>(), {
  size: 'm',
  tag: 'button',
  weight: 'reg'
})
</script>

<template>
  <component :is="tag"
             class="icon-text"
             :class="`icon-text--${size} icon-text--${weight} ${type ? `icon-text--${type}` : ''}`">
    <svg v-if="leftIcon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <use :href="`#${leftIcon}`"></use>
    </svg>

    <span v-if="text">{{ text }}</span>

    <svg v-if="rightIcon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <use :href="`#${rightIcon}`"></use>
    </svg>
  </component>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins.scss' as *;

.icon-text {
  padding: 0;
  background: transparent;
  border: none;

  display: flex;
  align-items: center;
  gap: 10px;

  cursor: pointer;

  @include hover {
    color: var(--text-primary-hover);

    & svg {
      color: var(--icon-primary-hover);
    }
  }

  & svg {
    display: block;
  }

  &--m {
    font: var(--light-14);
    gap: 5px;

    & svg {
      width: 18px;
      height: 18px;
    }
  }

  &--l {
    font: var(--bold-18);

    & svg {
      display: block;
      width: 16px;
      height: 16px;
    }
  }

  &--bold {
    font-weight: 400;
    gap: 6px;
  }

  &--accent {
    color: var(--text-primary-hover);
  }
}
</style>
