<script setup lang="ts">
import SimpleInputIcon from '@/components/ui-kit/inputs/text/SimpleInputIcon.vue'

const props = defineProps<{
  modelValue: string
  icon?: string
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const formatTime = (value: string): string => {
  const digits = value.replace(/\D/g, '').slice(0, 4)
  if (!digits) return ''

  let hours = digits.slice(0, 2)
  let minutes = digits.slice(2)

  if (hours.length === 2) {
    const h = parseInt(hours, 10)
    if (h > 23) hours = '23'
  }

  if (minutes.length > 0) {
    if (minutes.length === 2) {
      const m = parseInt(minutes, 10)
      if (m > 59) minutes = '59'
    }
    return `${hours.padStart(2, '0')}:${minutes}`
  }

  return hours
}

const onInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  const formatted = formatTime(target.value)
  target.value = formatted
  emit('update:modelValue', formatted)
}
</script>

<template>
  <SimpleInputIcon class="simple-input-icon-time"
    :modelValue="modelValue"
    :icon="icon"
    :placeholder="placeholder || '00:00'"
    @input="onInput"
  />
</template>

<style scoped lang="scss">
.simple-input-icon-time {
  width: 68px;
}
</style>
