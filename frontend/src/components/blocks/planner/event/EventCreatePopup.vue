<script setup lang="ts">
import { ref, nextTick, computed } from 'vue';
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import TextTitleInput from "@/components/ui-kit/inputs/text/TextTitleInput.vue";
import EventCalendarSelect from "@/components/blocks/planner/event/EventCalendarSelect.vue";
import EventTimeSelect from "@/components/blocks/planner/event/EventTimeSelect.vue";
import TextField from "@/components/ui-kit/inputs/text/TextField.vue";
import ActionBtn from "@/components/ui-kit/btns/ActionBtn.vue";
import { useEventsStore } from "@/store/events";
import type { EventInput } from "@fullcalendar/core";

const dialog = ref<HTMLDialogElement | null>(null);

const title = ref('');
const description = ref('');
const startDate = ref<Date | null>(null);
const endDate = ref<Date | null>(null);
const userCalendarId = ref<number>();
const editingEventId = ref<string | null>(null);

const eventsStore = useEventsStore();

const isEditMode = computed(() => Boolean(editingEventId.value));

const toDate = (value: Date | string | null | undefined): Date | null => {
  if (!value) return null;

  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const open = async (date: Date, event?: EventInput) => {
  dialog.value?.showModal();

  if (event?.id) {
    const googleEvent = event.extendedProps?.googleEvent;
    const eventStartDate = toDate(event.start as Date | string);
    const eventEndDate = toDate(event.end as Date | string);

    editingEventId.value = String(event.id);
    startDate.value = eventStartDate || date;
    endDate.value = eventEndDate || new Date((eventStartDate || date).getTime() + 3600000);
    title.value = event.title || '';
    description.value = googleEvent?.description || '';
    userCalendarId.value = googleEvent?.user_calendar_id || event.extendedProps?.user_calendar_id;
  } else {
    editingEventId.value = null;
    startDate.value = date;
    endDate.value = new Date(date.getTime() + 3600000);
    title.value = '';
    description.value = '';
  }

  await nextTick();
};

const close = () => {
  editingEventId.value = null;
  dialog.value?.close();
};

const onSubmit = async () => {
  if (!userCalendarId.value || !startDate.value || !endDate.value) {
    console.log('Validation failed');
    return;
  }

  const payload = {
    summary: title.value || 'Без названия',
    user_calendar_id: userCalendarId.value,
    description: description.value || undefined,
    start: {
      dateTime: startDate.value.toISOString()
    },
    end: {
      dateTime: endDate.value.toISOString()
    }
  };

  const eventId = editingEventId.value;

  close();

  if (eventId) {
    await eventsStore.updateEventFromForm({
      ...payload,
      id: Number(eventId)
    });
    return;
  }

  await eventsStore.createEventFromForm(payload);
};

const deleteCurrentEvent = async () => {
  if (!editingEventId.value || !userCalendarId.value) return;

  const eventId = editingEventId.value;
  const calendarId = userCalendarId.value;

  close();
  await eventsStore.deleteEvent(eventId, calendarId);
};

defineExpose({ open, close });
</script>

<template>
  <dialog class="event-create-popup" ref="dialog">
    <form @submit.prevent="onSubmit">

      <div class="event-create-popup__header">
        <IconBtn icon="delete"
                 size="s"
                 variant="secondary"
                 v-if="isEditMode"
                 @click="deleteCurrentEvent"
                 type="button"
        />
        <IconBtn icon="cross"
                 size="s"
                 @click="close"
                 type="button"
        />
      </div>

      <TextTitleInput
        class="event-create-popup__title"
        v-model="title"
        placeholder="Название события"
      />

      <div class="event-create-popup__fields">
        <EventTimeSelect
          v-model:start-date="startDate"
          v-model:end-date="endDate"
          class="event-create-popup__date"
        />

        <EventCalendarSelect v-model="userCalendarId" />

        <TextField v-model="description" />
      </div>

      <div class="event-create-popup__footer">
        <ActionBtn text="Отменить" variant="secondary" @click="close" />
        <ActionBtn :text="isEditMode ? 'Сохранить' : 'Создать'" variant="primary" type="submit" />
      </div>
    </form>
  </dialog>
</template>

<style scoped lang="scss">
.event-create-popup {
  border: none;
  outline: none;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  background: var(--bg-highlight);
  border-radius: 16px;
  padding: 24px;
  max-width: 516px;
  width: 100%;

  overflow: visible;

  &__header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 16px;
    gap: 12px;
  }

  &__title {
    margin-bottom: 22px;
  }

  &__fields {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  &__footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;

    margin-top: 32px;
  }
}
</style>
