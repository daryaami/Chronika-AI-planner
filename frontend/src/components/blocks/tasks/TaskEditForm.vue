<script setup lang="ts">
import { Task } from "@/types/task";
import { computed, ref, watch, onMounted } from "vue";
import { useTasksStore } from "@/store/tasks";
import CustomDatePicker from "@/components/blocks/form/CustomDatePicker.vue";
import { PRIORITIES } from "@/constants/tasks";
import SelectSmall from "@/components/blocks/form/SelectSmall.vue";
import TaskCheckbox from "@/components/blocks/form/TaskCheckbox.vue";
import SelectDefault from "@/components/blocks/form/SelectDefault.vue";
import { useCalendarsStore } from "@/store/calendars";
import { Calendar } from "@/types/calendar";
import { useCategoriesStore } from "@/store/categories";
import { Category } from "@/types/category";
import DurationInput from "@/components/blocks/form/DurationInput.vue";
import TimeLogCard from "@/components/blocks/tasks/TimeLogCard.vue";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import ActionBtn from "@/components/ui-kit/btns/ActionBtn.vue";

const taskStore = useTasksStore();
const calendarsStore = useCalendarsStore();
const categoriesStore = useCategoriesStore();

const props = defineProps<{
  task: Task;
  mode: 'popup' | 'card';
  showActions?: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'save', task: Task): void;
  (e: 'delete', taskId: number): void;
}>();

// Локальный тип с датой в виде объекта
type EditableTask = Omit<Task, "due_date"> & {
  due_date: Date | null;
};

// Создаём копию задачи с нормализацией даты
const taskCopy = ref<EditableTask>({
  ...props.task,
  due_date: props.task.due_date ? new Date(props.task.due_date) : null,
});

// Обновление задачи (отправка на сервер)
let updateTimeout: ReturnType<typeof setTimeout>;

const updateTask = (task: EditableTask) => {
  clearTimeout(updateTimeout);

  updateTimeout = setTimeout(async () => {
    const preparedTask: Task = {
      ...task,
      due_date: task.due_date ? task.due_date.toISOString() : null,
      el: null,
    };

    // Сравниваем без el
    const taskWithoutEl = ({ el, ...rest }: any) => rest;
    if (JSON.stringify(taskWithoutEl(preparedTask)) === JSON.stringify(taskWithoutEl(props.task))) return;

    await taskStore.updateTask(preparedTask);
    emit('save', preparedTask);
  }, 500);
};

// Следим за изменениями пропса (например, если обновился извне)
watch(
  () => props.task,
  (newValue) => {
    const taskWithoutEl = ({ el, ...rest }: any) => rest;
    if (JSON.stringify(taskWithoutEl(newValue)) !== JSON.stringify(taskWithoutEl(taskCopy.value))) {
      taskCopy.value = {
        ...newValue,
        due_date: newValue.due_date ? new Date(newValue.due_date) : null,
      };
    }
  },
  { deep: true }
);

watch(() => taskCopy.value.priority, () => updateTask(taskCopy.value));
watch(() => taskCopy.value.completed, () => updateTask(taskCopy.value));
watch(() => taskCopy.value.duration, () => updateTask(taskCopy.value));

// Calendars
const calendars = ref<Calendar[]>([]);

const loadCalendars = async () => {
  calendars.value = await calendarsStore.getOwnedCalendars();
};

// Categories
const categories = ref<Category[]>([]);

const loadCategories = async () => {
  categories.value = await categoriesStore.getCategories();
};

onMounted(async () => {
  await Promise.all([loadCalendars(), loadCategories()]);
});

const calendarsOptions = computed(() => {
  return calendars.value.map(c => {
    return {
      value: c.id.toString(),
      label: c.summary,
      icon: 'calendar-color',
      color: c.background_color
    };
  });
});

