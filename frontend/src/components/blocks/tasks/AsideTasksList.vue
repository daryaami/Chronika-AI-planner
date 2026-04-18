<script setup lang="ts">
import {ComponentPublicInstance, ref, watch} from "vue";
import {useTasksStore} from "@/store/tasks";
import {onMounted} from "vue";
import { Draggable } from '@fullcalendar/interaction';
import TaskItem from "@/components/blocks/tasks/TaskItem.vue";
import {Task, UiTask} from "@/types/task";
import TaskAddInput from "@/components/blocks/tasks/TaskAddInput.vue";

const tasksStore = useTasksStore()

const tasks = ref<UiTask[]>([])
const draggableEls: Draggable[] = []

const toUiTasks = (items: Task[]): UiTask[] =>
  items.map((t) => ({ ...t, el: null }));

const loadTasks = async () => {
  const data = await tasksStore.getTasks()
  tasks.value = toUiTasks(data)
}

onMounted(async () => {
  await loadTasks()
})

watch(
  () => tasksStore.tasks,
  async (newTasks) => {
    tasks.value = toUiTasks(newTasks)
    window.dispatchEvent(new Event('resize'))
  },
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
      <div
          v-for="task in tasks"
          :key="task.id"
          :ref="el => setTaskEl(el, task)"
          :data-task-id="task.id"
      >
        <TaskItem :task="task" />
      </div>
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
}
</style>
