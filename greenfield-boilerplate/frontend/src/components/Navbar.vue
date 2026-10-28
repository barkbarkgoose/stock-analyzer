<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
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
  { name: 'Dashboard', path: '/dashboard' },
]

function handleLogout() {
  isMenuOpen.value = false
  authStore.logout()
  router.push('/login')
}

function closeMenu() {
  isMenuOpen.value = false
}

function handleDocumentClick(event: MouseEvent) {
  if (profileMenu.value && !profileMenu.value.contains(event.target as Node)) {
    closeMenu()
  }
}

onMounted(() => document.addEventListener('click', handleDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', handleDocumentClick))
</script>

<template>
  <nav v-if="isAuthenticated" class="bg-white shadow-sm border-b border-gray-200">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex h-16 items-center justify-between">
        <!-- Logo -->
        <router-link to="/dashboard" class="flex-shrink-0">
          <span class="text-xl font-bold text-primary">App</span>
        </router-link>

        <!-- Nav Links -->
        <div class="hidden sm:flex sm:items-center sm:space-x-1">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            :class="route.path === item.path 
              ? 'bg-primary text-white' 
              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'"
          >
            {{ item.name }}
          </router-link>
        </div>

        <!-- Profile menu -->
        <div ref="profileMenu" class="relative">
          <button
            type="button"
            aria-label="Open account menu"
            :aria-expanded="isMenuOpen"
            class="flex items-center gap-2 rounded-full p-1.5 text-left transition-colors hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary/40"
            @click.stop="isMenuOpen = !isMenuOpen"
            @keydown.esc="closeMenu"
          >
            <span class="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-white shadow-sm">
              {{ initials }}
            </span>
            <span class="hidden max-w-32 text-sm font-medium text-gray-700 sm:block truncate">
              {{ displayName }}
            </span>
            <svg class="hidden h-4 w-4 text-gray-400 sm:block" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.51a.75.75 0 01-1.08 0l-4.25-4.51a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
            </svg>
          </button>

          <div
            v-if="isMenuOpen"
            class="absolute right-0 z-20 mt-2 w-64 origin-top-right rounded-2xl border border-gray-200 bg-white p-2 shadow-xl ring-1 ring-black/5"
            role="menu"
          >
            <div class="border-b border-gray-100 px-3 py-3">
              <p class="truncate text-sm font-semibold text-gray-900">{{ displayName }}</p>
              <p class="mt-0.5 truncate text-xs text-gray-500">{{ email }}</p>
            </div>
            <router-link
              to="/settings"
              role="menuitem"
              class="mt-2 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 hover:text-gray-900"
              @click="closeMenu"
            >
              <svg class="h-5 w-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.5 20.25a7.5 7.5 0 0115 0" />
              </svg>
              Profile & settings
            </router-link>
            <button
              type="button"
              role="menuitem"
              class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-red-50 hover:text-red-700"
              @click="handleLogout"
            >
              <svg class="h-5 w-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6A2.25 2.25 0 005.25 5.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 12h9m0 0l-3-3m3 3l-3 3" />
              </svg>
              Log out
            </button>
          </div>
        </div>
      </div>
    </div>
  </nav>
</template>
