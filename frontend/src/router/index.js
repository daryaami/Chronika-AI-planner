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
        metaTitle: 'Log in to Chronika'
      },
    },
    {
      path: '/login',
      component: () => import("../views/LoginView.vue"),
      meta: {
        layout: 'login',
        metaTitle: 'Log in to Chronika'
      },
    },
    {
      path: '/planner',
      component: () => import("../views/PlannerView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Planner'
      },
    },
    {
      path: '/tasks',
      component: () => import("../views/TasksView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Tasks'
      },
    },
    {
      path: '/privacy-policy',
      component: () => import("@/views/PrivacyPolicy.vue"),
      meta: {
        layout: 'text',
        metaTitle: 'Privacy Policy'
      },
    },
    {
      path: '/profile',
      component: () => import("../views/ProfileView.vue"),
      meta: {
        layout: 'default',
        metaTitle: 'Profile'
      },
    },
  ],
})

export default router
