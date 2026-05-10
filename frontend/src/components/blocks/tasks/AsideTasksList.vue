<script setup lang="ts">
import {ComponentPublicInstance, computed, ref, watch} from "vue";
import {useTasksStore} from "@/store/tasks";
import {onMounted} from "vue";
import { Draggable } from '@fullcalendar/interaction';
import TaskItem from "@/components/blocks/tasks/TaskItem.vue";
import {Task, UiTask} from "@/types/task";
import TaskAddInput from "@/components/blocks/tasks/TaskAddInput.vue";

const tasksStore = useTasksStore()

const tasks = ref<UiTask[]>([])
const draggableEls: Draggable[] = []

type TaskGroup = {
  key: "today" | "tomorrow" | "week" | "later" | "other";
  title: string;
  tasks: UiTask[];
};

const toUiTasks = (items: Task[]): UiTask[] =>
  items.map((t) => ({ ...t, el: null }));

const loadTasks = async () => {
  const data = await tasksStore.getTasks()
  tasks.value = toUiTasks(data)
}

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

const sortedTasks = computed(() => {
  return [...tasks.value].sort((a, b) => {
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
    return [
      {
        key: "other",
        title: "Без срока",
        tasks: withoutDate,
      },
    ];
  }

  const now = new Date();
  const today = startOfDay(now);
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
    visibleGroups.push({
      key: "other",
      title: "Без срока",
      tasks: withoutDate,
    });
  }

  return visibleGroups;
});

onMounted(async () => {
  await loadTasks()
})

watch(
  () => tasksStore.tasks,
  async (newTasks) => {
    tasks.value = toUiTasks(newTasks)
    window.dispatchEvent(new Event('resize'))
  },
  { deep: true },
)

// Draggable
const DEFAULT_DURATION = '00:30'

const setTaskEl = (el: Element | ComponentPublicInstance | null, task: UiTask) => {
  if (!(el instanceof HTMLElement)) return;
  task.el = el;

  if (!el) return;

  // если уже инициализирован — второй раз не создаём
  if ((el as any)._draggableInstance) return;

  const draggable = new Draggable(el, {
      eventData: {
        title: task.title,
        duration: task.duration? task.duration * 60000: DEFAULT_DURATION,
      }
  });

  (el as any)._draggableInstance = draggable
  draggableEls.push(draggable)
}

</script>

<template>
  <div class="aside-tasks">
    <div class="aside-tasks__title-wrapper">
      <svg width="24" height="24" xmlns="http://www.w3.org/2000/svg">
        <use href="#bulb"></use>
      </svg>
      <h2 class="aside-tasks__title">Plan now</h2>
      <span class="aside-tasks__counter" v-if="tasksStore.tasks.length">{{ tasksStore.tasks.length? tasksStore.tasks.length: '' }}</span>
    </div>
    <TaskAddInput />
    <TransitionGroup name="list" tag="div" class="aside-tasks__list">
      <section
          v-for="group in groupedTasks"
          :key="group.key"
          class="aside-tasks__group"
      >
        <h3 class="aside-tasks__group-title">{{ group.title }}</h3>
        <div
            v-for="task in group.tasks"
            :key="task.id"
            :ref="el => setTaskEl(el, task)"
            :data-task-id="task.id"
        >
          <TaskItem :task="task" />
        </div>
      </section>
    </TransitionGroup>
  </div>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/resets' as *;

.list-move, /* apply transition to moving elements */
.list-enter-active,
.list-leave-active {
  transition: all 0.5s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
}

/* ensure leaving items are taken out of layout flow so that moving
   animations can be calculated correctly. */
.list-leave-active {
  opacity: 0;
  position: absolute;
  width: 100%;
}

.aside-tasks {
  width: 330px;
  padding: 22px 12px;
  box-shadow: 0 0 18px 0 rgba(0, 0, 0, 0.08);
  z-index: 10;
  position: relative;

  &__title-wrapper {
    display: flex;
    align-items: flex-end;
    gap: 14px;
    margin-bottom: 33px;
    padding-left: 8px;

    & svg {
      display: block;
    }
  }

  &__title {
    font: var(--light-20);
    margin: 0;
  }

  &__counter {
    font: var(--light-20);
    display: block;
    color: var(--text-accent);
  }

  &__list {
    @include reset-list;
    display: flex;
    flex-direction: column;
    gap: 8px;
    position: relative;

    margin-top: 16px;

    & .task-item {
      width: 100%;
    }
  }

  &__group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  &__group-title {
    margin: 8px 0 4px;
    padding-left: 8px;
    font: var(--medium-14);
  }
}
</style>
