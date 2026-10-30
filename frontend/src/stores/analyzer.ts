import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { AxiosError } from 'axios'
import {
  addToWatchlist,
  analyzeSymbol,
  getChart,
  getMarketConfig,
  getWatchlist,
  liveCheck as apiLiveCheck,
  removeFromWatchlist
} from '@/services/market'
import { firstError } from '@/utils/apiErrors'
import type {
  AnalysisConfig,
  ChartBar,
  ConfigSection,
  MarketConfigResponse,
  Profile,
  SignalRead,
  WatchlistItem
} from '@/types/market'

const CONFIG_KEY = 'dipwork.analyzer.config.v3'
const SYMBOL_KEY = 'dipwork.analyzer.symbol.v3'
const OVERRIDES_KEY = 'dipwork.analyzer.symbolOverrides.v1'

// Per-stock tweaks layered over the global study config. Only the target for
// now: it is the knob that most changes what a stock can deliver.
type SymbolOverride = Partial<Pick<AnalysisConfig, 'target_pct'>>

function readOverrides(): Record<string, SymbolOverride> {
  try {
    const raw = localStorage.getItem(OVERRIDES_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : {}
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, SymbolOverride>) : {}
  } catch {
    return {}
  }
}

function errorMessage(error: unknown): string {
  const axiosError = error as AxiosError<unknown>
  const fromBody = firstError(axiosError.response?.data)
  if (fromBody) return fromBody
  if (axiosError.message) return axiosError.message
  return 'Request failed.'
}

