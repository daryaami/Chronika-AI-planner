<script setup>
import MainAside from "../components/blocks/main-aside/MainAside.vue";
</script>

<template>
  <div class="page-wrapper">
    <MainAside />
    <div class="page-wrapper__main">
      <RouterView  />
    </div>
  </div>
</template>

<style lang="scss">
.page-wrapper {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: min-content 1fr;

  &__main {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }
}
</style>
