<script setup lang="ts">
import {computed} from "vue";

interface TaskEntityFields {
  title?: string
  due_date?: string
  duration?: number
  priority?: string
  category?: string
}

const props = defineProps<{
  fields?: TaskEntityFields
}>()

const priorityLabel = computed(() => {
  const priority = props.fields?.priority?.toLowerCase()
  if (priority === 'high') return 'Высокий'
  if (priority === 'medium') return 'Средний'
  if (priority === 'low') return 'Низкий'
  if (priority === 'critical') return 'Критический'
  return null
})

const priorityClass = computed(() => {
  const priority = props.fields?.priority?.toLowerCase()
  if (priority === 'high') return 'task-entity-block__badge--high'
  if (priority === 'medium') return 'task-entity-block__badge--medium'
  return 'task-entity-block__badge--default'
})

const dueDateLabel = computed(() => {
  const rawDate = props.fields?.due_date
  if (!rawDate) return null

  const date = new Date(rawDate)
  const weekday = date.toLocaleDateString('ru-RU', { weekday: 'short' }).replace('.', '').toUpperCase()
  const day = date.getDate()
  const month = date.toLocaleDateString('ru-RU', { month: 'long' })

  return `${weekday}, ${day} ${month}`
})

const durationLabel = computed(() => {
  const durationMinutes = props.fields?.duration
  if (!durationMinutes && durationMinutes !== 0) return null

  if (durationMinutes >= 60 && durationMinutes % 60 === 0) {
    return `${durationMinutes / 60} ч`
  }

  return `${durationMinutes} мин`
})
</script>

<template>
  <div class="task-entity-block">
    <div class="task-entity-block__meta" v-if="priorityLabel || fields?.category">
      <span class="task-entity-block__badge" :class="priorityClass" v-if="priorityLabel">
        <svg width="13" height="13">
          <use href="#flag"></use>
        </svg>
        {{ priorityLabel }}
      </span>

      <span class="task-entity-block__badge task-entity-block__badge--category" v-if="fields?.category">
        <svg width="13" height="13">
          <use href="#tag"></use>
        </svg>
        {{ fields.category }}
      </span>
    </div>

    <div class="task-entity-block__title">{{ fields?.title }}</div>

    <div class="task-entity-block__detail" v-if="dueDateLabel">
      До: {{ dueDateLabel }}
    </div>
    <div class="task-entity-block__detail" v-if="durationLabel">
      Длительность: {{ durationLabel }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.task-entity-block {
  width: 100%;
  display: flex;
  flex-direction: column;

  &__meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 2px;
  }

  &__badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font: var(--bold-12);
  }

  &__badge--high {
    color: var(--text-error);
  }

  &__badge--medium {
    color: var(--medium);
  }

  &__badge--default {
    color: var(--text-primary-disabled);
  }

  &__badge--category {
    color: var(--text-accent);
  }

  &__title {
    color: var(--text-primary);
    font: var(--bold-14);
    max-width: 100%;
    overflow-wrap: anywhere;
  }

  &__detail {
    color: var(--text-primary-muted);
    font: var(--light-14);
  }
}
</style>
