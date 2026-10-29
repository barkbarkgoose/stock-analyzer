<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ApiKeyStatus } from '@/types/auth'
import { useAuthStore } from '@/stores/auth'

interface Provider {
  id: string
  name: string
  description: string
}

const authStore = useAuthStore()

const providers: Provider[] = [
  { id: 'openai', name: 'OpenAI', description: 'GPT models and other OpenAI services.' },
  { id: 'anthropic', name: 'Anthropic', description: 'Claude models from Anthropic.' },
  { id: 'google', name: 'Google Gemini', description: 'Gemini models through Google AI.' },
  { id: 'ollama', name: 'Ollama', description: 'Use a hosted or local Ollama model.' }
]

const preferences = reactive({
  default_view: 'all',
  default_ai_provider: 'heuristic'
})
const apiKeyDrafts = reactive<Record<string, string>>({})
const savingProvider = ref<string | null>(null)
const savingPreferences = ref(false)
const isLoading = ref(true)
const loadError = ref('')
const preferencesMessage = ref('')
const preferencesError = ref('')
const providerMessages = reactive<Record<string, string>>({})
const providerErrors = reactive<Record<string, string>>({})

const user = computed(() => authStore.user)
const initials = computed(() => {
  const name = user.value?.name?.trim()
  if (name) {
    return name
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase()
  }
  return user.value?.email?.charAt(0).toUpperCase() || 'U'
})

function getApiKeyStatus(provider: string): ApiKeyStatus | undefined {
  return authStore.userSettings?.api_keys_status?.[provider]
}

async function loadSettings() {
  isLoading.value = true
  loadError.value = ''
  const settings = await authStore.fetchUserSettings()
  if (!settings) {
    loadError.value = 'We could not load your settings. Please try again.'
  } else {
    preferences.default_view = settings.default_view || 'all'
    preferences.default_ai_provider = settings.default_ai_provider || 'heuristic'
  }
  isLoading.value = false
}

async function savePreferences() {
  savingPreferences.value = true
  preferencesMessage.value = ''
  preferencesError.value = ''
  try {
    await authStore.updateUserSettings({ ...preferences })
    preferencesMessage.value = 'Preferences saved.'
  } catch {
    preferencesError.value = 'Could not save your preferences. Please try again.'
  } finally {
    savingPreferences.value = false
  }
}

async function saveProviderKey(provider: string) {
  const value = apiKeyDrafts[provider]?.trim() || ''
  if (!value) return

  savingProvider.value = provider
  providerMessages[provider] = ''
  providerErrors[provider] = ''
  const saved = await authStore.saveApiKey(provider, value)
  if (saved) {
    apiKeyDrafts[provider] = ''
    providerMessages[provider] = 'API key saved securely.'
  } else {
    providerErrors[provider] = 'Could not save this API key. Please try again.'
  }
  savingProvider.value = null
}

async function clearProviderKey(provider: string) {
  savingProvider.value = provider
  providerMessages[provider] = ''
  providerErrors[provider] = ''
  const cleared = await authStore.saveApiKey(provider, '')
  if (cleared) {
    providerMessages[provider] = 'API key removed.'
  } else {
    providerErrors[provider] = 'Could not remove this API key. Please try again.'
  }
  savingProvider.value = null
}

onMounted(loadSettings)
</script>

