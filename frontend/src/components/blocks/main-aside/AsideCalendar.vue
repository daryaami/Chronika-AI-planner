<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import IconBtn from "@/components/ui-kit/btns/IconBtn.vue";
import {getCurrentWeekMonday, getTomorrow} from "@/components/js/time-utils";
import { useRoute, useRouter } from "vue-router";

const props = defineProps({
  initialDate: {
    type: Date,
    default: () => new Date(),
  },
})

const weekDays = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const currentCalendarDate = ref(props.initialDate)
const selectedDate = ref(new Date(props.initialDate))
const route = useRoute()
const router = useRouter()

const toDateQuery = (date: Date): string => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const fromDateQuery = (value: unknown): Date | null => {
  if (typeof value !== 'string') return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null

  const [, yearRaw, monthRaw, dayRaw] = match
  const year = Number(yearRaw)
  const month = Number(monthRaw)
  const day = Number(dayRaw)
  const date = new Date(year, month - 1, day)

  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null
  }

  return date
}

const syncSelectedDateFromRoute = () => {
  const routeDate = fromDateQuery(route.query.date)
  if (!routeDate) return

  selectedDate.value = routeDate
  currentCalendarDate.value = new Date(routeDate)
}

const days = computed(() => {
  const daysArr = []

  let firstDayOfMonth;
  let firstDay;

  firstDayOfMonth = new Date(currentCalendarDate.value);
  firstDayOfMonth = new Date(firstDayOfMonth.setDate(1));

  firstDay = getCurrentWeekMonday(firstDayOfMonth);

  daysArr.push(firstDay)

  for(let i = 0; i < 34; i++) {
    const newDay = getTomorrow(daysArr[i]);
    daysArr.push(newDay);
  }

  return daysArr
})

const currentMonth = computed(() => {
  return `${currentCalendarDate.value.toLocaleString('en-US', { month: 'long' })} ${currentCalendarDate.value.getFullYear()}`;
})

const nextMonthHandler = () => {
  currentCalendarDate.value = new Date(currentCalendarDate.value.setMonth(currentCalendarDate.value.getMonth() + 1))
}

const prevMonthHandler = () => {
  currentCalendarDate.value = new Date(currentCalendarDate.value.setMonth(currentCalendarDate.value.getMonth() - 1))
}

const selectDay = async (day: Date) => {
  const dayCopy = new Date(day)
  selectedDate.value = dayCopy
  currentCalendarDate.value = new Date(dayCopy)

  const nextQuery = {
    ...route.query,
    date: toDateQuery(dayCopy)
  }

  if (route.path === '/planner') {
    await router.replace({ query: nextQuery })
    return
  }

  await router.push({ path: '/planner', query: nextQuery })
}

watch(
  () => route.query.date,
  () => {
    syncSelectedDateFromRoute()
  },
  { immediate: true }
)
</script>

<template>
  <div class="aside-calendar">
    <div class="aside-calendar__wrapper">
      <div class="aside-calendar__month-wrapper">
        <span class="aside-calendar__month">{{ currentMonth }}</span>
        <div class="aside-calendar__buttons-wrapper">
          <IconBtn
            @click="prevMonthHandler"
            icon="chevron-left"
            size="xs"
          />

          <IconBtn
            @click="nextMonthHandler"
            icon="chevron-right"
            size="xs"
          />
        </div>
      </div>

      <div class="aside-calendar__header aside-calendar__grid">
        <span class="aside-calendar__weekday"
          v-for="(weekDay, i) in weekDays"
          :key="i"
        >
          {{ weekDay }}
        </span>
      </div>

      <div class="aside-calendar__calendar aside-calendar__grid">
        <button class="aside-calendar__day aside-calendar__date"
          v-for="(day, i) in days"
          :key="i"
          @click="selectDay(day)"
          :class="{
            'today': day.toDateString() === new Date().toDateString(),
            'active': day.toDateString() === selectedDate.toDateString()
          }"
        >
            {{ day.getDate() }}
      </button>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/assets/scss/mixins/resets.scss' as *;
@use '@/assets/scss/mixins/mixins' as *;

.aside-calendar {
  margin: 0 30px 45px 30px;

  &__wrapper {
    width: fit-content;
  }

  &__month-wrapper {
    margin-bottom: 42px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__month {
    font: var(--bold-16);
  }

  &__grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    column-gap: 11px;
    row-gap: 10px;
  }

  &__header {
    width: fit-content;
    margin-bottom: 15px;
  }

  &__weekday {
    font: var(--bold-12);
    color: var(--text-primary-disabled);
    width: 22px;
    display: block;
    text-align: center;
  }

  &__calendar {
    width: fit-content;
  }

  &__date {
    @include reset-button;
    border-radius: 50%;
  }

  &__day {
    font: var(--bold-12);
    color: var(--text-primary-muted);
    background-color: var(--bg-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;

    @include hover {
      background: var(--bg-primary-hover);
    }

    &.today {
      background: var(--bg-accent);
      color: var(--text-secondary);
    }

    &.active {
      background: var(--bg-highlight);
      color: var(--text-primary);
    }
  }



  &__buttons-wrapper {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}
</style>