const userCalendarIdModel = computed({
  get: () => taskCopy.value.user_calendar_id?.toString() ?? null,
  set: (value: string) => {
    taskCopy.value.user_calendar_id = Number(value);
    updateTask(taskCopy.value);
  }
});

const categoriesOptions = computed(() => {
  const options = categories.value.map((c) => {
    return {
      value: c.id.toString(),
      label: c.name
    };
  });

  return [
    {
      value: null,
      label: 'Не выбрано'
    },
    ...options
  ];
});

const userCategoryIdModel = computed({
  get: () => taskCopy.value.category_id?.toString() ?? null,
  set: (value: string | null) => {
    taskCopy.value.category_id = typeof value === 'string' ? Number(value) : null;
    updateTask(taskCopy.value);
  }
});

const handleClose = () => {
  emit('close');
};

const handleDelete = () => {
  emit('delete', props.task.id);
};

const handleSave = () => {
  // Запускаем сохранение с debounce
  updateTask(taskCopy.value);
  // emit('save') будет вызван после завершения сохранения в updateTask
};
</script>

<template>
  <form class="task-edit-form" @submit.prevent="handleSave">
    <div class="task-edit-form__header" v-if="mode === 'popup'">
      <div class="task-edit-form__header-btns">
        <IconBtn
          v-if="showActions"
          icon="delete"
          size="s"
          variant="secondary"
          @click="handleDelete"
          type="button"
        />
        <IconBtn
          icon="cross"
          size="s"
          @click="handleClose"
          type="button"
        />
      </div>
    </div>

    <div class="task-edit-form__content">
      <div class="task-edit-form__header-fields">
        <CustomDatePicker
          v-model="taskCopy.due_date"
          :enable-time-picker="false"
          position="left"
          :teleport-to="mode === 'popup' ? '#task-edit-dialog' : 'body'"
          @update:modelValue="updateTask(taskCopy)"
        />
        <div class="task-edit-form__header-divider"></div>
        <SelectSmall
          v-model="taskCopy.priority"
          :options="PRIORITIES"
          icon="flag"
          :with-label="true"
        />
      </div>

      <div class="task-edit-form__title-wrapper">
        <TaskCheckbox
          v-model="taskCopy.completed"
          :priority="taskCopy.priority.toLowerCase()"
        />
        <input
          class="task-edit-form__title"
          type="text"
          v-model="taskCopy.title"
          @blur="updateTask(taskCopy)"
          placeholder="Название задачи"
        >
      </div>

      <div class="task-edit-form__inputs">
        <SelectDefault
          v-model="userCalendarIdModel"
          :options="calendarsOptions"
          icon="calendar-color"
        />

        <SelectDefault
          v-model="userCategoryIdModel"
          :options="categoriesOptions"
          icon="tag"
        />

        <DurationInput v-model="taskCopy.duration" />

        <div class="scheduled">
          <div class="scheduled__title-wrapper">
            <svg width="18" height="18">
              <use href="#alarm-2"></use>
            </svg>
            <span class="scheduled__title">Запланировано</span>
          </div>

          <p class="scheduled__no-events" v-if="!taskCopy.events.length">
            Нет предстоящих событий
          </p>

          <div class="scheduled__time-logs" v-else>
            <TimeLogCard
              v-for="timeLog in taskCopy.events"
              :key="timeLog.id"
              :time-log="timeLog"
            />
          </div>
        </div>
      </div>
    </div>

    <div class="task-edit-form__footer" v-if="mode === 'popup' && showActions">
      <!-- <ActionBtn text="Отменить" variant="secondary" @click="handleClose" /> -->
      <ActionBtn text="Сохранить" variant="primary" @click="handleSave" type="submit" />
    </div>
  </form>
</template>

<style scoped lang="scss">
.task-edit-form {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;

  &__header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 16px;

    &-btns {
      display: flex;
      gap: 12px;
    }
  }

  &__content {
    flex-grow: 1;
  }

  &__header-fields {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 24px;
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

  &__footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 32px;
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
