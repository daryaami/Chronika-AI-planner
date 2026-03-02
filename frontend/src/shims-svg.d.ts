declare module "*.svg" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

declare module "*.svg?url" {
  const src: string;
  export default src;
}
