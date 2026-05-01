import { onMounted, onBeforeUnmount, Ref } from "vue";

export function useClickOutside(elRef: Ref<HTMLElement | null>, cb: () => void) {
  function handler(e: MouseEvent) {
    if (elRef.value && !elRef.value.contains(e.target as Node)) {
      cb();
    }
  }
  onMounted(() => document.addEventListener("click", handler));
  onBeforeUnmount(() => document.removeEventListener("click", handler));
}
