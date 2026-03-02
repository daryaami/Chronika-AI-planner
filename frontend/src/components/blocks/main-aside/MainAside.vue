<script setup>
import MainMenu from "./MainMenu.vue";
import AsideCalendar from "./AsideCalendar.vue";
import logoIconURL from "@/assets/img/logo.svg?url";
</script>

<template>
  <div class="main-aside">
    <div class="main-aside__title-wrapper">
      <img :src="logoIconURL" alt="Chronika" width="34" height="34">
      <h1 class="main-aside__title">Chronika</h1>
    </div>
    <AsideCalendar />
    <MainMenu />
  </div>
</template>


<style lang="scss">
.main-aside {
  height: 100%;
  background-color: var(--bg-secondary);
  display: block;

  &__title-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 17px 30px 44px 30px;
  }

  &__title {
    font: var(--bold-24);
    margin: 0;
  }
}
</style>
