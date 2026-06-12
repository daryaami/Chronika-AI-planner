<script setup lang="ts">
import { ref, nextTick } from 'vue';
import { Task } from "@/types/task";
import TaskEditForm from "@/components/blocks/tasks/TaskEditForm.vue";
import { useTasksStore } from "@/store/tasks";

const dialog = ref<HTMLDialogElement | null>(null);
const currentTask = ref<Task | null>(null);

const taskStore = useTasksStore();

const open = async (task: Task) => {
  currentTask.value = task;
  dialog.value?.showModal();
  await nextTick();
};

const close = () => {
  currentTask.value = null;
  dialog.value?.close();
};

const handleSave = async (task: Task) => {
  await taskStore.updateTask(task);
  close();
};

const handleDelete = async (taskId: number) => {
  await taskStore.deleteTask(taskId);
  close();
};

defineExpose({ open, close });
</script>

<template>
  <dialog class="task-edit-popup" ref="dialog" id="task-edit-dialog">
    <TaskEditForm
      v-if="currentTask"
      :task="currentTask"
      mode="popup"
      :show-actions="true"
      @close="close"
      @save="handleSave"
      @delete="handleDelete"
    />
  </dialog>
</template>

<style lang="scss">
// Телепортированный календарь внутри dialog
#task-edit-dialog {
  .dp__menu {
    position: fixed !important;
  }
}
</style>

<style lang="scss">
.task-edit-popup {
  border: none;
  outline: none;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  background: var(--bg-highlight);
  border-radius: 16px;
  padding: 24px;
  max-width: 516px;
  width: 100%;
  overflow: visible;

  &::backdrop {
    background: rgba(0, 0, 0, 0.5);
  }

  & .dp--menu-wrapper {
    position: fixed!important;
  }
}
</style>
