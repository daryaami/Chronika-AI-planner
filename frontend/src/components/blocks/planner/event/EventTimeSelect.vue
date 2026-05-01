<script setup lang="ts">
import { computed } from 'vue'
import VueDatePicker from "@vuepic/vue-datepicker"

// 👉 тип для time-picker
interface TimeValue {
  hours: number
  minutes: number
}

// props
const props = defineProps<{
  startDate: Date | null
  endDate: Date | null
}>()

// emits
const emit = defineEmits<{
  (e: 'update:startDate', value: Date | null): void
  (e: 'update:endDate', value: Date | null): void
}>()

// 📅 ДАТА (берётся из startDate)
const dateModel = computed({
  get: () => props.startDate,
  set: (value: Date | null) => {
    if (!value || !props.startDate) return

    const newStart = new Date(value)

    // сохраняем время
    newStart.setHours(
      props.startDate.getHours(),
      props.startDate.getMinutes()
    )

    const duration = props.endDate
      ? props.endDate.getTime() - props.startDate.getTime()
      : 0

    emit('update:startDate', newStart)
    emit('update:endDate', new Date(newStart.getTime() + duration))
  }
})

// ⏰ START TIME
const startTimeModel = computed({
  get: (): TimeValue | null => {
    if (!props.startDate) return null
    return {
      hours: props.startDate.getHours(),
      minutes: props.startDate.getMinutes()
    }
  },
  set: (value: TimeValue | null) => {
    if (!value || !props.startDate) return

    const newStart = new Date(props.startDate)
    newStart.setHours(value.hours, value.minutes)

    const duration = props.endDate
      ? props.endDate.getTime() - props.startDate.getTime()
      : 0

    emit('update:startDate', newStart)
    emit('update:endDate', new Date(newStart.getTime() + duration))
  }
})

// ⏰ END TIME
const endTimeModel = computed({
  get: (): TimeValue | null => {
    if (!props.endDate) return null
    return {
      hours: props.endDate.getHours(),
      minutes: props.endDate.getMinutes()
    }
  },
  set: (value: TimeValue | null) => {
    if (!value || !props.endDate) return

    const newEnd = new Date(props.endDate)
    newEnd.setHours(value.hours, value.minutes)

    emit('update:endDate', newEnd)
  }
})
</script>

<template>
  <div class="event-time-select">
    <!-- 📅 дата -->
    <div class="event-time-select__date">
      <VueDatePicker
        v-model="dateModel"
        :enable-time-picker="false"
      />
    </div>

    <!-- ⏰ старт -->
    <VueDatePicker
      v-model="startTimeModel"
      time-picker
      text-input
    />

    <span>—</span>

    <!-- ⏰ конец -->
    <VueDatePicker
      v-model="endTimeModel"
      time-picker
      text-input
    />
  </div>
</template>

<style scoped lang="scss">
.event-time-select {
  display: flex;
  gap: 12px;
  align-items: center;

  &__date {
    flex-basis: 40%;
    flex-shrink: 0;
  }
}
</style>
