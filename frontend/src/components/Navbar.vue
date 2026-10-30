<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isAuthenticated = computed(() => authStore.isAuthenticated)
const isMenuOpen = ref(false)
const profileMenu = ref<HTMLElement | null>(null)

const displayName = computed(() => authStore.user?.name || authStore.user?.email || 'Account')
const email = computed(() => authStore.user?.email || '')
const initials = computed(() => {
  const name = authStore.user?.name?.trim()
  if (name) {
    return name
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase()
  }
  return authStore.user?.email?.charAt(0).toUpperCase() || 'U'
})

const navItems = [
  { name: 'Analyzer', path: '/' },
  { name: 'Screener', path: '/screener' },
  { name: 'Watchlist', path: '/watchlist' },
  { name: 'Paper', path: '/paper' },
  { name: 'Glossary', path: '/glossary' }
]

function isActive(path: string): boolean {
  if (path === '/') {
    return route.path === '/' || route.path.startsWith('/analyzer')
  }
  return route.path === path || route.path.startsWith(`${path}/`)
}

function handleLogout(): void {
  isMenuOpen.value = false
  authStore.logout()
  router.push('/login')
}

function closeMenu(): void {
  isMenuOpen.value = false
}

function handleDocumentClick(event: MouseEvent): void {
  if (profileMenu.value && !profileMenu.value.contains(event.target as Node)) {
    closeMenu()
  }
}

onMounted(() => document.addEventListener('click', handleDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', handleDocumentClick))
</script>

<template>
  <nav class="border-b border-slate-200 bg-white">
    <div class="mx-auto max-w-[1700px] px-4 sm:px-6">
      <div class="flex h-14 items-center justify-between gap-3">
        <div class="flex min-w-0 items-center gap-5">
          <router-link to="/" class="flex shrink-0 items-center gap-2">
            <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-xs font-bold text-white">D</span>
            <span class="hidden text-sm font-semibold tracking-tight text-slate-900 sm:block">Dipwork</span>
          </router-link>

          <div v-if="isAuthenticated" class="flex min-w-0 items-center gap-0.5 overflow-x-auto">
            <router-link
              v-for="item in navItems"
              :key="item.path"
              :to="item.path"
              class="whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
              :class="isActive(item.path) ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'"
            >
              {{ item.name }}
            </router-link>
          </div>
        </div>

        <div class="flex shrink-0 items-center gap-2">
          <template v-if="isAuthenticated">
            <div ref="profileMenu" class="relative">
              <button
                type="button"
                aria-label="Open account menu"
                :aria-expanded="isMenuOpen"
                class="flex items-center gap-2 rounded-full p-1.5 text-left transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                @click.stop="isMenuOpen = !isMenuOpen"
                @keydown.esc="closeMenu"
              >
                <span class="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white shadow-sm">
                  {{ initials }}
                </span>
                <span class="hidden max-w-32 truncate text-sm font-medium text-slate-700 md:block">{{ displayName }}</span>
              </button>

              <div
                v-if="isMenuOpen"
                class="absolute right-0 z-20 mt-2 w-60 origin-top-right rounded-xl border border-slate-200 bg-white p-2 shadow-xl"
                role="menu"
              >
                <div class="border-b border-slate-100 px-3 py-2.5">
                  <p class="truncate text-sm font-semibold text-slate-900">{{ displayName }}</p>
                  <p class="mt-0.5 truncate text-xs text-slate-500">{{ email }}</p>
                </div>
                <router-link
                  to="/settings"
                  role="menuitem"
                  class="mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  @click="closeMenu"
                >
                  Profile &amp; settings
                </router-link>
                <button
                  type="button"
                  role="menuitem"
                  class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-rose-50 hover:text-rose-700"
                  @click="handleLogout"
                >
                  Log out
                </button>
              </div>
            </div>
          </template>
          <router-link v-else to="/login" class="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900">
            Sign in
          </router-link>
        </div>
      </div>
    </div>
  </nav>
</template>
