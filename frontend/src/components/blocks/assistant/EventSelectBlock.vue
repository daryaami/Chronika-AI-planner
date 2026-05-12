<script setup lang="ts">
import {computed} from "vue";
import {formatDueDate} from "@/components/js/time-utils";

const props = defineProps<{
  title?: string,
  start?: string,
  end?: string,
  number?: number,
}>()
const emit = defineEmits<{
  (e: 'select'): void
}>()

const formattedTimeRange = computed(() => {
  if (!props.start || !props.end) return ''

  const startDate = new Date(props.start)
  const endDate = new Date(props.end)

  return `${formatDueDate(startDate)} ${startDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })} — ${endDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`
})
</script>

<template>
  <div class="event-select-block">
    <div class="event-select-block__number">{{ number }}</div>

    <button class="event-select-block__card" type="button" @click="emit('select')">
      <div class="event-select-block__title-row">
        <span class="event-select-block__dot" />
        <span class="event-select-block__title">{{ title }}</span>
      </div>
      <div class="event-select-block__time">{{ formattedTimeRange }}</div>
    </button>
  </div>
</template>

<style scoped lang="scss">
.event-select-block {
  display: flex;
  align-items: center;
  gap: 10px;

  &__number {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid var(--text-accent);
    color: var(--text-accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font: var(--bold-12);
    flex-shrink: 0;
  }

  &__card {
    border: none;
    width: 100%;
    text-align: left;
    background: var(--bg-primary);
    border-radius: 14px;
    padding: 14px 18px;
    box-shadow: 0 6px 20px var(--stroke-primary-invisible);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  &__title-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  &__dot {
    width: 12px;
    height: 12px;
    border-radius: 4px;
    background: var(--bg-accent-secondary);
    flex-shrink: 0;
  }

  &__title {
    color: var(--text-primary-muted);
    font: var(--bold-14);
  }

  &__time {
    padding-left: 22px;
    color: var(--text-primary-disabled);
    font: var(--light-14);
  }
}
</style>
