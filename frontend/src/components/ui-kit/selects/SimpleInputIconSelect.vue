<script setup lang="ts">
import Dropdown from "@/components/ui-kit/Dropdown.vue";
import { computed, ref } from "vue";
import { useDropdown } from "@/components/composables/useDropdown";
import NavLink from "@/components/ui-kit/links/NavLink.vue";
import SimpleInputIcon from "@/components/ui-kit/inputs/text/SimpleInputIcon.vue";

interface SimpleInputIconOption {
  value: string | null,
  icon?: string,
  color?: string,
  label: string
}

interface Props {
  options: SimpleInputIconOption[],
  placeholder?: string
}

const props = defineProps<Props>()

const modelValue = defineModel<string | null>({ default: null })

const rootEl = ref<HTMLElement | null>(null);
const { isOpen, toggle, close } = useDropdown(rootEl);

const activeOption = computed(() => {
  return props.options.find(o => o.value === modelValue.value) || null
});

const displayValue = computed(() => {
  return activeOption.value?.label ?? ''
})

const selectOption = (option: SimpleInputIconOption) => {
  modelValue.value = option.value;
  close();
}
</script>

<template>
  <div class="simple-input-icon-select" ref="rootEl">
    <div class="simple-input-icon-select__input-wrapper" @click="toggle">
      <SimpleInputIcon
        :modelValue="displayValue"
        :placeholder="placeholder"
        readonly
      />
    </div>

    <Dropdown class="simple-input-icon-select__dropdown" v-if="isOpen">
      <NavLink v-for="(o, i) in options" type="button"
               :key="i"
               :text="o.label"
               :leftIcon="o.icon || undefined"
               :rightIcon="o.value === activeOption?.value ? 'check-active' : undefined"
               :color="o.color || undefined"
               @click.stop="selectOption(o)"
      />
    </Dropdown>
  </div>
</template>

<style scoped lang="scss">
@use "@/assets/scss/mixins/mixins" as *;

.simple-input-icon-select {
  width: fit-content;
  position: relative;

  &__input-wrapper {
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;

    > * {
      pointer-events: none;
    }
  }

  &__dropdown {
    position: absolute;
    left: 0;
    top: calc(100% + 4px);
    z-index: 10;
  }
}
</style>
