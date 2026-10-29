import api from '@/services/api'
import type {
  AnalysisConfig,
  ChartBar,
  CoverageResponse,
  LiveCheckResponse,
  MarketConfigResponse,
  PaperStats,
  PaperTrade,
  Profile,
  ScreenRun,
  SearchResult,
  WatchlistItem
} from '@/types/market'

export async function getMarketConfig(): Promise<MarketConfigResponse> {
  const response = await api.get<MarketConfigResponse>('/api/v1/market/config')
  return response.data
}

export async function searchSymbols(query: string): Promise<SearchResult[]> {
  const response = await api.get<{ results: SearchResult[] }>('/api/v1/market/symbols', {
    params: { q: query }
  })
  return response.data.results
}

export async function analyzeSymbol(
  symbol: string,
  config: AnalysisConfig,
  force = false
): Promise<Profile> {
  const response = await api.post<Profile>('/api/v1/market/analyze', {
    symbol,
    config,
    force
  })
  return response.data
}

export async function getProfile(symbol: string, configHash?: string): Promise<Profile> {
  const response = await api.get<Profile>(`/api/v1/market/profile/${encodeURIComponent(symbol)}`, {
    params: configHash ? { config_hash: configHash } : undefined
  })
  return response.data
}

export async function ingestBars(
  symbol: string,
  timeframe: string,
  options: { days?: number; force?: boolean; start?: string; end?: string } = {}
): Promise<Record<string, unknown>> {
  const response = await api.post('/api/v1/market/ingest', {
    symbol,
    timeframe,
    ...options
  })
  return response.data
}

export async function getCoverage(
  symbol: string,
  timeframe: string
): Promise<CoverageResponse> {
  const response = await api.get<CoverageResponse>(
    `/api/v1/market/coverage/${encodeURIComponent(symbol)}`,
    { params: { timeframe } }
  )
  return response.data
}

export async function getChart(
  symbol: string,
  timeframe: string,
  limit = 1500
): Promise<ChartBar[]> {
  const response = await api.get<{ bars: ChartBar[] }>(
    `/api/v1/market/chart/${encodeURIComponent(symbol)}`,
    { params: { timeframe, limit } }
  )
  return response.data.bars
}

export async function liveCheck(
  symbol: string,
  config: AnalysisConfig
): Promise<LiveCheckResponse> {
  const response = await api.post<LiveCheckResponse>('/api/v1/market/live-check', {
    symbol,
    config
  })
  return response.data
}

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const response = await api.get<{ items: WatchlistItem[] }>('/api/v1/market/watchlist')
  return response.data.items
}

export async function addToWatchlist(
  symbol: string,
  note = ''
): Promise<WatchlistItem> {
  const response = await api.post<WatchlistItem>('/api/v1/market/watchlist', {
    symbol,
    note
  })
  return response.data
}

export async function removeFromWatchlist(symbol: string): Promise<void> {
  await api.delete(`/api/v1/market/watchlist/${encodeURIComponent(symbol)}`)
}

export async function startScreen(payload: {
  symbols?: string[]
  universe?: string
  config: AnalysisConfig
  with_intraday: boolean
  limit?: number
  sync?: boolean
}): Promise<ScreenRun> {
  const response = await api.post<ScreenRun>('/api/v1/market/screen', payload)
  return response.data
}

export async function getScreenRun(id: number): Promise<ScreenRun> {
  const response = await api.get<ScreenRun>(`/api/v1/market/screen/${id}`)
  return response.data
}

export async function runPaperTick(
  symbols?: string[],
  notional?: number
): Promise<{ actions: Array<Record<string, unknown>>; open_trades: number; checked_at: string }> {
  const response = await api.post('/api/v1/market/paper/tick', {
    symbols,
    notional
  })
  return response.data
}

export async function getPaperTrades(status?: 'open' | 'closed'): Promise<PaperTrade[]> {
  const response = await api.get<{ trades: PaperTrade[] }>('/api/v1/market/paper/trades', {
    params: status ? { status } : undefined
  })
  return response.data.trades
}

export async function getPaperStats(): Promise<PaperStats> {
  const response = await api.get<PaperStats>('/api/v1/market/paper/stats')
  return response.data
}

export async function closePaperTrade(id: number, price?: number): Promise<PaperTrade> {
  const response = await api.post<PaperTrade>(`/api/v1/market/paper/trades/${id}/close`, {
    price
  })
  return response.data
}

export async function getUniverse(): Promise<string[]> {
  const response = await api.get<{ symbols: string[] }>('/api/v1/market/universe')
  return response.data.symbols
}
