<script setup>
import GoogleBtn from '../components/blocks/buttons/google-btn.vue'
import ChronikaLogo from '../components/icons/app-logo.vue'
import {BASE_API_URL} from "../config.ts";

const loginWithGoogle = async () => {
  try {
    const response = await fetch(`${BASE_API_URL}/auth/google/redirect/${window.location.search === '?consent=true'? '?consent=true' : ''}`, { credentials: 'include' });
    // Для запроса разрешений добавить параметр /?consent=true

    if (!response.ok) {
      console.error(response)
    }

    const data = await response.json();
    window.location.href = data.auth_url;
  } catch (error) {
    console.error('Error initiating Google login:', error);
  }
}
</script>

<template>
    <section class="login-page">
      <ChronikaLogo
        class="login-page__logo"
      />
      <h1 class="login-page__title">Log in to Chronika</h1>

      <GoogleBtn class="login-page__button"
        @click="loginWithGoogle"
        text="Continue with Google"
      />

      <p class="login-page__privacy-text">By using Chronika, you agree to our Terms of Service and Privacy Policy.</p>
    </section>
</template>

<style lang="scss">
@use '@/assets/scss/mixins/mixins.scss' as *;

.login-page {
  display: flex;
  align-items: center;
  flex-direction: column;

  &__logo {
    display: block;
    width: 70px;
    height: 70px;
    margin-bottom: 22px;
  }

  &__title {
    line-height: 100%;
    margin-top: 0;
    margin-bottom: 88px;
    font-weight: 600;
    font-size: 50px;
    text-align: center;
    color: var(--text-secondary);
  }

  &__button {
    margin-bottom: 143px;
  }

  &__privacy-text {
    font: var(--light-20);
    margin: 0;
    color: var(--text-secondary-muted);
  }
}
</style>
