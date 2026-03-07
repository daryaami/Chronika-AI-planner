<script setup lang="ts">
import RoundIconButton from "@/components/ui-kit/btns/RoundIconButton.vue";
import Dropdown from "@/components/ui-kit/Dropdown.vue";
import {ref} from "vue";
import {useDropdown} from "@/components/composables/useDropdown";
import ToggleButtons from "@/components/ui-kit/btns/ToggleButtons.vue";

const rootEl = ref<HTMLElement | null>(null);
const { isOpen, toggle } = useDropdown(rootEl);
</script>

<template>
  <div class="view-popup" ref="rootEl">
    <RoundIconButton icon="dots"
                     @click.prevent="toggle"
    />

    <Dropdown class="view-popup__dropdown"
              v-if="isOpen">
      <ToggleButtons label="View"
                     name="view"
                     :buttons="[
                       {
                         label: 'List',
                         icon: 'list-view'
                       },
                       {
                         label: 'Column',
                         icon: 'column-view'
                       }
                     ]"
      />

    </Dropdown>
  </div>
</template>

<style scoped lang="scss">
.view-popup {
  position: relative;

  &__dropdown {
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
  }
}
</style>
