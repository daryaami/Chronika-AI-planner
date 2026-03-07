<script setup lang="ts">
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import SelectSmall from "@/components/blocks/form/SelectSmall.vue";
import { SelectSmallOption } from "@/types/selectSmallOption";
import { ref, computed, onMounted } from "vue";
import { useCategoriesStore } from "@/store/categories";
import { Category } from "@/types/category";
import { useClickOutside } from "@/components/composables/useClickOutside";
import CustomDatePicker from "@/components/blocks/form/CustomDatePicker.vue";
import { useTasksStore } from "@/store/tasks";
import { TaskCreate, TaskPriority } from "@/types/task";
import { PRIORITIES } from "@/constants/tasks";

const categoriesStore = useCategoriesStore();
const tasksStore = useTasksStore();

// ----------------------------
// Focus / UI state
// ----------------------------
const isFocused = ref(false);
const containerRef = ref<HTMLElement | null>(null);

useClickOutside(containerRef, () => {
  isFocused.value = false;
});

const activateFocus = () => {
  isFocused.value = true;
};

// ----------------------------
// Form fields (value-based)
// ----------------------------
const title = ref<string>("");
const priority = ref<TaskPriority | null>(null);
const category = ref<string | null>(null);
const dueDate = ref<Date | null>(null);

// ----------------------------
// Categories
// ----------------------------
const categories = ref<Category[]>([]);

const categoriesOptions = computed<SelectSmallOption[]>(() =>
  categories.value.map((category) => ({
    label: category.name,
    value: category.id.toString(),
    icon: category.name.toLowerCase(),
  }))
);

// ----------------------------
// Derived UI state
// ----------------------------
const hasAnyValue = computed(() =>
  !!title.value ||
  !!dueDate.value ||
  !!priority.value ||
  !!category.value
);

const isExpanded = computed(() => isFocused.value || hasAnyValue.value);

// ----------------------------
// Submit
// ----------------------------
const isSubmitting = ref(false);

const submitHandler = async () => {
  if (!title.value.trim() || isSubmitting.value) return;

  isSubmitting.value = true;

  try {
    const data: TaskCreate = { title: title.value };

    if (priority.value) data.priority = priority.value;
    if (category.value) data.category_id = Number(category.value);
    if (dueDate.value) data.due_date = dueDate.value.toISOString();

    await tasksStore.createTask(data);
    resetForm();
  } finally {
    isSubmitting.value = false;
  }
};

const resetForm = () => {
  title.value = "";
  priority.value = null;
  category.value = null;
  dueDate.value = null;
};

// ----------------------------
// Init
// ----------------------------
onMounted(async () => {
  categories.value = await categoriesStore.getCategories();

  // DEFAULT PRIORITY — теперь только value
  priority.value = PRIORITIES[0].value;
});
</script>

<template>
  <form
    @submit.prevent="submitHandler"
    ref="containerRef"
    class="task-add-input"
    :class="{ filled: title.length > 0, focus: isFocused }"
  >
    <!-- Input field -->
    <div class="task-add-input__input-wrapper">
      <div class="task-add-input__placeholder" :class="{ hidden: isFocused || title.length > 0 }">
        <svg width="16" height="16">
          <use href="#plus"></use>
        </svg>
        <span>Add task</span>
      </div>

      <input
        type="text"
        class="task-add-input__input"
        placeholder="What would you like to do?"
        v-model="title"
        @focus="activateFocus"
        autocomplete="off"
        spellcheck="false"
      />
    </div>

    <!-- Buttons -->
    <div class="task-add-input__buttons" v-show="isExpanded">
      <CustomDatePicker v-model="dueDate" />

      <SelectSmall
        v-model="priority"
        :options="PRIORITIES"
        icon="flag"
      />

      <SelectSmall
        v-if="categoriesOptions.length > 0"
        v-model="category"
        :options="categoriesOptions"
        icon="tag"
      />

      <IconBtn
        type="submit"
        class="task-add-input__submit"
        icon="arrow-up"
        variant="accent"
        size="s"
        :disabled="!title.length || isSubmitting"
      />
    </div>
  </form>
</template>

<style scoped lang="scss">
.task-add-input {
  border: 1px solid var(--stroke-primary-invisible);
  border-radius: 8px;
  min-height: 33px;
  transition: border-color 0.3s ease;

  &.focus {
    border-color: var(--bg-accent);
  }

  &__input-wrapper {
    position: relative;
  }

  &__input {
    border: none;
    outline: none;
    border-radius: 0;
    background: transparent;
    display: block;
    width: 100%;
    caret-color: var(--bg-accent);
    font: var(--light-14);
    padding: 7px 8px;

    &::placeholder {
      opacity: 0;
    }
  }

  &__placeholder {
    position: absolute;
    top: 50%;
    left: 18px;
    transform: translateY(-50%);
    color: var(--text-primary-disabled);
    font: var(--light-14);
    pointer-events: none;
    display: flex;
    align-items: center;
    gap: 6px;
    opacity: 1;
    transition: opacity 0.2s ease;

    &.hidden {
      opacity: 0;
    }
  }

  &__buttons {
    padding: 4px 7px 7px 7px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  &__submit {
    margin-left: auto;
  }
}
</style>
