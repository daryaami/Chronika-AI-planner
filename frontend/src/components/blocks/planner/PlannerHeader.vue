<script setup lang="ts">
import RoundTextBtn from "@/components/ui-kit/btns/RoundTextBtn.vue";
import {computed} from "vue";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import ProfileDropdown from "@/components/blocks/ProfileDropdown.vue";


const emit = defineEmits(['nextWeek', 'prevWeek', 'today'])
const props = defineProps(['currentDate'])

const currentMonth = computed(() => {
  if (props.currentDate) {
    const now = props.currentDate;
    return `${now.toLocaleString('EN-US', { month: 'long' })} ${now.getFullYear()}`;
  } else {
    return ''
  }
})
</script>


<template>
  <div class="planner-header">
    <div class="planner-header__left-col">
      <RoundTextBtn text="Today"
                    @click="emit('today')"
      />
      <div class="planner-header__chevrons">
        <IconBtn
          icon="chevron-left"
          size="s"
          @click="emit('prevWeek')"
        />
        <IconBtn
          icon="chevron-right"
          size="s"
          @click="emit('nextWeek')"
        />
      </div>
      <span class="planner-header__date">{{ currentMonth }}</span>
    </div>

    <div class="planner-header__right-col">
      <RoundTextBtn
        text="Week"
        icon="chevron-down"
      />

      <ProfileDropdown />
    </div>


  </div>
</template>


<style lang="scss">

.planner-header {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 15px 35px;

  position: relative;
  z-index: 10;

  &__left-col {
    display: flex;
    align-items: center;
    gap: 18px;
  }

  &__date {
    font: var(--bold-24);
  }

  &__chevrons {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__right-col {
    display: flex;
    align-items: center;
    margin-left: auto;

    gap: 32px;
  }
}
</style>
