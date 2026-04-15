<script setup lang="ts">
interface Props {
  placeholder?: string
  modelValue?: string
}

withDefaults(defineProps<Props>(), {
  placeholder: 'Название'
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <input
    class="text-title-input"
    :placeholder="placeholder"
    type="text"
    :value="modelValue"
    @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
  >
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
