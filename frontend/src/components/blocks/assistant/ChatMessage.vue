<script setup lang="ts">
import {ChatMessageType} from "@/types/chat";
import {formatDueDate} from "@/components/js/time-utils";
import ActionBtn from "@/components/ui-kit/btns/ActionBtn.vue";
import {useChatStore} from "@/store/chat";
import {computed, ref} from "vue";
import SimpleInputIcon from "@/components/ui-kit/inputs/text/SimpleInputIcon.vue";
import SimpleInputIconDate from "@/components/ui-kit/inputs/date/SimpleInputIconDate.vue";
import SimpleInputIconTime from "@/components/ui-kit/inputs/time/SimpleInputIconTime.vue";
import SimpleInputIconSelect from "@/components/ui-kit/selects/SimpleInputIconSelect.vue";
import {useCalendarsStore} from "@/store/calendars";
import {Calendar} from "@/types/calendar";

const props = defineProps<{
  message: ChatMessageType
}>()

const chatStore = useChatStore()

const getTextForEvent = (fields: any) => {
  return `<b>${fields.summary}</b><br>${formatDueDate(new Date(fields.start))} — ${new Date(fields.end).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;
}

const confirmMessage = () => {
  chatStore.confirmMessage(props.message.message_id)
}

// Edit mode
const calendarStore = useCalendarsStore()

const editMode = ref<'event' | false>(false)
const editingContextId = ref<string | null>(null)

const eventName = ref('')
const date = ref<Date | null>(null)
const startTime = ref('')
const endTime = ref('')
const calendars = ref<Calendar[]>([])
const selectedCalendarId = ref<string | null>(null)


const enterEditMode = (block: any) => {
  if (block.entity_type === 'event') {
    editingContextId.value = block.context_id ?? null
    eventName.value = block.fields.summary ?? ''
    date.value = block.fields.start ? new Date(block.fields.start) : null

    const startDateTime = new Date(block.fields.start)
    const endDateTime = new Date(block.fields.end)

    startTime.value = `${startDateTime.getHours().toString().padStart(2, '0')}:${startDateTime.getMinutes().toString().padStart(2, '0')}`
    endTime.value = `${endDateTime.getHours().toString().padStart(2, '0')}:${endDateTime.getMinutes().toString().padStart(2, '0')}`

    selectedCalendarId.value = block.fields.calendar_id?.toString() || null

    calendarStore.getOwnedCalendars().then((data) => {
      calendars.value = data

      if (!selectedCalendarId.value) {
        const primary = data.find((c) => c.primary)
        selectedCalendarId.value = primary?.id.toString() ?? data[0]?.id.toString() ?? null
      }
    })

    editMode.value = 'event'
  }
}

const exitEditMode = () => {
  editMode.value = false
  editingContextId.value = null
  eventName.value = ''
  date.value = null
  startTime.value = ''
  endTime.value = ''
  selectedCalendarId.value = null
}

const saveEditMode = () => {
  if (!editingContextId.value || !date.value || !startTime.value || !endTime.value) return

  const [startHours, startMinutes] = startTime.value.split(':').map(Number)
  const [endHours, endMinutes] = endTime.value.split(':').map(Number)

  const start = new Date(date.value)
  start.setHours(startHours, startMinutes, 0, 0)

  const end = new Date(date.value)
  end.setHours(endHours, endMinutes, 0, 0)

  const fields: Record<string, any> = {
    summary: eventName.value,
    start: start.toISOString(),
    end: end.toISOString(),
  }

  if (selectedCalendarId.value) {
    fields.calendar_id = selectedCalendarId.value
  }

  chatStore.updateEntity(props.message.message_id, editingContextId.value, fields)
  exitEditMode()
}

const calendarOptions = computed(() => {
  return calendars.value.map((calendar) => ({
    value: calendar.id.toString(),
    label: calendar.summary,
    icon: 'calendar-color',
    color: calendar.background_color
  }))
})
</script>

<template>
  <div class="chat-message"
       :class="`chat-message--${message.role}`"
  >
    <div
         v-if="message.blocks?.length && !editMode"
         v-for="(b, i) in message.blocks"
         :key="i">
      <span class="chat-message__block"
            v-if="b.type === 'text'">{{ b.text }}</span>

      <div class="chat-message__block"
           v-if="b.type === 'entity' && b.entity_type === 'event'"
      >
        <span v-html="getTextForEvent(b.fields)"></span>

        <div class="chat-message__buttons"
             v-if="b.mode === 'editable'">
          <ActionBtn text="Да"
                     variant="secondary"
                     type="button"
                     @click="confirmMessage"
          />

          <ActionBtn text="Изменить"
                     variant="secondary"
                     type="button"
                     @click="enterEditMode(b)"
          />
        </div>
      </div>

    </div>

    <div v-if="!message.blocks?.length && !editMode">
      <span>{{ message.content }}</span>
    </div>

    <template v-if="editMode === 'event'">
      <div>Что нужно изменить?</div>

      <div class="chat-message__inputs-block">
        <SimpleInputIcon v-model="eventName" />

        <div class="chat-message__inputs">
          <SimpleInputIconDate v-model="date" />
          <SimpleInputIconTime v-model="startTime" />
          <span>-</span>
          <SimpleInputIconTime v-model="endTime" />
        </div>
        <SimpleInputIconSelect v-model="selectedCalendarId" :options="calendarOptions" />
      </div>


      <div class="chat-message__buttons">
        <ActionBtn text="Сохранить"
                   variant="primary"
                   type="button"
                   @click="saveEditMode"
        />

        <ActionBtn text="Отмена"
                   variant="secondary"
                   type="button"
                   @click="exitEditMode"
        />
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.chat-message {
  border-radius: 20px;
  padding: 6px 12px;
  max-width: 274px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 24px;

  &:not(:last-child) {
    & .chat-message__buttons {
      display: none;
    }
  }

  &__buttons {
    display: flex;
    gap: 10px;

    margin-top: 24px;
  }

  &__inputs-block {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  &__inputs {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__input {
    width: 60px
  }

  &--user {
    margin-left: auto;
    background: var(--robot-gray);
  }
}
</style>
