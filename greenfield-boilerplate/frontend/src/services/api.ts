import axios from 'axios'
import type { AxiosError } from 'axios'
import router from '@/router'
import { clearStoredAuth, TOKEN_KEY } from '@/utils/authStorage'

const api = axios.create({
  // Same-origin by default: the Vite dev proxy forwards /api to the backend, so the
  // app works from any host (localhost, LAN, Tailscale). Set VITE_API_URL to bypass.
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status
    const requestUrl = error.config?.url ?? ''
    const isAuthAttempt =
      requestUrl.includes('/auth/login/') || requestUrl.includes('/auth/register/')

    // A 401 on a normal request means the access token expired (or was revoked).
    // Clear the stored session and route to /login; the router guard re-reads
    // storage, so the in-memory auth state is reconciled on navigation.
    if (status === 401 && !isAuthAttempt) {
      clearStoredAuth()

      if (router.currentRoute.value.name !== 'login') {
        router.push({
          name: 'login',
          query: { redirect: router.currentRoute.value.fullPath }
        })
      }
    }

    return Promise.reject(error)
  }
)

export default api
