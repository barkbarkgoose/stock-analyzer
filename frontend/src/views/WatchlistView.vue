<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  addToWatchlist,
  getWatchlist,
  liveCheck,
  removeFromWatchlist,
  runPaperTick
} from '@/services/market'
import { useAnalyzerStore } from '@/stores/analyzer'
import type { SignalRead, WatchlistItem } from '@/types/market'
import {
  formatDateTime,
  formatMoney,
  formatRate,
  formatSignedPercent,
  riskTone,
  statusTone
} from '@/utils/format'

const store = useAnalyzerStore()
const router = useRouter()
const items = ref<WatchlistItem[]>([])
const newSymbol = ref('')
const loading = ref(false)
const busy = ref<string | null>(null)
const checkingAll = ref(false)
const message = ref('')
const error = ref('')

const openTrades = computed(() => items.value.filter((item) => item.open_trade).length)

function readOf(item: WatchlistItem): SignalRead | null {
  const read = item.last_signal as SignalRead
  return read && read.state && read.state !== 'no_data' ? read : null
}

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await getWatchlist()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load watchlist.'
  } finally {
    loading.value = false
  }
}

async function add(): Promise<void> {
  const symbol = newSymbol.value.trim().toUpperCase()
  if (!symbol) return
  try {
    await addToWatchlist(symbol)
    newSymbol.value = ''
    await load()
    await store.loadWatchlist()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not add symbol.'
  }
}

async function remove(symbol: string): Promise<void> {
  try {
    await removeFromWatchlist(symbol)
    await load()
    await store.loadWatchlist()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not remove symbol.'
  }
}

async function check(item: WatchlistItem): Promise<void> {
  if (!store.config) await store.loadConfig()
  if (!store.config) return
  busy.value = item.security.symbol
  try {
    const result = await liveCheck(item.security.symbol, store.config)
    const target = items.value.find((row) => row.id === item.id)
    if (target) {
      target.last_signal = result.signal_read
      target.last_price = result.signal_read.price ?? target.last_price
      target.last_checked_at = new Date().toISOString()
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Live check failed.'
  } finally {
    busy.value = null
  }
}

async function checkAll(): Promise<void> {
  checkingAll.value = true
  try {
    for (const item of items.value) {
      await check(item)
    }
  } finally {
    checkingAll.value = false
  }
}

async function tick(): Promise<void> {
  busy.value = 'tick'
  message.value = ''
  try {
    const result = await runPaperTick()
    message.value = `Paper tick: ${result.actions.length} actions, ${result.open_trades} open trades.`
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Paper tick failed.'
  } finally {
    busy.value = null
  }
}

function analyze(symbol: string): void {
  void router.push({ name: 'analyzer', params: { symbol } })
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <div class="mx-auto max-w-[1300px] px-4 py-6 sm:px-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Monitor</div>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">Watchlist</h1>
          <p class="mt-1 text-sm text-slate-500">{{ items.length }} symbols · {{ openTrades }} open paper trades</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input v-model="newSymbol" class="input h-9 w-36 py-0 text-sm uppercase" placeholder="Add ticker" @keydown.enter.prevent="add">
          <button class="btn-secondary h-9 text-xs" type="button" @click="add">Add</button>
          <button class="btn-secondary h-9 text-xs" type="button" :disabled="busy !== null || checkingAll || !items.length" @click="checkAll">
            {{ checkingAll ? 'Checking…' : 'Check all' }}
          </button>
          <button class="btn-primary h-9 text-xs" type="button" :disabled="busy !== null || !items.length" @click="tick">
            {{ busy === 'tick' ? 'Ticking…' : 'Paper tick' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{{ error }}</div>
      <div v-if="message" class="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{{ message }}</div>

      <div v-if="!items.length && !loading" class="mt-8 card p-10 text-center">
        <h2 class="text-lg font-semibold text-slate-900">Nothing on the watchlist yet</h2>
        <p class="mt-1 text-sm text-slate-500">Add the demo ticker to see the workflow.</p>
        <button class="btn-primary mt-4" type="button" @click="newSymbol = 'DEMO'; add()">Add DEMO</button>
      </div>

      <div v-else class="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="item in items" :key="item.id" class="card p-4">
          <div class="flex items-start justify-between gap-2">
            <div>
              <button class="text-lg font-semibold tracking-tight text-slate-900 hover:text-blue-700" type="button" @click="analyze(item.security.symbol)">
                {{ item.security.symbol }}
              </button>
              <div class="text-[11px] text-slate-400">
                {{ item.last_price ? formatMoney(item.last_price) : 'no quote' }} ·
                {{ item.last_checked_at ? formatDateTime(item.last_checked_at) : 'not checked' }}
              </div>
            </div>
            <span v-if="readOf(item)" class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1" :class="statusTone(readOf(item)?.state)">
              {{ readOf(item)?.state.replace('_', ' ') }}
            </span>
            <span v-else class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">idle</span>
          </div>

          <div v-if="readOf(item)" class="mt-3 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="text-slate-500">Fake-rebound risk</span>
              <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ring-1" :class="riskTone(readOf(item)?.fake_rebound_risk.level)">
                {{ readOf(item)?.fake_rebound_risk.level }}
              </span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-slate-500">P(target before stop)</span>
              <span class="font-semibold tabular-nums text-slate-800">{{ formatRate(readOf(item)?.probability) }}</span>
            </div>
            <div v-if="readOf(item)?.waiting_for.length" class="rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] leading-snug text-slate-500">
              Waiting for {{ readOf(item)?.waiting_for.slice(0, 2).join('; ') }}
            </div>
          </div>

          <div v-if="item.open_trade" class="mt-3 rounded-lg border border-blue-100 bg-blue-50/60 p-2.5 text-[11px]">
            <div class="flex items-center justify-between font-medium text-blue-900">
              <span>Open paper trade</span>
              <span class="tabular-nums">{{ formatSignedPercent(item.open_trade.return_pct) }}</span>
            </div>
            <div class="mt-1 flex justify-between text-blue-700">
              <span>Entry {{ formatMoney(item.open_trade.entry_price) }}</span>
              <span>Target {{ formatMoney(item.open_trade.target_price) }}</span>
              <span>Stop {{ formatMoney(item.open_trade.stop_price) }}</span>
            </div>
          </div>

          <div class="mt-3 flex items-center justify-between gap-2">
            <div class="flex gap-1.5">
              <button class="btn-ghost text-[11px]" type="button" @click="analyze(item.security.symbol)">Analyze</button>
              <button class="btn-ghost text-[11px]" type="button" :disabled="busy === item.security.symbol || checkingAll" @click="check(item)">
                {{ busy === item.security.symbol ? 'Checking…' : 'Check' }}
              </button>
            </div>
            <button class="text-[11px] font-medium text-rose-500 hover:text-rose-700" type="button" @click="remove(item.security.symbol)">Remove</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