export const useAnalyzerStore = defineStore('analyzer', () => {
  const config = ref<AnalysisConfig | null>(null)
  const schema = ref<ConfigSection[]>([])
  const provider = ref<Record<string, unknown>>({})
  const providerWarnings = ref<string[]>([])
  const defaults = ref<AnalysisConfig | null>(null)
  const settings = ref<MarketConfigResponse['settings'] | null>(null)

  const symbol = ref<string>(localStorage.getItem(SYMBOL_KEY) || 'DEMO')
  const profile = ref<Profile | null>(null)
  const liveRead = ref<SignalRead | null>(null)
  const chartBars = ref<ChartBar[]>([])
  const watchlist = ref<WatchlistItem[]>([])
  const symbolOverrides = ref<Record<string, SymbolOverride>>(readOverrides())

  const initialized = ref(false)
  const loading = ref(false)
  const chartLoading = ref(false)
  const liveLoading = ref(false)
  const watchlistLoading = ref(false)
  const error = ref('')

  const isWatched = computed(() =>
    watchlist.value.some((item) => item.security.symbol === symbol.value.toUpperCase())
  )

  const hasProfile = computed(() => Boolean(profile.value))

  const symbolOverride = computed<SymbolOverride>(() => symbolOverrides.value[symbol.value] ?? {})

  // The config actually sent for the current symbol.
  const effectiveConfig = computed<AnalysisConfig | null>(() =>
    config.value ? { ...config.value, ...symbolOverride.value } : null
  )

  function setSymbolTarget(target: number | null): void {
    const next = { ...symbolOverrides.value }
    const current = { ...(next[symbol.value] ?? {}) }
    if (target === null || (config.value && target === config.value.target_pct)) {
      delete current.target_pct
    } else {
      current.target_pct = target
    }
    if (Object.keys(current).length) next[symbol.value] = current
    else delete next[symbol.value]
    symbolOverrides.value = next
    try {
      localStorage.setItem(OVERRIDES_KEY, JSON.stringify(next))
    } catch {
      // Storage can be unavailable (private mode); the override still applies this session.
    }
  }

  function saveConfig(): void {
    if (config.value) {
      localStorage.setItem(CONFIG_KEY, JSON.stringify(config.value))
    }
    localStorage.setItem(SYMBOL_KEY, symbol.value)
  }

  async function loadConfig(): Promise<void> {
    if (initialized.value) return
    try {
      const data = await getMarketConfig()
      defaults.value = data.defaults
      schema.value = data.schema.sections
      provider.value = data.provider
      providerWarnings.value = data.provider_warnings
      settings.value = data.settings
      const stored = localStorage.getItem(CONFIG_KEY)
      let merged: AnalysisConfig = { ...data.defaults }
      if (stored) {
        try {
          merged = { ...merged, ...(JSON.parse(stored) as Partial<AnalysisConfig>) }
        } catch {
          // Ignore malformed local preferences.
        }
      }
      // Only keep keys the backend understands.
      const allowed = new Set(Object.keys(data.defaults))
      const clean: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(merged)) {
        if (allowed.has(key)) clean[key] = value
      }
      config.value = clean as unknown as AnalysisConfig
      initialized.value = true
    } catch (err) {
      error.value = errorMessage(err)
    }
  }

  function updateConfig(patch: Partial<AnalysisConfig>): void {
    if (!config.value) return
    config.value = { ...config.value, ...patch }
    saveConfig()
  }

  function resetConfig(): void {
    if (defaults.value) {
      config.value = { ...defaults.value }
      saveConfig()
    }
  }

  function setSymbol(next: string): void {
    const clean = next.trim().toUpperCase()
    if (!clean) return
    symbol.value = clean
    localStorage.setItem(SYMBOL_KEY, clean)
  }

  async function loadChart(): Promise<void> {
    if (!config.value || !profile.value) return
    chartLoading.value = true
    try {
      const timeframe = profile.value.meta.timeframe || config.value.timeframe
      const limit = timeframe === '1d' ? 1500 : 2200
      chartBars.value = await getChart(symbol.value, timeframe, limit)
    } catch (err) {
      error.value = errorMessage(err)
    } finally {
      chartLoading.value = false
    }
  }

  async function analyze(force = false): Promise<void> {
    if (!config.value) await loadConfig()
    if (!config.value) return
    loading.value = true
    error.value = ''
    try {
      const result = await analyzeSymbol(symbol.value, effectiveConfig.value ?? config.value, force)
      profile.value = result
      liveRead.value = result.signal_read
      saveConfig()
      await loadChart()
    } catch (err) {
      error.value = errorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function refreshLive(): Promise<void> {
    if (!config.value) return
    liveLoading.value = true
    error.value = ''
    try {
      const result = await apiLiveCheck(symbol.value, effectiveConfig.value ?? config.value)
      liveRead.value = result.signal_read
      if (profile.value) {
        profile.value = { ...profile.value, signal_read: result.signal_read }
      }
    } catch (err) {
      error.value = errorMessage(err)
    } finally {
      liveLoading.value = false
    }
  }

  async function loadWatchlist(): Promise<void> {
    watchlistLoading.value = true
    try {
      watchlist.value = await getWatchlist()
    } catch (err) {
      error.value = errorMessage(err)
    } finally {
      watchlistLoading.value = false
    }
  }

  async function toggleWatchlist(): Promise<void> {
    const clean = symbol.value.toUpperCase()
    if (!watchlist.value.length) await loadWatchlist()
    try {
      if (watchlist.value.some((item) => item.security.symbol === clean)) {
        await removeFromWatchlist(clean)
      } else {
        await addToWatchlist(clean)
      }
      await loadWatchlist()
    } catch (err) {
      error.value = errorMessage(err)
    }
  }

  return {
    config,
    schema,
    provider,
    providerWarnings,
    defaults,
    settings,
    symbol,
    profile,
    liveRead,
    chartBars,
    watchlist,
    symbolOverride,
    effectiveConfig,
    setSymbolTarget,
    initialized,
    loading,
    chartLoading,
    liveLoading,
    watchlistLoading,
    error,
    isWatched,
    hasProfile,
    loadConfig,
    updateConfig,
    resetConfig,
    setSymbol,
    analyze,
    loadChart,
    refreshLive,
    loadWatchlist,
    toggleWatchlist,
    saveConfig
  }
})
