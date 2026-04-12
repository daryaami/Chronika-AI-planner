<script setup lang="ts">
import { ref, nextTick } from 'vue';
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import TextTitleInput from "@/components/ui-kit/inputs/TextTitleInput.vue";
import EventCalendarSelect from "@/components/blocks/planner/event/EventCalendarSelect.vue";
import EventTimeSelect from "@/components/blocks/planner/event/EventTimeSelect.vue";
import TextField from "@/components/ui-kit/inputs/TextField.vue";
import ActionBtn from "@/components/ui-kit/btns/ActionBtn.vue";

const dialog = ref<HTMLDialogElement | null>(null);

const startDate = ref<Date | null>(null);
const endDate = ref<Date | null>(null);
const userCalendarId = ref<number>();

const open = async (date: Date) => {
  dialog.value?.showModal();

  startDate.value = date;
  endDate.value = new Date(date.getTime() + 3600000);

  // 🔥 ключевой фикс: дождаться рендера dialog + children
  await nextTick();
};

const close = () => {
  dialog.value?.close();
};

defineExpose({ open, close });
</script>

<template>
  <dialog class="event-create-popup" ref="dialog">
    <div class="event-create-popup__header">
      <IconBtn icon="delete" size="s" variant="secondary" />
      <IconBtn icon="cross" size="s" @click="close" />
    </div>

    <TextTitleInput class="event-create-popup__title" />

    <div class="event-create-popup__fields">
      <EventTimeSelect
        v-model:start-date="startDate"
        v-model:end-date="endDate"
        class="event-create-popup__date"
      />

      <EventCalendarSelect v-model="userCalendarId" />

      <TextField />
    </div>

    <div class="event-create-popup__footer">
      <ActionBtn text="Отменить" type="secondary" @click.native="close" />
      <ActionBtn text="Создать" type="primary" @click.native="close" />
    </div>
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
