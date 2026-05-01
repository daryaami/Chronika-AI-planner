<script setup lang="ts">
import {onMounted, ref} from "vue";

const text = ref<string>('')

const phrases = [
  'думаю над ответом...',
  'анализирую запрос...',
  'ищу лучшее решение...',
  'все еще думаю...',
  'виртуальные нейроны работают…'
]

const showRandomPhrase = () => {
  const randomIndex = Math.floor(Math.random() * phrases.length)
  text.value = phrases[randomIndex]
}

onMounted(() => {
  showRandomPhrase()

  setInterval(showRandomPhrase, 5000)
})
</script>

<template>
  <div class="fetching-message">
    <div class="typing-live">
      <span></span>
      <span></span>
      <span></span>
    </div>

    <span>{{text}}</span>
  </div>
</template>

<style scoped lang="scss">
.fetching-message {
  padding: 6px 12px;
  margin-right: auto;

  display: flex;
  gap: 16px;

  font: var(--light-14);

  color: var(--text-tertiary);
}

.typing-live {
  display: flex;
  gap: 5px;
  justify-content: center;
  align-items: center;
  height: 30px;
}

.typing-live span {
  width: 6px;
  height: 6px;
  background: #becffa; /* можно менять цвет */
  border-radius: 50%;
  animation: live 1.2s infinite ease-in-out;
}

.typing-live span:nth-child(1) {
  animation-delay: 0s;
}
.typing-live span:nth-child(2) {
  animation-delay: 0.2s;
}
.typing-live span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes live {
  0%, 80%, 100% {
    transform: translateY(0) scale(0.6);
    opacity: 0.3;
  }
  40% {
    transform: translateY(-8px) scale(1);
    opacity: 1;
  }
}
</style>
