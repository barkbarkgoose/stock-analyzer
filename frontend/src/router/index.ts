import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { refreshAccessToken } from '@/services/api'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/AnalyzerView.vue')
  },
  {
    path: '/analyzer/:symbol?',
    name: 'analyzer',
    component: () => import('@/views/AnalyzerView.vue')
  },
  {
    path: '/screener/:runId?',
    name: 'screener',
    component: () => import('@/views/ScreenerView.vue')
  },
  {
    path: '/watchlist',
    name: 'watchlist',
    component: () => import('@/views/WatchlistView.vue')
  },
  {
    path: '/paper',
    name: 'paper',
    component: () => import('@/views/PaperView.vue')
  },
  {
    path: '/glossary',
    name: 'glossary',
    component: () => import('@/views/GlossaryView.vue')
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresGuest: true, public: true }
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue')
  },
  {
    path: '/dashboard',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// Every page except /login needs a session. An expired access token is
// renewed from the refresh token before giving up and showing /login.
router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  authStore.loadFromStorage()

  if (!authStore.isAuthenticated && !to.meta.public) {
    if (await refreshAccessToken()) authStore.loadFromStorage()
  }

  if (!to.meta.public && !authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresGuest && authStore.isAuthenticated) {
    return { name: 'home' }
  }
  return true
})

export default router
