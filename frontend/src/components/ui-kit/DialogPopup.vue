<script setup lang="ts">
import { withDefaults, defineProps, defineEmits, ref, watch, nextTick } from 'vue'
import ActionBtn from './btns/ActionBtn.vue'
import IconBtn from './btns/IconBtn.vue'

defineOptions({
  name: 'DialogPopup',
})

interface Props {
  modelValue: boolean
  title?: string
  confirmText?: string
  cancelText?: string
  type?: 'small' | 'default',
  isConfirmDisabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Title',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  type: 'default',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const dialogRef = ref<HTMLDialogElement | null>(null)

const openDialog = async () => {
  await nextTick()
  if (dialogRef.value && !dialogRef.value.open) {
    dialogRef.value.showModal()
  }
}

const closeDialog = () => {
  if (dialogRef.value?.open) {
    dialogRef.value.close()
  }
}

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      openDialog()
    } else {
      closeDialog()
    }
  },
  { immediate: true }
)

const close = (emitCancel = false) => {
  if (emitCancel) {
    emit('cancel')
  }
  emit('update:modelValue', false)
}

const onCancel = () => {
  emit('cancel')
  close()
}

const onConfirm = () => {
  emit('confirm')
  close()
}

const onBackdropClick = (e: MouseEvent) => {
  if (e.target === dialogRef.value) {
    onCancel()
  }
}

const onNativeClose = () => {
  emit('update:modelValue', false)
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="modal"
    :class="type === 'small'? 'modal--small': ''"
    @click="onBackdropClick"
    @cancel="onNativeClose"
  >
    <div class="modal__header" v-if="type === 'default'">
      <div class="modal__title">
        {{ title }}
      </div>

      <IconBtn icon="cross" size="s" @click="close(true)" />
    </div>

    <div class="modal__body">
      <slot></slot>
    </div>

    <div class="modal__footer" :class="type === 'small'? 'modal__footer--small': ''">
      <ActionBtn
        :text="cancelText"
        type="secondary"
        @click="onCancel"
      />

      <ActionBtn
        :text="confirmText"
        type="primary"
        @click="onConfirm"
        :disabled="isConfirmDisabled"
      />
    </div>
  </dialog>
</template>

<style lang="scss" scoped>
.modal {
  border: none;
  border-radius: 8px;
  padding: 12px 16px;
  width: 100%;
  max-width: 360px;
  box-shadow:
    0 20px 25px -5px rgba(0, 0, 0, 0.1),
    0 10px 10px -5px rgba(0, 0, 0, 0.04);

  &::backdrop {
    background: rgba(0, 0, 0, 0.5);
  }

  &--small {
    max-width: 300px;
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    margin-bottom: 12px;
  }

  &__title {
    font: var(--bold-18);
  }

  &__body {
    margin-bottom: 24px;
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;

    &--small {
      justify-content: center;

      & button {
        width: 100%;
      }
    }
  }
}
</style>
