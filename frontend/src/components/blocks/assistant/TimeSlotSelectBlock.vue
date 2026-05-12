<script setup lang="ts">
import {computed} from "vue";

interface SlotItem {
  start: string,
  end: string,
}

const props = defineProps<{
  slots?: SlotItem[]
}>()

const emit = defineEmits<{
  (e: 'select', slot: SlotItem): void
}>()

const toDayLabel = (iso: string) => {
  const date = new Date(iso)
  const weekDay = date.toLocaleDateString('ru-RU', { weekday: 'short' }).replace('.', '').toUpperCase()
  const day = date.getDate().toString().padStart(2, '0')
  const month = (date.getMonth() + 1).toString().padStart(2, '0')
  return `${weekDay}, ${day}.${month}`
}

const toTimeRange = (startIso: string, endIso: string) => {
  const start = new Date(startIso)
  const end = new Date(endIso)

  const from = start.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})
  const to = end.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})

  return `${from} — ${to}`
}

const slotsByDay = computed(() => {
  const groups: Record<string, SlotItem[]> = {}

  for (const slot of props.slots ?? []) {
    const key = toDayLabel(slot.start)
    if (!groups[key]) groups[key] = []
    groups[key].push(slot)
  }

  return Object.entries(groups).map(([day, slots]) => ({day, slots}))
})
</script>

<template>
  <div class="time-slot-select-block">
    <div class="time-slot-select-block__rows">
      <div
        v-for="(group, groupIndex) in slotsByDay"
        :key="group.day + groupIndex"
        class="time-slot-select-block__row"
      >
        <div class="time-slot-select-block__day">{{ group.day }}</div>
        <div class="time-slot-select-block__slots">
          <button
            v-for="(slot, slotIndex) in group.slots"
            :key="slot.start + slot.end + slotIndex"
            class="time-slot-select-block__slot-btn"
            type="button"
            @click="emit('select', slot)"
          >
            {{ toTimeRange(slot.start, slot.end) }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.time-slot-select-block {
  display: flex;
  flex-direction: column;
  gap: 12px;

  &__rows {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  &__row {
    display: flex;  
    align-items: flex-start;
    gap: 10px;
  }

  &__day {
    min-width: 84px;
    font: var(--light-14);
    padding-top: 8px;
  }

  &__slots {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  &__slot-btn {
    border: 1px solid var(--stroke-primary-invisible);
    background: var(--bg-primary);
    border-radius: 10px;
    padding: 8px 12px;
    font: var(--light-14);
    cursor: pointer;
    transition: border-color .15s ease, color .15s ease;

    &:hover {
      border-color: var(--text-accent);
      color: var(--text-accent);
    }
  }
}
</style>
