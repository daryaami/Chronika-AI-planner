<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import LoginLayout from './layouts/LoginLayout.vue';
import DefaultLayout from './layouts/DefaultLayout.vue';
import TextLayout from './layouts/TextLayout.vue';
import Toast from './components/ui-kit/Toast.vue';

const route = useRoute();

const layoutComponent = computed(() => {
  const layout = route.meta.layout || 'default';
  const layouts = {
    login: LoginLayout,
    default: DefaultLayout,
    text: TextLayout,
  };
  return layouts[layout] || DefaultLayout;
});
</script>

<template>
  <div class="container">
    <component :is="layoutComponent" />
    <Toast />
  </div>
</template>

<style lang="scss">
* {
  box-sizing: border-box;
}

html {
  height: 100%;
}

#app {
  height: 100%;
  width: 100%;
}

body {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
  font-weight: 300;
  font-family: var(--main-font), sans-serif;
  background-color: var(--bg-primary);
}

a {
  color: inherit;
  text-decoration: none;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  border: 0;
  padding: 0;
  white-space: nowrap;
  clip-path: inset(100%);
  clip: rect(0 0 0 0);
  overflow: hidden;
}

.container {
  width: 100%;
  height: 100%;
}
</style>
