<script setup lang="ts">
import {Task} from "@/types/task";
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import {useTasksStore} from "@/store/tasks";
import {ref, computed, watch, onMounted} from "vue";
import {formatDueDate} from "@/components/js/time-utils";
import TaskCheckbox from "@/components/blocks/form/TaskCheckbox.vue";
import {useCategoriesStore} from "@/store/categories";
import {Category} from "@/types/category";

const props = defineProps<{ task: Task }>()

const dueDate = computed(() => {
  if (!props.task.due_date) return
  const date = new Date(props.task.due_date)

  const dateString = formatDueDate(date)

  return `Due ${dateString}`
})

const tasksStore = useTasksStore()
const isCompleted = ref<boolean>(props.task.completed)

watch(() => isCompleted.value, (newValue) => {
  tasksStore.toggleCompleteTask(props.task.id, newValue)
})

watch(() => props.task, (newValue) => {
  isCompleted.value = newValue.completed
})


const categoriesStore = useCategoriesStore()
const categories = ref<Category[]>([])

onMounted(async () => {
  categories.value = await categoriesStore.getCategories()
})

const categoryName = computed(() => {
  const id = props.task.category_id
  if (!id) return null

  const category = categories.value.find(c => c.id === id)
  return category ? category.name : null
})

</script>

<template>
  <div class="task-item">
    <TaskCheckbox class="task-item__checkbox"
                  :priority="task.priority.toLowerCase()"
                  v-model="isCompleted"
                  @click.stop
    />
    <span class="task-item__category" v-if="categoryName">{{ categoryName }}</span>
    <span class="task-item__title">{{ task.title }}</span>
    <span class="task-item__due" v-if="dueDate">{{ dueDate }}</span>
    <IconBtn
      @click.prevent="tasksStore.deleteTask(task.id)"
      class="task-item__delete"
      icon="delete"
      size="xs"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/assets/scss/mixins/mixins.scss' as *;

.task-item {
  padding: 7px 7px 7px 36px;
  border-radius: 8px;
  box-shadow: 0 1px 4px 0 rgba(0, 0, 0, 0.07);
  background: var(--bg-highlight);
  white-space: nowrap;
  position: relative;

  cursor: pointer;

  &:has([type="checkbox"]:checked) {
    & .task-item__title {
      color: var(--icon-disabled);
      position: relative;

      &:after {
        content: '';
        width: 100%;
        height: 1px;

        background-color: var(--stroke-secondary);
        position: absolute;
        bottom: 40%;
        left: 0;
      }
    }
  }

  @include hover {
    background: var(--bg-secondary);

    & .task-item__delete {
      opacity: 1;
    }
  }

  &__checkbox {
    position: absolute;
    top: 7px;
    left: 7px;
  }

  &__category {
    display: block;

    font: var(--light-11);
    color: var(--text-primary-disabled);

    margin-bottom: 6px;
  }

  &__title {
    font: var(--light-14);
    display: block;
    width: fit-content;

    max-width: 100%;
    overflow: hidden;

    text-overflow: ellipsis;

    &:after {
      animation: line-through .3s linear;
    }
  }

  &__due {
    font: var(--light-11);
    color: var(--text-accent);
    display: block;
    margin-top: 6px;
  }

  &__delete {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    right: 7px;

    opacity: 0;
    transition: opacity 0.2s;
  }
}

@keyframes line-through {
  0% {
    width: 0;
  }

  100% {
    width: 100%;
  }
}
</style>
