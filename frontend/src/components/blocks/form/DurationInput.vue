<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { vMaska } from "maska/vue"

const modelValue = defineModel<number | undefined>({ required: true })

const rawValue = ref('')

const inputRef = ref<HTMLInputElement | null>(null)

const displayedValue = computed(() => {
  const total = modelValue.value
  const hrs = Math.floor(total / 60)
  const min = total % 60

  return `${hrs > 0? hrs + ' hrs ': ''}${min} min`
})

const syncFromModel = () => {
  const total = modelValue.value
  const hrs = Math.floor(total / 60)
  const min = total % 60

  rawValue.value =
    String(hrs).padStart(2, '0') +
    ':' +
    String(min).padStart(2, '0')
}

watch(
  () => modelValue.value,
  () => {
    if (document.activeElement !== inputRef.value) {
      syncFromModel()
    }
  },
  { immediate: true }
)

const onInput = (value: string) => {
  // только обновляем rawValue, не трогаем modelValue
}

const onBlur = () => {
  const [hhStr, mmStr] = rawValue.value.split(':')
  if (!hhStr || !mmStr) return

  const hh = Number(hhStr)
  let mm = Number(mmStr.slice(0, 2))

  if (Number.isNaN(hh) || Number.isNaN(mm)) return
  if (mm > 59) mm = 59

  modelValue.value = hh * 60 + mm
  syncFromModel()
}

const maskaOptions = {
  mask: 'H*:Mm',
  tokens: {
    H: { pattern: /\d/ },
    M: { pattern: /[0-5]/ },
    m: { pattern: /\d/ }
  }
}
</script>

<template>
  <div class="duration-input">
    <label for="duration-card" class="duration-input__label">
      <svg height="18" width="18">
        <use href="#duration" />
      </svg>
      <span>Duration</span>
    </label>

    <div class="duration-input__input-wrapper">
      <input
        ref="inputRef"
        id="duration-card"
        type="text"
        class="duration-input__input"
        v-model="rawValue"
        v-maska="maskaOptions"
        @blur="onBlur"
      />

      <span class="duration-input__display-value">
        {{ displayedValue }}
      </span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.duration-input {
  display: flex;
  align-items: center;
  gap: 12px;

  &__label {
    font: var(--bold-14);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  &__input-wrapper {
    position: relative;
    padding: 8px 12px;
    background-color: var(--bg-secondary);
    border-radius: 4px;
  }

  &__input {
    font: var(--light-14);

    position: absolute;
    inset: 0;

    opacity: 0;
    width: 100%;
    height: 100%;

    text-align: center;
    border: none;
    outline: none;
    background: transparent;

    &:focus {
      opacity: 1;
    }
  }

  &__display-value {
    font: var(--light-14);
    color: var(--text-primary-disabled);
  }

  &:has(input:focus) {
    .duration-input__display-value {
      opacity: 0;
    }
  }
}
</style>
