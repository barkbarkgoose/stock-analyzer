<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SymbolSearch from '@/components/market/SymbolSearch.vue'
import ConfigPanel from '@/components/market/ConfigPanel.vue'
import DataCoverageCard from '@/components/market/DataCoverageCard.vue'
import VerdictCard from '@/components/market/VerdictCard.vue'
import ReadinessCard from '@/components/market/ReadinessCard.vue'
import SignalReadCard from '@/components/market/SignalReadCard.vue'
import PriceChart from '@/components/market/PriceChart.vue'
import RuleTable from '@/components/market/RuleTable.vue'
import AttemptAnalysisCard from '@/components/market/AttemptAnalysisCard.vue'
import FakeReboundStudyCard from '@/components/market/FakeReboundStudyCard.vue'
import ModelPanel from '@/components/market/ModelPanel.vue'
import TradeTable from '@/components/market/TradeTable.vue'
import EquityChart from '@/components/market/EquityChart.vue'
import StrategyCard from '@/components/market/StrategyCard.vue'
import BlindReplayCard from '@/components/market/BlindReplayCard.vue'
import BounceProfileCard from '@/components/market/BounceProfileCard.vue'
import DipHistoryCard from '@/components/market/DipHistoryCard.vue'
import Term from '@/components/Term.vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import { useScreenerStore } from '@/stores/screener'
import { formatDateTime } from '@/utils/format'
import type { Timeframe } from '@/types/market'

const store = useAnalyzerStore()
const screener = useScreenerStore()
const route = useRoute()
const router = useRouter()

const profile = computed(() => store.profile)

// The simulation and the true history are kept apart on purpose: one is what
// you would have gotten trading blind, the other is what the stock did.
type View = 'blind' | 'history' | 'now'
const view = ref<View>('blind')
const chartSource = ref<'blind' | 'hindsight'>('blind')
const views: Array<{ id: View; label: string; hint: string }> = [
  { id: 'blind', label: 'Blind simulation', hint: 'what you would have gotten' },
  { id: 'history', label: 'What actually happened', hint: 'hindsight research' },
  { id: 'now', label: 'Right now', hint: 'latest bar in detail' }
]

function selectView(next: View): void {
  view.value = next
  if (next === 'blind') chartSource.value = 'blind'
  if (next === 'history') chartSource.value = 'hindsight'
}

const chartTrades = computed(() =>
  (chartSource.value === 'blind' ? profile.value?.blind.trades : profile.value?.trades) ?? []
)
const chartBands = computed(() => profile.value?.watch_bands?.[chartSource.value] ?? [])
const timeframe = computed<Timeframe>(() => (store.config?.timeframe ?? '5m') as Timeframe)
const timeframes: Timeframe[] = ['1m', '5m', '15m', '30m', '1h', '1d']
const examples = computed(() =>
  String(store.provider?.name ?? '') === 'synthetic'
    ? ['DEMO', 'SYNTH-FAKE', 'SYNTH-CLEAN', 'SYNTH-DOWN', 'SYNTH-QUIET']
    : ['AAPL', 'TSLA', 'NVDA', 'AMD', 'META']
)

function handleSelect(symbol: string): void {
  if (route.params.symbol === symbol) {
    void store.analyze(false)
  } else {
    void router.push({ name: 'analyzer', params: { symbol } })
  }
}

function changeTimeframe(event: Event): void {
  const value = (event.target as HTMLSelectElement).value as Timeframe
  store.updateConfig({ timeframe: value })
  void store.analyze(false)
}

function backToScreener(): void {
  if (screener.runId === null) return
  void router.push({ name: 'screener', params: { runId: String(screener.runId) } })
}

watch(
  () => route.params.symbol,
  (value) => {
    if (typeof value === 'string' && value) {
      store.setSymbol(value)
      if (store.config) void store.analyze(false)
    }
  }
)

