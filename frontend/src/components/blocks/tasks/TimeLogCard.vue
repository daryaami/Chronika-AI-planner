<script setup lang="ts">
import {TaskEvent} from "@/types/task";
import {computed} from "vue";
import {toWeekDayAndDate} from "@/components/js/time-utils";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";

const props = defineProps<{
  timeLog: TaskEvent
}>()

const date = computed(() => {
  return toWeekDayAndDate(new Date(props.timeLog.start_time))
})

const time = computed(() => {
  const startTime = new Date(props.timeLog.start_time)
  const endTime = new Date(props.timeLog.end_time)

  const format = (date: Date) =>
    date.toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    })

  return `${format(startTime)}-${format(endTime)}`
})

</script>

<template>
  <div class="time-log-card">
    <span class="time-log-card__date">{{ date }}</span>
    <span class="time-log-card__time">{{ time }}</span>
    <IconBtn icon="dots"
             size="xxs"
             type="button"
    />
  </div>
</template>

<style scoped lang="scss">
.time-log-card {
  display: grid;
  grid-template-columns: subgrid;
  grid-column: 1 / -1;

  align-items: center;
  gap: 16px;

  font: var(--light-12);

  padding: 10px;
  background: var(--bg-secondary);

  &__date {
    color: var(--text-primary-muted);
    white-space: nowrap;
  }

  &__time {
    color: var(--text-primary-disabled);
  }
}
</style>
