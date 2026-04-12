import { ref, nextTick, watch, onMounted } from 'vue';

export function useAutoHeightTextarea(initialValue = '') {
  const textareaRef = ref<HTMLTextAreaElement | null>(null);
  const value = ref(initialValue);

  const resize = () => {
    const el = textareaRef.value;
    if (!el) return;

    // reset высоты
    el.style.height = 'auto';

    const height = el.scrollHeight;

    // защита от 0px при первом рендере
    if (height > 0) {
      el.style.height = `${height}px`;
    }

    el.style.overflow = 'hidden';
  };

  const resizeSafe = async () => {
    await nextTick();
    resize();
  };

  watch(value, () => {
    resize();
  });

  onMounted(() => {
    resizeSafe();
  });

  return {
    textareaRef,
    value,
    resize,
    resizeSafe,
  };
}
