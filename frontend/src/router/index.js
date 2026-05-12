import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: () => import("../views/AuthCheck.vue"),
      meta: {
        layout: 'login',
      }
    },
    {
      path: '/auth/google/callback',
      component: () => import("../views/Callback.vue"),
      meta: {
        layout: 'login',
        metaTitle: 'Вход в Chronika'
      },
    },
    {
      path: '/login',
      component: () => import("../views/LoginView.vue"),
      meta: {
        layout: 'login',
        metaTitle: 'Вход в Chronika'
      },
    },
    {
      path: '/planner',
      component: () => import("../views/PlannerView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Календарь'
      },
    },
    {
      path: '/tasks',
      component: () => import("../views/TasksView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Задачи'
      },
    },
    {
      path: '/privacy-policy',
      component: () => import("@/views/PrivacyPolicy.vue"),
      meta: {
        layout: 'text',
        metaTitle: 'Политика конфиденциальности'
      },
    },
    {
      path: '/profile',
      component: () => import("../views/ProfileView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Профиль'
      },
    },
    {
      path: '/api-tester',
      component: () => import("../views/ApiTesterView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Тестер API'
      },
    },
  ],
})

export default router
