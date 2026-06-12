<script setup lang="ts">
import { Task } from "@/types/task";
import TaskEditForm from "@/components/blocks/tasks/TaskEditForm.vue";

const props = defineProps<{
  task: Task;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'save', task: Task): void;
}>();
</script>

<template>
  <div class="task-card">
    <TaskEditForm
      :task="task"
      mode="card"
      @close="emit('close')"
      @save="(task) => emit('save', task)"
    />
  </div>
</template>

<style scoped lang="scss">
.task-card {
  padding: 30px;
  border-radius: 15px;
  height: 100%;
  overflow-x: visible;
  width: 100%;
  box-shadow: 0 0 6px 0 rgba(0, 0, 0, 0.07);
  background: var(--bg-highlight);
}
</style>
