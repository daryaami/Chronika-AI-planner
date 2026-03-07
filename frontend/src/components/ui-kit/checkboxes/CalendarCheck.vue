<script setup lang="ts">
import {Calendar} from "@/types/calendar";

interface Props {
  calendar: Calendar
}

defineProps<Props>()
</script>

<template>
  <label class="calendar-check">
    <span class="calendar-check__color" :style="`background-color: ${calendar.background_color}`"></span>
    <input type="checkbox" class="calendar-check__input" v-model="calendar.selected">
    <span class="calendar-check__title">{{ calendar.summary }}</span>
    <svg class="calendar-check__icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
      <use data-checked href="#checkbox-check"></use>
      <use data-unchecked href="#checkbox-unchecked"></use>
    </svg>
  </label>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins' as *;

.calendar-check {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px 5px 10px;
  border-radius: 4px;
  cursor: pointer;

  @include hover {
    background-color: var(--bg-secondary);
  }

  & [data-checked] {
    display: none;
  }

  & [data-unchecked] {
    display: block;
  }

  &:has(:checked) {
    & [data-checked] {
      display: block;
    }

    & [data-unchecked] {
      display: none;
    }
  }

  &__color {
    display: block;
    width: 10px;
    height: 10px;
    border-radius: 4px;

    flex-shrink: 0;
  }

  &__input {
    display: none;
  }

  &__title {
    flex-shrink: 1;
    overflow: hidden;
    text-overflow: ellipsis;

    font: var(--light-14);
  }

  &__icon {
    display: block;
    width: 16px;
    height: 16px;
    flex-shrink: 0;

    margin-left: auto;
    color: var(--icon-inactive);
  }
}
</style>