<template>
  <div class="min-h-[calc(100vh-4rem)] bg-slate-50 px-4 py-10 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-5xl">
      <header class="mb-10 max-w-2xl">
        <p class="text-sm font-semibold uppercase tracking-[0.18em] text-primary">Account</p>
        <h1 class="mt-3 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">Profile & settings</h1>
        <p class="mt-3 text-base leading-7 text-slate-600">
          Manage your profile, defaults, and the integrations available to your account.
        </p>
      </header>

      <div v-if="isLoading" class="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div class="flex items-center gap-3 text-sm text-slate-500">
          <span class="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-primary"></span>
          Loading your settings...
        </div>
      </div>

      <div v-else-if="loadError" class="rounded-3xl border border-red-200 bg-red-50 p-6">
        <p class="font-medium text-red-900">{{ loadError }}</p>
        <button type="button" class="mt-4 rounded-xl bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800" @click="loadSettings">
          Try again
        </button>
      </div>

      <div v-else class="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <section class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div class="flex items-center gap-4">
            <span class="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-primary text-xl font-bold text-white shadow-sm">
              {{ initials }}
            </span>
            <div class="min-w-0">
              <h2 class="truncate text-xl font-semibold text-slate-950">{{ user?.name || 'Your profile' }}</h2>
              <p class="truncate text-sm text-slate-500">{{ user?.email }}</p>
            </div>
          </div>
          <div class="mt-8 border-t border-slate-100 pt-6">
            <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Organization</p>
            <p class="mt-2 text-sm font-medium text-slate-800">{{ user?.organization?.name || 'Personal account' }}</p>
            <p class="mt-1 text-sm leading-6 text-slate-500">
              Profile details are managed by your account administrator.
            </p>
          </div>
        </section>

        <section class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div>
            <p class="text-sm font-semibold uppercase tracking-wider text-primary">Preferences</p>
            <h2 class="mt-2 text-xl font-semibold text-slate-950">Make the app feel like yours</h2>
          </div>
          <form class="mt-6 space-y-5" @submit.prevent="savePreferences">
            <div class="grid gap-5 sm:grid-cols-2">
              <label class="block">
                <span class="text-sm font-semibold text-slate-800">Default view</span>
                <select v-model="preferences.default_view" class="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/10">
                  <option value="all">All items</option>
                  <option value="recent">Recent items</option>
                </select>
                <span class="mt-1.5 block text-xs text-slate-500">Choose where you land when opening the app.</span>
              </label>
              <label class="block">
                <span class="text-sm font-semibold text-slate-800">Default AI provider</span>
                <select v-model="preferences.default_ai_provider" class="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/10">
                  <option value="heuristic">Built-in provider</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="google">Google Gemini</option>
                  <option value="ollama">Ollama</option>
                </select>
                <span class="mt-1.5 block text-xs text-slate-500">Used when an AI-powered feature needs a provider.</span>
              </label>
            </div>
            <div class="flex flex-wrap items-center gap-3 pt-1">
              <button type="submit" :disabled="savingPreferences" class="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                {{ savingPreferences ? 'Saving...' : 'Save preferences' }}
              </button>
              <p v-if="preferencesMessage" class="text-sm font-medium text-emerald-700">{{ preferencesMessage }}</p>
              <p v-if="preferencesError" class="text-sm font-medium text-red-700">{{ preferencesError }}</p>
            </div>
          </form>
        </section>

        <section class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:col-span-2 sm:p-8">
          <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p class="text-sm font-semibold uppercase tracking-wider text-primary">Integrations</p>
              <h2 class="mt-2 text-xl font-semibold text-slate-950">API keys</h2>
              <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                Keys are encrypted before they are stored. We only show a short preview after a key has been saved.
              </p>
            </div>
            <span class="inline-flex w-fit items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
              <span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
              Stored securely
            </span>
          </div>

          <div class="mt-7 grid gap-4 md:grid-cols-2">
            <article v-for="provider in providers" :key="provider.id" class="rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h3 class="font-semibold text-slate-900">{{ provider.name }}</h3>
                  <p class="mt-1 text-xs leading-5 text-slate-500">{{ provider.description }}</p>
                </div>
                <span
                  class="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                  :class="getApiKeyStatus(provider.id)?.is_configured ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'"
                >
                  {{ getApiKeyStatus(provider.id)?.is_configured ? 'Configured' : 'Not set' }}
                </span>
              </div>

              <p v-if="getApiKeyStatus(provider.id)?.is_configured" class="mt-4 font-mono text-xs text-slate-500">
                {{ getApiKeyStatus(provider.id)?.preview }}
              </p>
              <form class="mt-4" @submit.prevent="saveProviderKey(provider.id)">
                <label :for="`${provider.id}-key`" class="sr-only">{{ provider.name }} API key</label>
                <div class="flex flex-col gap-2 sm:flex-row">
                  <input
                    :id="`${provider.id}-key`"
                    v-model="apiKeyDrafts[provider.id]"
                    type="password"
                    autocomplete="new-password"
                    :placeholder="getApiKeyStatus(provider.id)?.is_configured ? 'Enter a new key to replace it' : 'Paste API key'"
                    class="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-primary focus:ring-4 focus:ring-primary/10"
                  />
                  <button type="submit" :disabled="savingProvider === provider.id || !apiKeyDrafts[provider.id]?.trim()" class="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50">
                    {{ savingProvider === provider.id ? 'Saving...' : 'Save key' }}
                  </button>
                </div>
              </form>
              <div class="mt-3 flex min-h-5 items-center justify-between gap-3">
                <p v-if="providerMessages[provider.id]" class="text-xs font-medium text-emerald-700">{{ providerMessages[provider.id] }}</p>
                <p v-else-if="providerErrors[provider.id]" class="text-xs font-medium text-red-700">{{ providerErrors[provider.id] }}</p>
                <span v-else></span>
                <button v-if="getApiKeyStatus(provider.id)?.is_configured" type="button" :disabled="savingProvider === provider.id" class="text-xs font-semibold text-slate-500 hover:text-red-700 disabled:opacity-50" @click="clearProviderKey(provider.id)">
                  Remove key
                </button>
              </div>
            </article>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
