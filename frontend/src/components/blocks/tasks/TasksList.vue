<script setup lang="ts">
import {useTasksStore} from "@/store/tasks";
import {computed, onMounted, ref, watch} from "vue";
import {Task} from "@/types/task";
import TaskItem from "@/components/blocks/tasks/TaskItem.vue";

defineProps<{
  modelValue: Task | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: Task | null): void;
}>();

const tasksStore = useTasksStore()

const tasks = ref<Task[]>([])
type TaskGroup = {
  key: "today" | "tomorrow" | "week" | "later" | "other";
  title: string;
  tasks: Task[];
};

const startOfDay = (date: Date) => {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  return result;
};

const isSameDay = (left: Date, right: Date) =>
  left.getFullYear() === right.getFullYear() &&
  left.getMonth() === right.getMonth() &&
  left.getDate() === right.getDate();

const endOfWeek = (date: Date) => {
  const start = startOfDay(date);
  const day = start.getDay();
  const diff = day === 0 ? 6 : day - 1;
  const monday = new Date(start);
  monday.setDate(start.getDate() - diff);

  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  sunday.setHours(23, 59, 59, 999);
  return sunday;
};

const activeTasks = computed(() => tasks.value.filter((task) => !task.completed));
const completedTasks = computed(() => tasks.value.filter((task) => task.completed));

const sortedTasks = computed(() => {
  return [...activeTasks.value].sort((a, b) => {
    const aHasDate = !!a.due_date;
    const bHasDate = !!b.due_date;

    if (aHasDate && bHasDate) {
      return new Date(a.due_date!).getTime() - new Date(b.due_date!).getTime();
    }

    if (aHasDate) return -1;
    if (bHasDate) return 1;
    return 0;
  });
});

const groupedTasks = computed<TaskGroup[]>(() => {
  const withDate = sortedTasks.value.filter((task) => !!task.due_date);
  const withoutDate = sortedTasks.value.filter((task) => !task.due_date);

  if (!withDate.length) {
    return withoutDate.length
      ? [{ key: "other", title: "Без срока", tasks: withoutDate }]
      : [];
  }

  const today = startOfDay(new Date());
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const weekEnd = endOfWeek(today);

  const groups: TaskGroup[] = [
    { key: "today", title: "Сегодня", tasks: [] },
    { key: "tomorrow", title: "Завтра", tasks: [] },
    { key: "week", title: "На этой неделе", tasks: [] },
    { key: "later", title: "Позже", tasks: [] },
  ];

  for (const task of withDate) {
    const dueDate = new Date(task.due_date!);
    if (dueDate < today || isSameDay(dueDate, today)) {
      groups[0].tasks.push(task);
    } else if (isSameDay(dueDate, tomorrow)) {
      groups[1].tasks.push(task);
    } else if (dueDate > tomorrow && dueDate <= weekEnd) {
      groups[2].tasks.push(task);
    } else {
      groups[3].tasks.push(task);
    }
  }

  const visibleGroups = groups.filter((group) => group.tasks.length);
  if (withoutDate.length) {
    visibleGroups.push({ key: "other", title: "Без срока", tasks: withoutDate });
  }

  return visibleGroups;
});


onMounted(async () => {
  tasks.value = await tasksStore.getTasks()
})

watch(() => tasksStore.tasks, async () => {
  tasks.value = await tasksStore.getTasks()
})
</script>

<template>
  <div>
    <div class="tasks-list-wrapper"
         v-for="group in groupedTasks"
         :key="group.key">
      <span class="tasks-list-wrapper__title">{{ group.title }}</span>
      <div class="tasks-list">
        <TaskItem v-for="task in group.tasks"
                  :key="task.id"
                  :task="task" @click="emit('update:modelValue', task)"
        />
      </div>
    </div>

    <div class="tasks-list-wrapper"
         v-if="completedTasks.length">
      <span class="tasks-list-wrapper__title">Завершено</span>
      <div class="tasks-list">
        <TaskItem v-for="task in completedTasks"
                  :key="task.id"
                  :task="task" @click="emit('update:modelValue', task)"
        />
      </div>
    </div>
  </div>

</template>

<style scoped lang="scss">
.tasks-list-wrapper {
  & + .tasks-list-wrapper {
    margin-top: 30px;
  }
  &__title {
    display: block;
    padding: 0 6px;
    margin-bottom: 14px;

    font: var(--bold-20);
  }
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