onMounted(async () => {
  await store.loadConfig()
  const routeSymbol = route.params.symbol
  if (typeof routeSymbol === 'string' && routeSymbol) {
    store.setSymbol(routeSymbol)
    await store.analyze(false)
  } else if (store.config && !store.profile) {
    await store.analyze(false)
  }
  await store.loadWatchlist()
})
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div class="mx-auto flex max-w-[1700px] flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center">
        <div class="flex min-w-0 flex-1 items-center gap-3">
          <div class="hidden shrink-0 lg:block">
            <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Dipwork</div>
            <div class="text-sm font-semibold text-slate-900">Rebound research</div>
          </div>
          <div class="min-w-0 flex-1 max-w-2xl">
            <SymbolSearch @select="handleSelect" />
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button v-if="screener.runId !== null" class="btn-secondary h-9 text-xs" type="button" @click="backToScreener">
            ← Screener results
          </button>
          <label class="text-[11px] font-medium uppercase tracking-wide text-slate-400" for="timeframe">TF</label>
          <select id="timeframe" class="input h-9 w-24 py-0 text-xs font-medium" :value="timeframe" @change="changeTimeframe">
            <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
          </select>
          <button class="btn-secondary h-9 text-xs" type="button" :disabled="store.loading" @click="store.analyze(true)">
            {{ store.loading ? 'Refreshing…' : 'Refresh data' }}
          </button>
          <button class="btn-secondary h-9 text-xs" type="button" :disabled="store.liveLoading" @click="store.refreshLive()">
            {{ store.liveLoading ? 'Checking…' : 'Live check' }}
          </button>
          <button class="btn-secondary h-9 text-xs" type="button" @click="store.toggleWatchlist()">
            {{ store.isWatched ? '★ Watching' : '☆ Watch' }}
          </button>
        </div>
      </div>
    </header>

    <div v-if="store.error" class="mx-auto mt-4 max-w-[1700px] px-4 sm:px-6">
      <div class="flex items-start justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
        <span>{{ store.error }}</span>
        <button class="text-xs font-semibold uppercase tracking-wide" type="button" @click="store.error = ''">Dismiss</button>
      </div>
    </div>

    <div class="mx-auto max-w-[1700px] px-4 py-5 sm:px-6">
      <div v-if="!profile && store.loading" class="grid gap-5 lg:grid-cols-12">
        <div class="lg:col-span-3">
          <div class="card h-80 animate-pulse bg-slate-100" />
        </div>
        <div class="space-y-5 lg:col-span-9">
          <div class="card h-52 animate-pulse bg-slate-100" />
          <div class="card h-64 animate-pulse bg-slate-100" />
          <div class="card h-96 animate-pulse bg-slate-100" />
        </div>
      </div>

      <div v-else-if="!profile" class="grid gap-6 py-12 lg:grid-cols-12">
        <div class="lg:col-span-3">
          <ConfigPanel />
        </div>
        <div class="lg:col-span-9">
          <div class="card p-8">
            <div class="max-w-2xl">
              <span class="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-blue-700 ring-1 ring-blue-200">Signal lab</span>
              <h1 class="mt-3 text-3xl font-semibold tracking-tight text-slate-900">Wait for the dip. Confirm the turn. Take 1%.</h1>
              <p class="mt-3 text-sm leading-relaxed text-slate-600">
                Build a profile for any ticker to get a plain-English strategy for it: when to watch, when to buy, when to sell —
                and what would have happened if you had followed it blind, without knowing the future.
              </p>
              <div class="mt-5 flex flex-wrap gap-2">
                <button v-for="example in examples" :key="example" type="button" class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-blue-300 hover:text-blue-700" @click="handleSelect(example)">
                  {{ example }}
                </button>
              </div>
              <div class="mt-6 grid gap-3 sm:grid-cols-3">
                <div class="rounded-xl bg-slate-50 p-3">
                  <div class="text-xs font-semibold text-slate-800">1. Dip context</div>
                  <p class="mt-1 text-[11px] leading-relaxed text-slate-500">A >= 5% drawdown inside a longer uptrend, tracked as one multi-leg episode.</p>
                </div>
                <div class="rounded-xl bg-slate-50 p-3">
                  <div class="text-xs font-semibold text-slate-800">2. Confirmation</div>
                  <p class="mt-1 text-[11px] leading-relaxed text-slate-500">Higher low, EMA/VWAP reclaim, volume and structure break — not the first green bar.</p>
                </div>
                <div class="rounded-xl bg-slate-50 p-3">
                  <div class="text-xs font-semibold text-slate-800">3. Triple barrier</div>
                  <p class="mt-1 text-[11px] leading-relaxed text-slate-500">+1% target vs stop vs max hold, with pessimistic fills and costs.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="grid gap-5 lg:grid-cols-12">
        <aside class="order-2 min-w-0 space-y-4 lg:order-1 lg:col-span-3">
          <ConfigPanel />
          <DataCoverageCard />
          <div class="card p-4 text-[11px] leading-relaxed text-slate-500">
            <div class="font-semibold text-slate-700">Reading the numbers</div>
            <p class="mt-1">Hit rate is target-before-stop. Net EV includes costs. Weekly is compounded sequential trades, not a forecast. The blind simulation is the honest estimate; hindsight numbers flatter.</p>
            <router-link class="mt-2 inline-block font-medium text-blue-600 hover:text-blue-700" to="/glossary">Full glossary →</router-link>
            <p class="mt-2 text-slate-400">Built {{ profile.cache?.built_at ? formatDateTime(profile.cache.built_at) : formatDateTime(profile.meta.generated_at) }} · engine {{ profile.meta.engine_version }}</p>
          </div>
        </aside>

        <main class="order-1 min-w-0 space-y-5 lg:order-2 lg:col-span-9">
          <StrategyCard />
          <ReadinessCard />
          <PriceChart
            v-model:source="chartSource"
            :bars="store.chartBars"
            :trades="chartTrades"
            :bands="chartBands"
            :timeframe="profile.meta.timeframe"
          />

          <div class="flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm" role="tablist">
            <button
              v-for="item in views"
              :key="item.id"
              type="button"
              role="tab"
              :aria-selected="view === item.id"
              class="flex-1 rounded-lg px-3 py-2 text-left transition"
              :class="view === item.id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-50'"
              @click="selectView(item.id)"
            >
              <div class="text-sm font-semibold">{{ item.label }}</div>
              <div class="text-[11px]" :class="view === item.id ? 'text-slate-300' : 'text-slate-400'">{{ item.hint }}</div>
            </button>
          </div>

          <template v-if="view === 'blind'">
            <BlindReplayCard />
            <TradeTable source="blind" />
            <EquityChart source="blind" />
          </template>

          <template v-else-if="view === 'history'">
            <div class="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-3 text-xs leading-relaxed text-slate-500">
              Everything below looks at the whole history at once. It is the right place to learn how this stock behaves,
              but rule results here are <Term k="hindsight">hindsight</Term> — the best rule was picked after seeing the outcome.
            </div>
            <BounceProfileCard />
            <DipHistoryCard />
            <VerdictCard />
            <RuleTable />
            <div class="grid gap-5 xl:grid-cols-2">
              <FakeReboundStudyCard />
              <AttemptAnalysisCard />
            </div>
            <ModelPanel />
            <TradeTable source="hindsight" />
            <EquityChart source="hindsight" />
          </template>

          <template v-else>
            <SignalReadCard />
          </template>

          <div class="pb-10 text-center text-[11px] text-slate-400">{{ profile.meta.disclaimer }}</div>
        </main>
      </div>
    </div>
  </div>
</template>
