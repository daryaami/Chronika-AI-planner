<script setup lang="ts">
import { ref, computed } from "vue";
import Dropdown from "@/components/ui-kit/Dropdown.vue";
import NavLink from "@/components/ui-kit/links/NavLink.vue";
import { SelectSmallOption } from "@/types/selectSmallOption";
import { useDropdown } from "@/components/composables/useDropdown";

const modelValue = defineModel<string | null>({
  default: null
});

interface Props {
  icon: string,
  options: SelectSmallOption[],
  withLabel?: boolean,
}

const props = withDefaults(defineProps<Props>(), {
  withLabel: false,
})

const activeOption = computed(() =>
  props.options.find(o => o.value === modelValue.value) || null
);

const buttonColor = computed(() => {
  if (!activeOption.value) return "inactive";
  return activeOption.value.color ?? "active";
});

const rootEl = ref<HTMLElement | null>(null);
const { isOpen, toggle, close } = useDropdown(rootEl);

const toggleActiveOption = (option: SelectSmallOption) => {
  modelValue.value = modelValue.value === option.value ? null : option.value;
  close();
};
</script>


<template>
  <div class="select-small" ref="rootEl">
    <button type="button"
      class="select-small__button"
      :class="buttonColor"
      @click.prevent="toggle"
    >
      <svg class="select-small__icon" width="16" height="16">
        <use :href="`#${icon}`"></use>
      </svg>
      <span class="select-small__label" v-if="withLabel && activeOption">{{ activeOption.label }}</span>
    </button>

    <Dropdown class="select-small__dropdown" v-if="isOpen">
      <NavLink
        v-for="(option, i) in options"
        :key="i"
        :text="option.label"
        :leftIcon="option.icon || undefined"
        :rightIcon="option.value === activeOption?.value ? 'check-active' : undefined"
        :class="{ [option.color || '']: !!option.color }"
        @click="toggleActiveOption(option)"
      />
    </Dropdown>
  </div>
</template>

<style lang="scss">
@use "@/assets/scss/mixins/mixins" as *;

.select-small {
  position: relative;

  &__button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    background: transparent;
    border: none;
    outline: none;
    padding: 2px;
    border-radius: 4px;
    color: var(--icon-inactive);
    cursor: pointer;

    @include hover {
      background: var(--bg-primary-hover);
    }

    &.active svg,
    &.active span {
      color: var(--text-accent);
    }

    span {
      font: var(--light-14);
    }
  }

  &__dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    z-index: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .inactive svg,
  .inactive .select-small__label {
    color: var(--icon-inactive);
  }

  .medium svg,
  .medium .select-small__label {
    color: var(--medium);
  }

  .high svg,
  .high .select-small__label {
    color: var(--text-error);
  }
}
</style>
