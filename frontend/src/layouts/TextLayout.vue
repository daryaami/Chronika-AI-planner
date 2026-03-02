<script setup lang="ts">
import logoIconURL from "@/assets/img/logo.svg?url";
import {useRoute} from "vue-router";

const route = useRoute()
</script>

<template>
  <div class="text-page-wrapper">
    <header class="text-header">
      <div class="text-header__logo">
        <img :src="logoIconURL" alt="Chronika" width="34" height="34">
        <span>Chronika</span>
      </div>

      <span class="text-header__title">{{ route.meta.metaTitle }}</span>
    </header>
    <RouterView  />
  </div>
</template>

<style scoped lang="scss">
.text-page-wrapper {
  width: 100%;
  max-width: 808px;
  margin: 0 auto;

  padding: 0 15px;
}

.text-header {
  padding: 18px 0;

  display: flex;
  align-items: center;

  margin-bottom: 32px;

  gap: 13px;

  &__logo {
    display: flex;
    align-items: center;
    gap: 8px;

    font: var(--bold-24)
  }

  &__title {
    margin: 0;
    font: var(--light-20);
    color: var(--text-primary-muted);
  }
}
</style>
