<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getScreenRun, startScreen } from '@/services/market'
import { useAnalyzerStore } from '@/stores/analyzer'
import type { ScreenResult, ScreenRun } from '@/types/market'
import {
  formatMoney,
  formatNumber,
  formatRate,
  formatSignedPercent,
  statusTone
} from '@/utils/format'

const store = useAnalyzerStore()
const router = useRouter()
const run = ref<ScreenRun | null>(null)
const loading = ref(false)
const error = ref('')
const limit = ref(25)
const withIntraday = ref(false)
let timer: number | undefined

const results = computed<ScreenResult[]>(() => run.value?.results ?? [])
const progress = computed(() => (run.value ? Math.round(run.value.progress_pct || 0) : 0))
const running = computed(() => run.value?.status === 'running' || run.value?.status === 'pending')

const isSynthetic = computed(() => String(store.provider?.name ?? '') === 'synthetic')

const demoUniverse = [
  'DEMO',
  'SYNTH-UP',
  'SYNTH-FAKE',
  'SYNTH-CLEAN',
  'SYNTH-CHOP',
  'SYNTH-DOWN',
  'SYNTH-QUIET'
]

function stopPolling(): void {
  window.clearTimeout(timer)
}

async function poll(id: number): Promise<void> {
  try {
    const next = await getScreenRun(id)
    run.value = next
    if (next.status === 'running' || next.status === 'pending') {
      timer = window.setTimeout(() => void poll(id), 1500)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not fetch the screen run.'
  }
}

async function scan(symbols?: string[]): Promise<void> {
  if (!store.config) await store.loadConfig()
  if (!store.config) return
  loading.value = true
  error.value = ''
  run.value = null
  stopPolling()
  try {
    const started = await startScreen({
      symbols,
      universe: 'default',
      config: store.config,
      with_intraday: withIntraday.value,
      limit: limit.value
    })
    run.value = started
    if (started.status === 'running' || started.status === 'pending') {
      void poll(started.id)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Screen failed to start.'
  } finally {
    loading.value = false
  }
}

function openSymbol(symbol: string): void {
  void router.push({ name: 'analyzer', params: { symbol } })
}

function trendScore(item: ScreenResult): number {
  return Number(item.uptrend?.trend_score ?? 0)
}

function rangeDays(item: ScreenResult): number {
  return Number(item.volatility?.range_5pct_days_60d ?? 0)
}

function dipsPerMonth(item: ScreenResult): number {
  return Number(item.dips?.per_month ?? 0)
}

onMounted(async () => {
  await store.loadConfig()
})
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <div class="mx-auto max-w-[1500px] px-4 py-6 sm:px-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Universe</div>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">Screener</h1>
          <p class="mt-1 max-w-2xl text-sm text-slate-500">
            Daily-first: trend, liquidity, 5% range days and dip frequency. Intraday confirmation is optional and slower
            because it builds a full profile for each qualifier.
          </p>
        </div>
        <div class="flex flex-wrap items-end gap-2">
          <div>
            <label class="mb-1 block text-[10px] font-medium uppercase tracking-wide text-slate-400" for="screen-limit">Limit</label>
            <input id="screen-limit" v-model.number="limit" class="input h-9 w-20 py-0 text-sm tabular-nums" type="number" min="1" max="500">
          </div>
          <label class="flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600">
            <input v-model="withIntraday" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-blue-600">
            Intraday confirm
          </label>
          <button v-if="isSynthetic" class="btn-secondary h-9 text-xs" type="button" :disabled="loading || running" @click="scan(demoUniverse)">
            Scan demos
          </button>
          <button class="btn-primary h-9 text-xs" type="button" :disabled="loading || running" @click="scan()">
            {{ loading || running ? 'Scanning…' : 'Scan universe' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{{ error }}</div>

      <div v-if="run" class="mt-5 card p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1" :class="statusTone(run.status === 'completed' ? 'qualified' : run.status === 'failed' ? 'reject' : 'watch')">
              {{ run.status }}
            </span>
            <span class="text-xs text-slate-500">
              {{ run.completed }} / {{ run.total }} symbols · {{ run.with_intraday ? 'intraday confirmation' : 'daily only' }}
            </span>
          </div>
          <span class="text-xs tabular-nums text-slate-500">{{ progress }}%</span>
        </div>
        <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div class="h-full rounded-full bg-blue-500 transition-all" :style="{ width: `${progress}%` }" />
        </div>
        <p v-if="run.error" class="mt-2 text-xs text-rose-700">{{ run.error }}</p>
        <p v-if="run.symbols.length" class="mt-2 truncate text-[11px] text-slate-400">{{ run.symbols.join(' · ') }}</p>
      </div>

      <div v-if="results.length" class="mt-5 card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-xs">
            <thead class="border-b border-slate-100 bg-slate-50/70 text-[10px] uppercase tracking-wide text-slate-400">
              <tr>
                <th class="px-4 py-2.5 font-medium">Symbol</th>
                <th class="px-2 py-2.5 font-medium">Status</th>
                <th class="px-2 py-2.5 text-right font-medium">Score</th>
                <th class="px-2 py-2.5 text-right font-medium">Price</th>
                <th class="px-2 py-2.5 text-right font-medium">Trend</th>
                <th class="px-2 py-2.5 text-right font-medium">5% days</th>
                <th class="px-2 py-2.5 text-right font-medium">Dips/mo</th>
                <th class="px-2 py-2.5 font-medium">Readiness</th>
                <th class="px-2 py-2.5 font-medium">Best rule</th>
                <th class="px-2 py-2.5 text-right font-medium">Trades</th>
                <th class="px-2 py-2.5 text-right font-medium">Hit</th>
                <th class="px-2 py-2.5 text-right font-medium">Weekly</th>
                <th class="px-2 py-2.5 text-right font-medium">Fast</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="item in results" :key="item.symbol" class="cursor-pointer transition hover:bg-slate-50" @click="openSymbol(item.symbol)">
                <td class="px-4 py-2.5">
                  <div class="font-semibold text-slate-900">{{ item.symbol }}</div>
                  <div v-if="item.error" class="max-w-xs truncate text-[10px] text-rose-600">{{ item.error }}</div>
                  <div v-else-if="item.profile_error" class="max-w-xs truncate text-[10px] text-amber-600">{{ item.profile_error }}</div>
                </td>
                <td class="px-2 py-2.5">
                  <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1" :class="statusTone(item.status)">{{ item.status }}</span>
                </td>
                <td class="px-2 py-2.5 text-right font-semibold tabular-nums text-slate-900">{{ formatNumber(item.score, 1) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ item.price ? formatMoney(item.price) : '—' }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ formatRate(trendScore(item)) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ rangeDays(item) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ formatNumber(dipsPerMonth(item), 1) }}</td>
                <td class="px-2 py-2.5">
                  <div v-if="item.readiness" class="flex items-center gap-1.5">
                    <span class="rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide" :class="item.readiness.status === 'promising' ? 'bg-emerald-600 text-white' : item.readiness.status === 'fragile' ? 'bg-amber-500 text-white' : item.readiness.status === 'needs_more_data' ? 'bg-sky-600 text-white' : 'bg-rose-600 text-white'">
                      {{ item.readiness.status.replace('_', ' ') }}
                    </span>
                    <span class="tabular-nums text-slate-500">{{ formatNumber(item.readiness.score, 0) }}</span>
                  </div>
                  <span v-else class="text-slate-300">—</span>
                </td>
                <td class="px-2 py-2.5 text-slate-600">{{ item.recommended?.rule_id ?? '—' }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ item.recommended?.trades ?? '—' }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ item.recommended ? formatRate(item.recommended.hit_rate) : '—' }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums" :class="(item.recommended?.weekly_return_pct ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'">
                  {{ item.recommended ? formatSignedPercent(item.recommended.weekly_return_pct) : '—' }}
                </td>
                <td class="px-2 py-2.5 text-right tabular-nums text-slate-600">{{ item.recommended ? formatRate(item.recommended.fast_hit_rate) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="!run" class="mt-8 card p-10 text-center">
        <h2 class="text-lg font-semibold text-slate-900">Find the next research candidate</h2>
        <p class="mx-auto mt-1 max-w-xl text-sm text-slate-500">
          The first scan fetches daily history for the selected universe. Later scans are much faster because bars are cached.
          Use “Scan demos” for an offline run against the synthetic symbols.
        </p>
      </div>
    </div>
  </div>
</template>
