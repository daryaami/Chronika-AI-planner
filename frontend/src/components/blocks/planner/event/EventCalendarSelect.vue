<script setup lang="ts">
import EventSelectDisplay from "@/components/ui-kit/selects/EventSelectDisplay.vue";
import {useCalendarsStore} from "@/store/calendars";
import {computed, onMounted, ref, watch} from "vue";
import {Calendar} from "@/types/calendar";
import {useDropdown} from "@/components/composables/useDropdown";
import NavLink from "@/components/ui-kit/links/NavLink.vue";
import Dropdown from "@/components/ui-kit/Dropdown.vue";

// Props & Emits
const props = defineProps<{
  modelValue?: number;
}>();

const emit = defineEmits<{
  'update:modelValue': [calendarId: number];
}>();

// Calendars
const calendarsStore = useCalendarsStore()

const calendars = ref<Calendar[]>()
const selectedCalendar = ref<Calendar>()

onMounted(async () => {
  const fetchedCalendars = await calendarsStore.getCalendars();
  calendars.value = fetchedCalendars.filter(c => c.owner)
  console.log(calendars)
  selectedCalendar.value = calendars.value.filter(calendar => calendar.primary)[0]

  // Если передан calendarId через v-model, выбираем соответствующий календарь
  if (props.modelValue) {
    const calendar = calendars.value.find(c => c.id === props.modelValue)
    if (calendar) {
      selectedCalendar.value = calendar
    }
  } else if (selectedCalendar.value) {
    // Если не передан calendarId, эмитим primary календарь
    emit('update:modelValue', selectedCalendar.value.id)
  }
})

// Следим за изменением calendarId извне
watch(() => props.modelValue, (newCalendarId) => {
  if (newCalendarId && calendars.value) {
    const calendar = calendars.value.find(c => c.id === newCalendarId)
    if (calendar) {
      selectedCalendar.value = calendar
    }
  }
})

// Dropdown
const rootEl = ref<HTMLElement | null>(null);
const { isOpen, toggle, close } = useDropdown(rootEl);

const optionClickHandler = (calendar: Calendar) => {
  selectedCalendar.value = calendar
  emit('update:modelValue', calendar.id)
  close()
}
</script>

<template>
  <div v-if="selectedCalendar" class="event-calendar-select" ref="rootEl">
    <EventSelectDisplay
      icon="color"
      :icon-color="selectedCalendar.background_color"
      :primary-value="selectedCalendar.summary"
      subtext="Выберите календарь"
      @click="toggle"
    />

    <Dropdown class="event-calendar-select__dropdown" v-if="isOpen">
      <NavLink v-for="(c, i) in calendars" tag="button"
               :key="i"
               :text="c.summary"
               leftIcon="color"
               :rightIcon="c.id === selectedCalendar.id ? 'check-active' : undefined"
               :color="c.background_color || undefined"
               @click.stop="optionClickHandler(c)"
      />
    </Dropdown>
  </div>
</template>

<style scoped lang="scss">
.event-calendar-select {
  position: relative;
  width: fit-content;

  &__dropdown {
    position: absolute;
    left: 0;
    top: calc(100% + 4px);
  }
}
</style>
