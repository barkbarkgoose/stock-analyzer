import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'
import router from '@/router'
import { clearStoredAuth, REFRESH_KEY, TOKEN_KEY } from '@/utils/authStorage'
import { isTokenExpired } from '@/utils/jwt'

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

let pendingRefresh: Promise<string | null> | null = null

/**
 * Swap the refresh token for a new access token. Concurrent callers share one
 * request. Resolves to null when there is no usable refresh token.
 */
export function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh || isTokenExpired(refresh)) return Promise.resolve(null)
  if (!pendingRefresh) {
    // Plain axios, not `api`, so a failed refresh cannot recurse into the
    // 401 handler below.
    pendingRefresh = axios
      .post<{ access: string }>(`${api.defaults.baseURL ?? ''}/api/v1/auth/refresh/`, { refresh })
      .then((response) => {
        localStorage.setItem(TOKEN_KEY, response.data.access)
        return response.data.access
      })
      .catch(() => null)
      .finally(() => {
        pendingRefresh = null
      })
  }
  return pendingRefresh
}

type RetriableConfig = InternalAxiosRequestConfig & { _retriedAfterRefresh?: boolean }

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status
    const config = error.config as RetriableConfig | undefined
    const requestUrl = config?.url ?? ''
    const isAuthAttempt =
      requestUrl.includes('/auth/login/') || requestUrl.includes('/auth/refresh/')

    // An expired access token: renew it once and replay the request.
    if (status === 401 && !isAuthAttempt && config && !config._retriedAfterRefresh) {
      const access = await refreshAccessToken()
      if (access) {
        config._retriedAfterRefresh = true
        config.headers.Authorization = `Bearer ${access}`
        return api(config)
      }
    }

    // Still 401 (refresh missing, expired or revoked): the session is over.
    // Clear it and route to /login; the router guard re-reads storage, so the
    // in-memory auth state is reconciled on navigation.
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
