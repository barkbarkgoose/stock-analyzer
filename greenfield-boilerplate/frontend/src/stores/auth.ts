import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  User,
  LoginCredentials,
  RegisterRequest,
  LoginResponse,
  RegisterResponse,
  UserSettings,
  UserSettingsUpdate
} from '@/types/auth'
import { isTokenExpired } from '@/utils/jwt'
import {
  REFRESH_KEY,
  SETTINGS_KEY,
  TOKEN_KEY,
  USER_KEY,
  clearStoredAuth
} from '@/utils/authStorage'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<User | null>(null)
  const userSettings = ref<UserSettings | null>(null)

  const isAuthenticated = computed(() => !!token.value && !isTokenExpired(token.value))

  function clearAuthState(): void {
    token.value = null
    user.value = null
    userSettings.value = null
    clearStoredAuth()
  }

  function loadFromStorage(): void {
    const storedToken = localStorage.getItem(TOKEN_KEY)

    // Treat a missing or expired/malformed access token as logged out so the
    // router guard can redirect to /login instead of leaving the UI broken.
    if (!storedToken || isTokenExpired(storedToken)) {
      clearAuthState()
      return
    }

    const storedUser = localStorage.getItem(USER_KEY)
    const storedSettings = localStorage.getItem(SETTINGS_KEY)

    token.value = storedToken
    if (storedUser) {
      user.value = JSON.parse(storedUser)
    }
    if (storedSettings) {
      userSettings.value = JSON.parse(storedSettings)
    }
  }

  function storeUser(nextUser: User): void {
    user.value = nextUser
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
    if (nextUser.settings) {
      userSettings.value = nextUser.settings
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(nextUser.settings))
    }
  }

  async function fetchUserSettings(): Promise<UserSettings | null> {
    if (!token.value) return null
    try {
      const response = await api.get<UserSettings>('/api/v1/auth/settings/')
      userSettings.value = response.data
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(response.data))
      if (user.value) {
        user.value.settings = response.data
        localStorage.setItem(USER_KEY, JSON.stringify(user.value))
      }
      return response.data
    } catch {
      return null
    }
  }

  async function updateUserSettings(settings: UserSettingsUpdate): Promise<UserSettings> {
    const response = await api.patch<UserSettings>('/api/v1/auth/settings/', settings)
    userSettings.value = response.data
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(response.data))
    if (user.value) {
      user.value.settings = response.data
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    }
    return response.data
  }

  async function saveApiKey(provider: string, apiKey: string): Promise<boolean> {
    if (!token.value || !provider) return false
    try {
      await updateUserSettings({ api_keys: { [provider]: apiKey.trim() } })
      return true
    } catch {
      return false
    }
  }

  async function login(credentials: LoginCredentials): Promise<void> {
    const response = await api.post<LoginResponse>('/api/v1/auth/login/', credentials)
    token.value = response.data.access
    localStorage.setItem(TOKEN_KEY, response.data.access)
    if (response.data.refresh) {
      localStorage.setItem(REFRESH_KEY, response.data.refresh)
    }
    if (response.data.user) {
      storeUser(response.data.user)
    }
  }

  async function register(payload: RegisterRequest): Promise<void> {
    const response = await api.post<RegisterResponse>('/api/v1/auth/register/', payload)
    token.value = response.data.token
    localStorage.setItem(TOKEN_KEY, response.data.token)
    storeUser({
      id: response.data.id,
      email: response.data.email,
      name: response.data.name,
      organization: response.data.organization
    })
  }

  function logout(): void {
    clearAuthState()
  }

  return {
    token,
    user,
    userSettings,
    isAuthenticated,
    loadFromStorage,
    fetchUserSettings,
    updateUserSettings,
    saveApiKey,
    login,
    register,
    logout
  }
})
