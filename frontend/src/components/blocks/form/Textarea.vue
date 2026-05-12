<script setup>
const text = defineModel()
</script>

<template>
  <div class="input">
    <textarea class="input__input" rows="1"
      v-model="text"
    ></textarea>
    <span class="input__label">Добавить заметку</span>
  </div>
</template>
