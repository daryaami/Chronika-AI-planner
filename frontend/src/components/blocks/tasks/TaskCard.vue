<script setup lang="ts">
import { Task } from "@/types/task";
import {computed, onMounted, ref, watch} from "vue";
import { useTasksStore } from "@/store/tasks";
import CustomDatePicker from "@/components/blocks/form/CustomDatePicker.vue";
import {PRIORITIES} from "@/constants/tasks";
import SelectSmall from "@/components/blocks/form/SelectSmall.vue";
import TaskCheckbox from "@/components/blocks/form/TaskCheckbox.vue";
import SelectDefault from "@/components/blocks/form/SelectDefault.vue";
import {useCalendarsStore} from "@/store/calendars";
import {Calendar} from "@/types/calendar";
import {useCategoriesStore} from "@/store/categories";
import {Category} from "@/types/category";
import DurationInput from "@/components/blocks/form/DurationInput.vue";
import TimeLogCard from "@/components/blocks/tasks/TimeLogCard.vue";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";

const taskStore = useTasksStore();

const props = defineProps<{
  task: Task;
}>();

const emit = defineEmits<{
  (e: 'close'): void
}>()

// локальный тип с датой в виде объекта
type EditableTask = Omit<Task, "due_date"> & {
  due_date: Date | null;
};

// создаём копию задачи с нормализацией даты
const taskCopy = ref<EditableTask>({
  ...props.task,
  due_date: props.task.due_date ? new Date(props.task.due_date) : null,
});


// обновление задачи (отправка на сервер)

let updateTimeout: ReturnType<typeof setTimeout>;

const updateTask = (task: EditableTask) => {
  clearTimeout(updateTimeout)

  updateTimeout = setTimeout(() => {
    const preparedTask: Task = {
      ...task,
      due_date: task.due_date ? task.due_date.toISOString() : null,
    };

    if (JSON.stringify(preparedTask) === JSON.stringify(props.task)) return;

    taskStore.updateTask(preparedTask);
  }, 500)
};

// следим за изменениями пропса (например, если обновился извне)
watch(
  () => props.task,
  (newValue) => {
    if (JSON.stringify(newValue) !== JSON.stringify(taskCopy.value)) {
      taskCopy.value = {
        ...newValue,
        due_date: newValue.due_date ? new Date(newValue.due_date) : null,
      };
    }
  },
  { deep: true }
);

watch(() => taskCopy.value.priority, () => updateTask(taskCopy.value))
watch(() => taskCopy.value.completed, () => updateTask(taskCopy.value))


// Calendars
const calendarsStore = useCalendarsStore()
const calendars = ref<Calendar[]>([])

onMounted(async ()=> {
  calendars.value = await calendarsStore.getCalendars()
})

const calendarsOptions = computed(() => {
  return calendars.value.map(c => {
    return {
      value: c.id.toString(),
      label: c.summary,
      icon: 'calendar-color',
      color: c.background_color
    }
  })
})

const userCalendarIdModel = computed({
  get: () => taskCopy.value.user_calendar_id?.toString() ?? null,
  set: (value: string) => {
    taskCopy.value.user_calendar_id = Number(value);
    updateTask(taskCopy.value);
  }
});

// Categories
const categoriesStore = useCategoriesStore()
const categories = ref<Category[]>([])

const categoriesOptions = computed(() => {
  const options = categories.value.map((c) => {
    return {
      value: c.id.toString(),
      label: c.name
    }
  })

  return [
    {
      value: null,
      label: 'Not selected'
    },
    ...options
  ]
})

onMounted(async ()=> {
  categories.value = await categoriesStore.getCategories()
})

const userCategoryIdModel = computed({
  get: () => taskCopy.value.category_id?.toString() ?? null,
  set: (value: string | null) => {
    taskCopy.value.category_id = typeof(value) === 'string'? Number(value): null
    updateTask(taskCopy.value);
  }
})

</script>

<template>
  <form class="task-card">
    <div class="task-card__header">
      <CustomDatePicker v-model="taskCopy.due_date" @update:modelValue="updateTask(taskCopy)" />
      <div class="task-card__header-divider"></div>
      <SelectSmall v-model="taskCopy.priority"
                   :options="PRIORITIES"
                   icon="flag"
                   :with-label="true"
      />

      <IconBtn class="task-card__close"
               icon="cross"
               type="button"
               @click="emit('close')"
      />
    </div>

    <div class="task-card__title-wrapper">
      <TaskCheckbox v-model="taskCopy.completed"
                    :priority="taskCopy.priority.toLowerCase()"/>
      <input
        class="task-card__title"
        type="text"
        v-model="taskCopy.title"
        @blur="updateTask(taskCopy)"
      >
    </div>

    <div class="task-card__inputs">
      <SelectDefault v-model="userCalendarIdModel"
                     :options="calendarsOptions"
                     icon="calendar-color"
      />

      <SelectDefault v-model="userCategoryIdModel"
                     :options="categoriesOptions"
                     icon="tag"
      />

      <DurationInput v-model="taskCopy.duration"/>

      <div class="scheduled">
        <div class="scheduled__title-wrapper">
          <svg width="18" height="18">
            <use href="#alarm-2"></use>
          </svg>
          <span class="scheduled__title">Scheduled</span>
        </div>

        <p class="scheduled__no-events"
           v-if="!taskCopy.time_logs.length">No upcoming events</p>

        <div class="scheduled__time-logs" v-else>
          <TimeLogCard v-for="timeLog in taskCopy.time_logs" :key="timeLog.id" :time-log="timeLog" />
        </div>


      </div>
    </div>
  </form>
</template>

<style scoped lang="scss">
.task-card {
  padding: 30px;
  border-radius: 15px;
  height: 100%;
  width: 100%;
  box-shadow: 0 0 6px 0 rgba(0, 0, 0, 0.07);
  background: var(--bg-highlight);

  &__header {
    display: flex;
    align-items: center;
    gap: 8px;

    margin-bottom: 24px;
  }

  &__close {
    margin-left: auto;
  }

  &__header-divider {
    width: 1px;
    height: 14px;
    background: var(--text-primary-disabled);
  }

  &__title-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;

    margin-bottom: 24px;
  }

  &__title {
    padding: 0;
    background: transparent;
    border: none;
    outline: none;

    width: 100%;

    font: var(--bold-18);
    color: var(--text-primary);
  }

  &__inputs {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}

.scheduled {
  width: 100%;

  &__title-wrapper {
    display: flex;
    align-items: center;
    gap: 4px;

    padding: 6px 4px;
    margin-bottom: 12px;

    & svg {
      display: block;
    }
  }

  &__title {
    font: var(--bold-14);
    color: var(--text-primary);
    display: block;
  }

  &__no-events {
    margin: 0;
    padding-left: 4px;

    font: var(--light-14);
    color: var(--text-primary-disabled);
  }

  &__time-logs {
    display: grid;
    grid-template-columns: min-content 1fr min-content;
    width: 100%;
    row-gap: 6px;
  }
}
</style>
