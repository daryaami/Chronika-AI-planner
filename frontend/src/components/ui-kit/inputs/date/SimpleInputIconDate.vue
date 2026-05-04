<script setup lang="ts">
import VueDatePicker from "@vuepic/vue-datepicker";
import SimpleInputIcon from "@/components/ui-kit/inputs/text/SimpleInputIcon.vue";
import {ref, nextTick, onMounted, computed} from "vue";
import {toWeekDayAndDate} from "@/components/js/time-utils";

const props = defineProps<{
  modelValue: Date | string | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: Date | null): void;
}>();

const value = ref();

const onOpen = async () => {
  await nextTick();

  const menu = document.querySelector(".dp__menu");
  if (!menu) return;

  const rect = menu.getBoundingClientRect();

  menu.setAttribute("style", `
    position: fixed !important;
    top: auto !important;
    left: auto !important;
    right: ${window.innerWidth - rect.right}px;
    bottom: ${window.innerHeight - rect.bottom}px;
    z-index: 10000;
  `);
};


const displayedValue = computed(() => {
  return toWeekDayAndDate(value.value);
})
</script>

<template>
  <div class="simple-input-icon-date">
    <VueDatePicker
      :enable-time-picker="false"
      v-model="value"
      teleport
      @open="onOpen"
    >
      <template #trigger>
        <SimpleInputIcon v-model="displayedValue" />
      </template>
    </VueDatePicker>
  </div>
</template>

<style lang="scss">
.simple-input-icon-date {
  flex-shrink: 1;
  width: 100px;
}

.dp__arrow_bottom {
  display: none !important;
}
</style>
