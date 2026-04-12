<script setup lang="ts">
interface Props {
  placeholder?: string
}

withDefaults(defineProps<Props>(), {
  placeholder: 'Название'
})
</script>

<template>
  <input class="text-title-input" :placeholder="placeholder" type="text">
</template>

<style scoped lang="scss">
.text-title-input {
  font: var(--bold-20);

  border: 0;
  outline: none;

  display: block;

  &::placeholder {
    color: var(--text-tertiary);
  }
}
</style>
