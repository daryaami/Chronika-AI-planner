<script setup lang="ts">
import {useTasksStore} from "@/store/tasks";
import {onMounted, ref, watch} from "vue";
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
const inboxTasks = ref<Task[]>([])
const todayTasks = ref<Task[]>([])
const nextWeekTasks = ref<Task[]>([])
const laterTasks = ref<Task[]>([])
const completedTasks = ref<Task[]>([])

const sortTasks = () => {
  const sortedToInbox: Task[] = []
  const sortedToToday: Task[] = []
  const sortedToNextWeek: Task[] = []
  const sortedToLater: Task[] = []
  const sortedToCompleted: Task[] = []

  const now = new Date()

  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  )

  const endOfToday = new Date(startOfToday)
  endOfToday.setDate(endOfToday.getDate() + 1)

  const endOfNextWeek = new Date(startOfToday)
  endOfNextWeek.setDate(endOfNextWeek.getDate() + 7)

  tasks.value.forEach((item) => {
    if (item.completed) {
      sortedToCompleted.push(item)
      return;
    }

    if (!item.events.length) {
      sortedToInbox.push(item)
      return
    }

    // сортируем логи по возрастанию
    const sortedLogs = [...item.events].sort(
      (a, b) =>
        new Date(a.start_time).getTime() -
        new Date(b.start_time).getTime()
    )

    // ищем ближайший лог в будущем
    const nextLog = sortedLogs.find(
      (log) => new Date(log.start_time) >= now
    )

    if (!nextLog) {
      // все логи в прошлом
      sortedToInbox.push(item)
      return
    }

    const logDate = new Date(nextLog.start_time)

    if (logDate >= startOfToday && logDate < endOfToday) {
      sortedToToday.push(item)
    } else if (logDate < endOfNextWeek) {
      sortedToNextWeek.push(item)
    } else {
      sortedToLater.push(item)
    }
  })

  inboxTasks.value = sortedToInbox
  todayTasks.value = sortedToToday
  nextWeekTasks.value = sortedToNextWeek
  laterTasks.value = sortedToLater
  completedTasks.value = sortedToCompleted
}


onMounted(async () => {
  tasks.value = await tasksStore.getTasks()
  sortTasks()
})

watch(() => tasksStore.tasks, async () => {
  tasks.value = await tasksStore.getTasks()
  sortTasks()
})
</script>

<template>
  <div>
    <div class="tasks-list-wrapper"
         v-if="todayTasks.length"
    >
      <span class="tasks-list-wrapper__title">Today</span>
      <div class="tasks-list">
        <TaskItem v-for="task in todayTasks"
                  :key="task.id"
                  :task="task" @click="emit('update:modelValue', task)"
        />
      </div>
    </div>


    <!--  Список nextWeekTasks  -->
    <div class="tasks-list-wrapper"
         v-if="nextWeekTasks.length">
      <span class="tasks-list-wrapper__title">Next week</span>
      <div class="tasks-list">
        <TaskItem v-for="task in nextWeekTasks"
                  :key="task.id"
                  :task="task" @click="emit('update:modelValue', task)"
        />
      </div>
    </div>


    <!--  Список laterTasks  -->
    <div class="tasks-list-wrapper" v-if="laterTasks.length">
      <span class="tasks-list-wrapper__title">Later</span>
      <div class="tasks-list">
        <TaskItem v-for="task in laterTasks"
                  :key="task.id"
                  :task="task" @click="emit('update:modelValue', task)"
        />
      </div>
    </div>

    <div class="tasks-list-wrapper"
         v-if="inboxTasks.length">
      <span class="tasks-list-wrapper__title">Inbox</span>
      <div class="tasks-list">
        <TaskItem v-for="task in inboxTasks"
                  :key="task.id"
                  :task="task" @click="emit('update:modelValue', task)"
        />
      </div>
    </div>

    <div class="tasks-list-wrapper"
         v-if="completedTasks.length">
      <span class="tasks-list-wrapper__title">Completed</span>
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
