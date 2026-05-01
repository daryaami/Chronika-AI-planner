<script setup lang="ts">
import Dropdown from "@/components/ui-kit/Dropdown.vue";
import {EventInput} from "@fullcalendar/core";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import {computed, onBeforeUnmount, onMounted, useTemplateRef} from "vue";
import {useEventsStore} from "@/store/events";

interface Props {
  event: EventInput
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void,
  (e: 'delete'): void
}>()

const eventsStore = useEventsStore()

const time = computed(() => {
  const start = new Date(props.event?.start)
  const end = new Date(props.event?.end)

  if (!start || !end) return ''

  return `${String(start.getHours()).padStart(2, '0')}:${String(start.getMinutes()).padStart(2, '0')} - ${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`
})

const deleteEvent = async () => {
  const googleEvent = props.event?.extendedProps?.googleEvent;

  // Пробуем получить данные из googleEvent или из extendedProps
  const eventId = googleEvent?.id || props.event.id;
  const userCalendarId = googleEvent?.user_calendar_id || props.event.extendedProps?.user_calendar_id;

  if (!eventId || !userCalendarId) return;

  await eventsStore.deleteEvent(eventId, userCalendarId)

  emit('delete')
}

const rootEl = useTemplateRef('rootEl')

const onClick = (event: MouseEvent) => {
  const target = event.target as Node

  const el = rootEl.value?.$el as HTMLElement | undefined

  if (el && !el.contains(target)) {

    emit('close')
  }
}

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === "Escape") {
    emit('close')
  }
};

onMounted(async () => {
  setInterval(() => {
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeydown);
  }, 500)
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onClick);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <Dropdown class="event-popup" ref="rootEl">
    <div class="event-popup__header">
      <span class="event-popup__title">{{ event.title }}</span>

      <IconBtn class="event-popup__delete"
               icon="delete"
               @click="deleteEvent"
      />
      <IconBtn icon="cross"
               @click="emit('close')"
      />
    </div>

    <p class="event-popup__time">{{ time }}</p>
    <p class="event-popup__text" v-if="event.extendedProps?.googleEvent?.description" v-html="event.extendedProps.googleEvent.description"></p>
  </Dropdown>
</template>

<style scoped lang="scss">
.event-popup {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);

  max-width: 360px;

  z-index: 10;

  &__header {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__delete {
    margin-left: 40px;
  }

  &__title {
    margin-right: auto;
    white-space: nowrap;
  }

  &__time {
    font: var(--light-14);
  }

  &__text {
    font: var(--light-12);
  }
}
</style>
