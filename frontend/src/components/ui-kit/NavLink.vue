<script setup lang="ts">
import {computed} from "vue";
import {RouterLink} from "vue-router";

const props = withDefaults(defineProps<{
  tag?: 'button' | 'a',
  to?: string,
  text: string,
  leftIcon?: string,
  rightIcon?: string,
  color?: string,
  type?: 'error',
}>(), {
  tag: 'button'
})

const component = computed(() => {
  if (props.to) return RouterLink
  return props.tag as string
})

const computedIconColor = computed(() => {
  if (!props.color) return null

  return `color: ${props.color}`
})
</script>

<template>
  <component :is="component"
             :to="to"
             :class="`nav-link${type ? ` nav-link--${type}` : ''}`">
    <svg v-if="leftIcon" width="18" height="18"
         :style="computedIconColor"

    >
      <use :href="`#${leftIcon}`"></use>
    </svg>

    <span class="nav-link__label">{{ text }}</span>

    <svg class="nav-link__right-icon"
         v-if="rightIcon"
         width="18"
         height="18">
      <use :href="`#${rightIcon}`"></use>
    </svg>
  </component>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins' as *;

.nav-link {
  padding: 5px 6px;

  background: transparent;
  border: none;
  outline: none;

  font: var(--light-14);

  display: flex;
  align-items: center;
  gap: 4px;

  cursor: pointer;

  @include hover {
    background: var(--bg-secondary);
  }

  &--error {
    color: var(--text-error);

    @include hover {
      background: transparent;
    }
  }

  &__label {
    display: block;
    white-space: nowrap;
  }

  &__right-icon {
    margin-left: auto;
  }
}
</style>
