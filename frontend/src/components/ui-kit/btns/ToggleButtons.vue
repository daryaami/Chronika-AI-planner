<script setup lang="ts">
import { onMounted, ref, nextTick } from 'vue'

interface Button {
  label: string
  icon: string
}

interface Props {
  label?: string
  buttons: Button[]
  name?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: 'toggle-buttons'
})

const bgEl = ref<HTMLElement | null>(null)
const activeIndex = ref(0)
const buttonRefs = ref<HTMLElement[]>([])

const setBgPosition = async (index: number) => {
  activeIndex.value = index
  await nextTick()

  const btn = buttonRefs.value[index]
  const bg = bgEl.value

  if (!btn || !bg) return

  bg.style.width = `${btn.offsetWidth}px`
  bg.style.transform = `translateX(${btn.offsetLeft}px)`
}

onMounted(async () => {
  await setBgPosition(0)
  await nextTick()
  bgEl.value?.classList.add('init')
})
</script>


<template>
  <div class="toggle-buttons">
    <span
        v-if="label"
        class="toggle-buttons__label"
    >
      {{ label }}
    </span>

    <div class="toggle-buttons__buttons">
      <div class="toggle-buttons__bg" ref="bgEl"></div>

      <label
          v-for="(button, index) in buttons"
          :key="button.label"
          class="toggle-buttons__button"
          :ref="el => el && (buttonRefs[index] = el)"
          @click="setBgPosition(index)"
      >
        <input
            type="radio"
            :name="name"
            class="visually-hidden"
            :checked="index === activeIndex"
        />

        <svg width="16" height="16">
          <use :href="`#${button.icon}`" />
        </svg>

        <span>{{ button.label }}</span>
      </label>
    </div>
  </div>
</template>


<style scoped lang="scss">
.toggle-buttons {
  &__label {
    font: var(--light-14);
    color: var(--text-primary-disabled);

    display: block;

    margin-bottom: 10px;
  }

  &__buttons {
    display: flex;
    gap: 8px;
    align-items: center;

    padding: 2px;
    border-radius: 20px;

    box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.07);
    background: var(--bg-primary-hover);

    position: relative;
  }

  &__bg {
    position: absolute;
    top: 2px;
    left: 0;
    height: calc(100% - 4px);
    background: var(--bg-primary);
    border-radius: 16px;
    z-index: 1;

    &.init {
      transition:
          transform 0.25s ease,
          width 0.25s ease;
    }
  }

  &__button {
    display: flex;
    gap: 6px;
    padding: 4px 6px;

    cursor: pointer;
    font: var(--bold-12);
    align-items: center;

    position: relative;
    z-index: 10;
  }
}
</style>
