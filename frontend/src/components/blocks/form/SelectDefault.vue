<script setup lang="ts">
import Dropdown from "@/components/ui-kit/Dropdown.vue";
import {computed, ref} from "vue";
import {useDropdown} from "@/components/composables/useDropdown";
import NavLink from "@/components/ui-kit/links/NavLink.vue";

interface SelectDefaultOption {
  value: string | null,
  icon?: string,
  color?: string,
  label: string
}

interface Props {
  icon?: string,
  options: SelectDefaultOption[]
}

const props = defineProps<Props>()

const modelValue = defineModel<string | null>({ default: null })

const rootEl = ref<HTMLElement | null>(null);
const { isOpen, toggle, close } = useDropdown(rootEl);


const activeOption = computed(() => {
  return props.options.find(o => o.value === modelValue.value) || null
});

const toggleActiveOption = (option: SelectDefaultOption) => {
  modelValue.value = modelValue.value === option.value ? null : option.value;
  close();
}

const computedIconColor = computed(() => {
  if (!activeOption.value?.color) return null
  return { color: activeOption.value.color }
})
</script>

<template>
  <div class="select-default" ref="rootEl">
    <button type="button" class="select-default__button"
            @click.prevent="toggle"
    >
      <svg v-if="icon" width="18" height="18"
           :style="computedIconColor"
      >
        <use :href="`#${icon}`"></use>
      </svg>
      <span v-if="activeOption">{{ activeOption.label }}</span>
      <svg width="12" height="12"
           :class="`select-default__chevron ${isOpen? 'rotated': ''}`"

      >
        <use :href="`#chevron-down`"></use>
      </svg>
    </button>

    <Dropdown class="select-default__dropdown" v-if="isOpen">
      <NavLink v-for="(o, i) in options" type="button"
               :key="i"
               :text="o.label"
               :leftIcon="o.icon || undefined"
               :rightIcon="o.value === activeOption?.value ? 'check-active' : undefined"
               :color="o.color || undefined"
               @click.stop="toggleActiveOption(o)"
      />
    </Dropdown>
  </div>
</template>

<style scoped lang="scss">
@use "@/assets/scss/mixins/mixins" as *;

.select-default {
  width: fit-content;
  position: relative;

  &__button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    background: transparent;
    border: none;
    outline: none;
    border-radius: 4px;
    color: var(--text-primary);
    cursor: pointer;
    padding: 6px 4px;

    @include hover {
      background: var(--bg-primary-hover);
    }

    span {
      font: var(--bold-14);
    }
  }

  &__chevron {
    transition: .15s;

    &.rotated {
      transform: rotate(180deg) ;
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
