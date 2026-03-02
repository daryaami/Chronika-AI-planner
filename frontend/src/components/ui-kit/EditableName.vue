<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import IconBtn from "@/components/ui-kit/IconBtn.vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  placeholder: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:modelValue']);
const el = ref(null);
const isEditable = ref(false);

const syncFromModel = () => {
  if (!el.value) return;
  if (el.value.textContent !== props.modelValue) {
    el.value.textContent = props.modelValue;
  }
};

const onInput = () => {
  emit('update:modelValue', el.value.textContent);
};

const onPaste = e => {
  e.preventDefault();
  const text = e.clipboardData.getData('text/plain');
  document.execCommand('insertText', false, text);
};

const focusOnName = () => {
  isEditable.value = true;
  setTimeout(() => el.value.focus(), 200);
}

onMounted(syncFromModel);
watch(() => props.modelValue, syncFromModel);
</script>

<template>
  <div class="editable-name">
    <div
      ref="el"
      class="editable-name__input"
      :contenteditable="isEditable"
      role="textbox"
      aria-multiline="false"
      :data-placeholder="placeholder"
      @input="onInput"
      @keydown.enter.prevent
      @paste="onPaste"
      @blur="isEditable = false"
    ></div>

    <IconBtn icon="edit"
             @click="focusOnName"
    />
  </div>
</template>

<style scoped lang="scss">
.editable-name {
  display: flex;
  align-items: center;
  gap: 22px;

  &__input {
    display: block;
    min-width: 1ch;
    white-space: nowrap;
    outline: none;

    width: fit-content;
    font: var(--title-30)
  }
}
</style>
