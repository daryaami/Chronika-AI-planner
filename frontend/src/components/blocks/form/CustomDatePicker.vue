<script setup lang="ts">
import VueDatePicker from "@vuepic/vue-datepicker";
import { computed } from "vue";
import {toWeekDayAndDate} from "@/components/js/time-utils";

const props = withDefaults(defineProps<{
  modelValue: Date | string | null;
  enableTimePicker?: boolean;
  /** Выравнивание меню относительно триггера: left — смещает меню правее относительно center */
  position?: "left" | "center" | "right";
  /** true — телепорт в body (удобно при overflow у предков) */
  teleport?: boolean | string;
}>(), {
  enableTimePicker: true,
});

const emit = defineEmits<{
  (e: "update:modelValue", value: Date | null): void;
}>();

// безопасная синхронизация локального значения
const value = computed({
  get: () => {
    if (typeof props.modelValue === "string") {
      const d = new Date(props.modelValue);
      return isNaN(d.getTime()) ? null : d;
    }
    return props.modelValue;
  },
  set: (val) => emit("update:modelValue", val),
});

const displayValue = computed(() => {
  if (!value.value) return "Due";
  return toWeekDayAndDate(value.value);
});
</script>

<template>
  <VueDatePicker
      v-model="value"
      :enable-time-picker="props.enableTimePicker"
      :position="props.position"
      :teleport="props.teleport"
  >
    <template #trigger>
      <button
        type="button"
        class="select-button-small"
        :class="{ 'select-button-small--active': value }"
      >
        <svg class="select-button-small__icon" width="16" height="16">
          <use href="#date-range"></use>
        </svg>
        <span>{{ displayValue }}</span>
      </button>
    </template>
  </VueDatePicker>
</template>

<style scoped lang="scss">
@use "@/assets/scss/mixins/mixins" as *;

.select-button-small {
  position: relative;

  font: var(--light-14);
  color: var(--text-primary-disabled);

  padding: 4px 4px 4px 20px;
  border-radius: 4px;

  border: none;
  outline: none;
  background: transparent;

  cursor: pointer;

  @include hover {
    background-color: var(--bg-primary-hover);
  }

  &--active {
    color: var(--text-primary-hover);
  }

  &__icon {
    position: absolute;
    top: 50%;
    left: 2px;
    transform: translateY(-50%);
    pointer-events: none;
  }
}

.dp__main {
  width: fit-content !important;
}
</style>
