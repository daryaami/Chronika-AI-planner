<script setup lang="ts">
import {ref} from "vue";
import {useDropdown} from "@/components/composables/useDropdown";

interface Props {
  icon: string,
  iconColor?: string,
  primaryValue?: string,
  subtext?: string
}

withDefaults(defineProps<Props>(), {
  iconColor: '#232634'
})
</script>

<template>
  <button class="event-select-display" type="button">
    <svg xmlns="http://www.w3.org/2000/svg" :style="`color: ${iconColor}`" class="event-select-display__icon" width="18" height="18">
      <use :href="`#${icon}`"></use>
    </svg>

    <span class="event-select-display__text">
      <span class="event-select-display__values">
        <span v-if="primaryValue" class="event-select-display__primary-value">{{ primaryValue }}</span>
      </span>

      <span v-if="subtext" class="event-select-display__subtext">{{ subtext }}</span>
    </span>
  </button>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins' as *;

.event-select-display {
  background-color: transparent;
  border: none;
  outline: none;
  box-shadow: none;

  display: flex;
  gap: 8px;

  width: fit-content;
  cursor: pointer;
  padding: 8px 4px;
  border-radius: 4px;

  @include hover {
    background-color: var(--bg-primary-hover);
  }

  &__icon {
    display: block;
  }

  &__values {
    display: flex;
    margin-bottom: 6px;
  }

  &__primary-value {
    display: block;
    font: var(--bold-14);
  }

  &__subtext {
    font: var(--light-11);
    color: var(--text-primary-disabled);

    display: block;
    text-align: left;
  }
}
</style>
