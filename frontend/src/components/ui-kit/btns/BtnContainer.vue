<script setup lang="ts">
import IconText from "@/components/ui-kit/links/IconText.vue";
import {UISize} from "@/types/UISize";
import {Button} from "@/types/button";
import {computed} from "vue";

const props = defineProps<{
  buttons: Button[]
  size?: UISize
}>()

const btnSize = computed(() => {
  switch (props.size) {
    case 'l':
      return 'm' as UISize
    default:
      return 'm' as UISize
  }
})

const btnWeight = computed(() => {
  switch (props.size) {
    case 'l':
      return 'bold'
    default:
      return 'reg'
  }
})
</script>

<template>
  <div class="btn-container" :class="`btn-container--${size}`">
  <IconText v-for="button in buttons"
            :key="button.icon"
            :left-icon="button.icon"
            :text="button.text"
            :size="btnSize"
            :weight="btnWeight"
  >

  </IconText>
  </div>
</template>

<style scoped lang="scss">
.btn-container {
  display: flex;
  align-items: center;

  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.07);
  background: var(--bg-highlight);

  &--l {
    gap: 24px;
    border-radius: 20px;
    padding: 11px 15px;
  }
}
</style>
