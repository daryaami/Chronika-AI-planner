<script setup lang="ts">
import {ref, watch, onMounted, useTemplateRef} from 'vue';
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";

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
const el = useTemplateRef('el');
const isEditable = ref(false);

const syncFromModel = () => {
  if (!el.value) return;
  if (el.value.textContent !== props.modelValue) {
    el.value.textContent = props.modelValue;
  }
};

const onBlur = () => {
  emit('update:modelValue', el.value?.textContent ?? '');
  isEditable.value = false;
};

const onPaste = e => {
  e.preventDefault();
  const text = e.clipboardData.getData('text/plain');
  document.execCommand('insertText', false, text);
};

const focusOnName = () => {
  isEditable.value = true;
  setTimeout(() => {
    if (!el.value) return;
    el.value.focus();
    const range = document.createRange();
    const sel = window.getSelection();
    range.selectNodeContents(el.value);
    range.collapse(false);
    sel?.removeAllRanges();
    sel?.addRange(range);
  }, 200);
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
      @keydown.enter.prevent
      @paste="onPaste"
      @blur="onBlur"
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
