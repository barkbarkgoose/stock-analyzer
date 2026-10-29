<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  closePaperTrade,
  getPaperStats,
  getPaperTrades,
  runPaperTick
} from '@/services/market'
import type { PaperStats, PaperTrade } from '@/types/market'
import {
  formatDateTime,
  formatMoney,
  formatRate,
  formatSignedPercent
} from '@/utils/format'

const stats = ref<PaperStats | null>(null)
const trades = ref<PaperTrade[]>([])
const filter = ref<'all' | 'open' | 'closed'>('all')
const loading = ref(false)
const busy = ref<number | 'tick' | null>(null)
const message = ref('')
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [nextStats, nextTrades] = await Promise.all([
      getPaperStats(),
      getPaperTrades(filter.value === 'all' ? undefined : filter.value)
    ])
    stats.value = nextStats
    trades.value = nextTrades
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load paper trades.'
  } finally {
    loading.value = false
  }
}

async function setFilter(next: 'all' | 'open' | 'closed'): Promise<void> {
  filter.value = next
  await load()
}

async function tick(): Promise<void> {
  busy.value = 'tick'
  message.value = ''
  error.value = ''
  try {
    const result = await runPaperTick()
    message.value = `Tick complete: ${result.actions.length} actions, ${result.open_trades} open trades.`
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Paper tick failed.'
  } finally {
    busy.value = null
  }
}

async function closeTrade(trade: PaperTrade): Promise<void> {
  busy.value = trade.id
  try {
    await closePaperTrade(trade.id)
    message.value = `Closed ${trade.symbol} manually.`
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not close trade.'
  } finally {
    busy.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <div class="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Simulation</div>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">Paper trades</h1>
          <p class="mt-1 text-sm text-slate-500">Simulated fills only. No broker connection, no real orders.</p>
        </div>
        <button class="btn-primary h-9 text-xs" type="button" :disabled="busy === 'tick'" @click="tick">
          {{ busy === 'tick' ? 'Ticking…' : 'Run paper tick' }}
        </button>
      </div>

      <div v-if="error" class="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{{ error }}</div>
      <div v-if="message" class="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{{ message }}</div>

      <div v-if="stats" class="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div class="card p-4">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Closed</div>
          <div class="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{{ stats.closed_trades }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Open</div>
          <div class="mt-1 text-2xl font-semibold tabular-nums text-blue-700">{{ stats.open_trades }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Win rate</div>
          <div class="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{{ formatRate(stats.win_rate) }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Avg return</div>
          <div class="mt-1 text-2xl font-semibold tabular-nums" :class="stats.avg_return_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatSignedPercent(stats.avg_return_pct) }}</div>
        </div>
        <div class="card p-4">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Total P&amp;L</div>
          <div class="mt-1 text-2xl font-semibold tabular-nums" :class="stats.total_pnl >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatMoney(stats.total_pnl) }}</div>
        </div>
      </div>

      <div class="mt-5 flex items-center gap-2">
        <div class="flex rounded-lg border border-slate-200 bg-white p-0.5 text-[11px]">
          <button v-for="option in (['all', 'open', 'closed'] as const)" :key="option" type="button" class="rounded-md px-3 py-1 font-medium capitalize transition" :class="filter === option ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'" @click="setFilter(option)">
            {{ option }}
          </button>
        </div>
        <button class="btn-secondary h-8 text-xs" type="button" :disabled="loading" @click="load">Refresh</button>
      </div>

      <div class="mt-3 card overflow-hidden">
        <div v-if="!trades.length" class="p-10 text-center text-sm text-slate-400">
          No paper trades yet. Add symbols to the watchlist, then run a paper tick.
        </div>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full text-left text-xs">
            <thead class="border-b border-slate-100 bg-slate-50/70 text-[10px] uppercase tracking-wide text-slate-400">
              <tr>
                <th class="px-4 py-2.5 font-medium">Symbol</th>
                <th class="px-2 py-2.5 font-medium">Status</th>
                <th class="px-2 py-2.5 font-medium">Rule</th>
                <th class="px-2 py-2.5 font-medium">Entry</th>
                <th class="px-2 py-2.5 text-right font-medium">Entry px</th>
                <th class="px-2 py-2.5 text-right font-medium">Target</th>
                <th class="px-2 py-2.5 text-right font-medium">Stop</th>
                <th class="px-2 py-2.5 font-medium">Exit</th>
                <th class="px-2 py-2.5 text-right font-medium">Return</th>
                <th class="px-2 py-2.5 text-right font-medium">P&amp;L</th>
                <th class="px-2 py-2.5 text-right font-medium">P(win)</th>
                <th class="px-2 py-2.5 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="trade in trades" :key="trade.id" class="hover:bg-slate-50">
                <td class="px-4 py-2.5 font-semibold text-slate-900">{{ trade.symbol }}</td>
                <td class="px-2 py-2.5">
                  <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1" :class="trade.status === 'open' ? 'bg-blue-50 text-blue-700 ring-blue-200' : 'bg-slate-100 text-slate-600 ring-slate-200'">{{ trade.status }}</span>
                </td>
                <td class="px-2 py-2.5 text-slate-500">{{ trade.rule_id }}</td>
                <td class="px-2 py-2.5 text-slate-500">{{ formatDateTime(trade.entry_ts) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-700">{{ formatMoney(trade.entry_price) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-emerald-700">{{ formatMoney(trade.target_price) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-rose-700">{{ formatMoney(trade.stop_price) }}</td>
                <td class="px-2 py-2.5 text-slate-500">
                  <div>{{ trade.exit_ts ? formatDateTime(trade.exit_ts) : '—' }}</div>
                  <div v-if="trade.exit_reason" class="text-[10px] text-slate-400">{{ trade.exit_reason }}</div>
                </td>
                <td class="px-2 py-2.5 text-right font-semibold tabular-nums" :class="(trade.return_pct ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'">
                  {{ formatSignedPercent(trade.return_pct) }}
                </td>
                <td class="px-2 py-2.5 text-right tabular-nums" :class="(trade.pnl ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatMoney(trade.pnl) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-500">{{ formatRate(trade.probability) }}</td>
                <td class="px-2 py-2.5 text-right">
                  <button v-if="trade.status === 'open'" class="text-[11px] font-medium text-rose-600 hover:text-rose-800" type="button" :disabled="busy === trade.id" @click="closeTrade(trade)">
                    {{ busy === trade.id ? 'Closing…' : 'Close' }}
                  </button>
                  <span v-else class="text-[11px] text-slate-300">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="stats && Object.keys(stats.by_rule).length" class="mt-5 card p-4">
        <h2 class="text-sm font-semibold text-slate-900">By rule</h2>
        <div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="(bucket, rule) in stats.by_rule" :key="rule" class="rounded-lg bg-slate-50 p-3 text-xs">
            <div class="font-medium text-slate-800">{{ rule }}</div>
            <div class="mt-1 flex justify-between text-slate-500">
              <span>{{ bucket.trades }} trades</span>
              <span>{{ formatRate(bucket.win_rate) }} win</span>
              <span :class="bucket.avg_return_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatSignedPercent(bucket.avg_return_pct) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
