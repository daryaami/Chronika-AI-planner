<script setup lang="ts">
interface Props {
  text: string
  modelValue?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const onChange = (event: Event) => {
  emit('update:modelValue', (event.target as HTMLInputElement).checked)
}
</script>

<template>
  <label class="checkbox-text">
   <input
      class="checkbox-text__input"
      type="checkbox"
      :checked="props.modelValue"
      @change="onChange"
    />
    <svg class="checkbox-text__icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24">
      <use data-checked href="#checkbox-check"></use>
      <use data-unchecked href="#checkbox-unchecked"></use>
    </svg>
    <span class="checkbox-text__text">{{ text }}</span>
  </label>
</template>

<style scoped lang="scss">
.checkbox-text {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;

  & [data-checked] {
    display: none;
  }

  & [data-unchecked] {
    display: block;
  }

  &:has(:checked) {
    & [data-checked] {
      display: block;
    }

    & [data-unchecked] {
      display: none;
    }
  }

  &__icon {
    display: block;
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  &__input {
    display: none;
  }

  &__text {
    font: var(--light-14);
  }
}
</style>
