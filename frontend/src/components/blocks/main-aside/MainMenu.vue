<script setup>
import calendarIcon from "@/assets/img/calendar.svg"
import checklistIcon from "@/assets/img/checklist.svg"
import goalIcon from "@/assets/img/goal.svg"

const menuItems = [
  {
    text: 'Мой день',
    icon: goalIcon,
    href: '/may-day/',
  },
  {
    text: 'Все мои задачи',
    icon: checklistIcon,
    href: '/tasks/',
  },
  {
    text: 'Календарь',
    icon: calendarIcon,
    href: '/planner/',
  },
]
</script>

<template>
  <nav class="main-menu">
    <ul class="main-menu__list">
      <li
        v-for="item in menuItems"
        :key="item.text"
      >
        <RouterLink :to="item.href" class="main-menu__link">
          <component :is="item.icon" />
          <span v-text="item.text"></span>
        </RouterLink>
      </li>
    </ul>

  </nav>
</template>



<style lang="scss">
@use '@/assets/scss/mixins/resets.scss' as *;
@use '@/assets/scss/mixins/mixins' as *;

.main-menu {
  &__list {
    padding: 0;
    margin: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
  }

  &__link {
    font: var(--light-16);
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 13px 30px;

    @include hover {
      background: var(--bg-primary-hover);
    }

    &.router-link-active {
      font: var(--bold-16);
      color: var(--text-accent);

      & * {
        fill: var(--text-accent)!important;
        color: var(--text-accent)!important;
      }
    }
  }

}
</style>
