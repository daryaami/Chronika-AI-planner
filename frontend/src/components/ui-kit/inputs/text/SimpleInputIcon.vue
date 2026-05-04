<script setup lang="ts">
const props = defineProps<{
  modelValue: string
  icon?: string
  placeholder?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const onInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
  emit('input', event)
}
</script>

<template>
  <label class="simple-input-icon">
    <input class="simple-input-icon__input"
      type="text"
      :value="modelValue"
      @input="onInput"
      :placeholder="placeholder"
      :readonly="readonly"
    >
    <span v-if="icon" class="icon">{{ icon }}</span>
  </label>
</template>

<style lang="scss" scoped>
.simple-input-icon {
  width: fit-content;
  overflow: hidden;

  &__input {
    border: none;
    outline: none;
    padding: 4px 12px;
    background-color: var(--bg-secondary);
    border-radius: 4px;
    width: auto;
    field-sizing: content;
    min-width: min-content;

    font: var(--light-14);
    max-width: 100%;
  }
}
</style>
