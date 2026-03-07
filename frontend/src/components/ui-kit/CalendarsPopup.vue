<script setup lang="ts">
import {Calendar} from "@/types/calendar";
import CalendarCheck from "@/components/ui-kit/checkboxes/CalendarCheck.vue";

defineProps<{
  calendars: Calendar[]
}>()
</script>

<template>
  <div class="calendars-popup">
    <CalendarCheck v-for="calendar in calendars"
                   :key="calendar.id"
                   :calendar="calendar"
    />
  </div>
</template>

<style scoped lang="scss">
.calendars-popup {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
