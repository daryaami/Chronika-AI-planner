<script setup lang="ts">
withDefaults(defineProps<{
  tag?: 'button' | 'a',
  icon?: string
}>(), {
  icon: 'placeholder',
  tag: 'button'
})
</script>

<template>
<component :is="tag" class="round-icon-button">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <use :href="`#${icon}`"></use>
  </svg>
</component>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins' as *;

.round-icon-button {
  padding: 0;
  border: none;
  background: var(--bg-highlight);

  display: flex;
  align-items: center;
  justify-content: center;

  width: 40px;
  height: 40px;
  border-radius: 50%;

  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.07);

  cursor: pointer;

  @include hover {
    color: var(--icon-primary-hover);
  }

  & svg {
    display: block;
    width: 18px;
    height: 18px;
  }
}
</style>
