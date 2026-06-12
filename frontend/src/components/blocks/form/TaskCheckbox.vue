<script setup lang="ts">
const model = defineModel<Boolean>()

interface Props {
  priority: string
}

defineProps<Props>()
</script>

<template>
  <label :class="`task-checkbox task-checkbox--${priority}`">
    <input type="checkbox"
           class="visually-hidden"
           v-model="model"
    >
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="15" height="15" rx="7.5" fill="currentColor" />
      <rect x="0.5" y="0.5" width="14" height="14" rx="7" stroke="currentColor" />
      <path d="M6.42133 11.7071L4.10128 9.38706C3.88744 9.17322 3.94594 8.81272 4.21643 8.67748C4.34893 8.61123 4.50577 8.61558 4.63439 8.68908L6.24521 9.60955C6.71753 9.87945 7.31896 9.72228 7.59885 9.2558L10.4395 4.52145C10.4939 4.43079 10.5789 4.36258 10.6792 4.32915C11.0496 4.20567 11.387 4.58718 11.2191 4.93974L8.12855 11.4299C7.96272 11.7782 7.61139 12 7.22568 12H7.12844C6.86322 12 6.60887 11.8947 6.42133 11.7071Z" fill="#FCFCFC" />
    </svg>
  </label>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins.scss' as *;

.task-checkbox {
  display: block;
  flex-shrink: 0;

  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 1px solid var(--stroke-secondary);
  cursor: pointer;

  @include hover {
    border-color: var(--bg-accent);
  }

  &--medium {
    background: rgba(255, 212, 171, 0.3);
    border-color: #FFE15D;
  }

  &--high {
    background: rgba(255, 171, 173, 0.3);
    border-color: #FF5457;
  }

  &--critical {
    background: rgba(255, 171, 230, 0.3);
    border-color: #FF4EC7
  }

  &:has(:checked) {
    border: 0;
    background: transparent;

    color: var(--icon-disabled);

    @include hover {
      color: var(--bg-accent);
    }

    & svg {
      display: block;
      width: 100%;
      height: 100%;
    }
  }

  & svg {
    display: none;
  }
}
</style>
