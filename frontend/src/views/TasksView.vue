<script setup lang="ts">
import TaskHeader from "@/components/blocks/tasks/TaskHeader.vue";
import checklistIcon from "@/assets/img/checklist.svg";
import TasksList from "@/components/blocks/tasks/TasksList.vue";
import TaskAddInput from "@/components/blocks/tasks/TaskAddInput.vue";
import {Task} from "@/types/task";
import {ref, watch} from "vue";
import TaskCard from "@/components/blocks/tasks/TaskCard.vue";
import {useTasksStore} from "@/store/tasks";

const activeTask = ref<Task | null>(null)
const taskStore = useTasksStore()

watch(
  () => taskStore.tasks,
  () => {
    if (!activeTask.value) return
    const updated = taskStore.tasks.find(t => t.id === activeTask.value!.id)
    if (updated) {
      activeTask.value = { ...updated }
    } else {
      activeTask.value = null
    }
  },
  { deep: true }
)
</script>

<template>
  <TaskHeader
    title="All my tasks"
    :icon="checklistIcon"
  />
  <div class="tasks-page">
    <div class="tasks-page__main">
      <TaskAddInput class="tasks-page__form"/>
      <TasksList
        v-model="activeTask"
      />
    </div>
    <TaskCard v-if="activeTask"
              :task="activeTask"
              @close="activeTask = null"
    />
  </div>
</template>

<style scoped lang="scss">
.tasks-page {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;

  padding: 24px 30px 44px;

  flex-shrink: 1;
  flex-grow: 1;

  min-height: 0;
  overflow: hidden;

  &__main {
    width: 100%;
    overflow: hidden;
    min-width: 0;
  }

  &__form {
    margin-bottom: 30px;
  }
}
</style>
