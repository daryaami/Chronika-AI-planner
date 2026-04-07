<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import VueSelect from 'vue-select'
import 'vue-select/dist/vue-select.css'
import IconBtn from '@/components/ui-kit/btns/IconBtn.vue'

interface TimezoneOption {
  value: string
  label: string
}

interface Props {
  modelValue: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | null): void
}>()

const options = ref<TimezoneOption[]>([])
const selected = ref<TimezoneOption | null>(null)

/**
 * Получить offset вида GMT+3
 */
function getOffset(tz: string): string {
  const date = new Date()

  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    timeZoneName: 'shortOffset'
  }).formatToParts(date)

  const offset = parts.find(p => p.type === 'timeZoneName')?.value || ''

  return offset.replace('GMT', 'GMT')
}

/**
 * Получить текущую таймзону пользователя
 */
function getClientTz(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

onMounted(() => {
  const zones = Intl.supportedValuesOf('timeZone')

  options.value = zones.map((tz) => ({
    value: tz,
    label: `${getOffset(tz)} (${tz})`
  }))

  initializeValue()
})

const initializeValue = () => {
  if (props.modelValue) {
    selected.value =
      options.value.find(o => o.value === props.modelValue) ?? null
  } else {
    const userTz = getClientTz()
    const found = options.value.find(o => o.value === userTz)

    if (found) {
      selected.value = found
      emit('update:modelValue', found.value)
    }
  }
}

watch(
  () => props.modelValue,
  (val) => {
    if (!val) {
      selected.value = null
      return
    }

    selected.value =
      options.value.find(o => o.value === val) ?? null
  }
)

watch(selected, (val) => {
  emit('update:modelValue', val?.value ?? null)
})
</script>

<template>
  <VueSelect
    class="select"
    v-model="selected"
    :options="options"
    label="label"
    :clearable="false"
  >
    <template #open-indicator>
      <IconBtn icon="chevron-down" class="select__toggle" size="s" />
    </template>
  </VueSelect>
</template>

<style lang="scss">
.select {
  &.vs--open {
    & .select__toggle {
      transform: rotate(180deg);
    }
  }

  &__toggle {
    transition: transform 0.2s;
  }
}

.vs__selected {
  position: absolute;
  width: 100%;

  display: -webkit-box;
  -webkit-line-clamp: 1;
  line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
