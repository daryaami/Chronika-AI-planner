<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import vSelect from 'vue-select'
import 'vue-select/dist/vue-select.css'
import { listTz, clientTz } from 'timezone-select-js'
import IconBtn from "@/components/ui-kit/IconBtn.vue";


interface TimezoneRaw {
  value: string
  label: string
  offset: string
  included: string
}

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

onMounted(() => {
  const raw = listTz()

  options.value = raw.map((tz: TimezoneRaw) => ({
    value: tz.value,
    // Расширяем label — встроенный поиск будет искать по всей строке
    label: `${tz.label} (${tz.value}) ${tz.included ?? ''}`,
  }))

  initializeValue()
})

const initializeValue = () => {
  if (props.modelValue) {
    selected.value =
      options.value.find(o => o.value === props.modelValue) ?? null
  } else {
    const userTz = clientTz()
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
  <vSelect
    class="select"
    v-model="selected"
    :options="options"
    label="label"
    :clearable="false"
  >
    <template #open-indicator>
      <IconBtn icon="chevron-down" class="select__toggle" size="s" />
    </template>
  </vSelect>
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
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
