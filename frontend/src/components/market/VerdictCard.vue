<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import { formatCompactMoney, formatNumber, formatPercent, formatRate, reasonTone, statusTone } from '@/utils/format'

const store = useAnalyzerStore()
const showAllReasons = ref(false)

const profile = computed(() => store.profile)
const qualification = computed(() => profile.value?.qualification)
const daily = computed(() => profile.value?.daily)
const reasons = computed(() => qualification.value?.reasons ?? [])
const visibleReasons = computed(() =>
  showAllReasons.value ? reasons.value : reasons.value.slice(0, 6)
)
const status = computed(() => qualification.value?.status ?? 'reject')
const score = computed(() => qualification.value?.score ?? 0)
const circumference = 2 * Math.PI * 30
const dashOffset = computed(() => circumference * (1 - Math.min(100, Math.max(0, score.value)) / 100))
const scoreColor = computed(() =>
  status.value === 'qualified' ? '#059669' : status.value === 'watch' ? '#d97706' : '#e11d48'
)

function num(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

const uptrend = computed(() => daily.value?.uptrend ?? {})
const volatility = computed(() => daily.value?.volatility ?? {})
const dips = computed(() => daily.value?.dips)
</script>

<template>
  <div v-if="profile && qualification && daily" class="card overflow-hidden">
    <div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ring-1" :class="statusTone(status)">
            {{ status }}
          </span>
          <span class="text-xs text-slate-500">
            {{ profile.meta.mode }} · {{ profile.meta.bars_analyzed.toLocaleString() }} bars ·
            {{ profile.meta.episodes }} dip episodes
          </span>
          <span v-if="profile.data.fallback" class="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
            daily fallback
          </span>
        </div>
        <h1 class="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{{ profile.meta.symbol }}</h1>
        <p class="mt-1 max-w-2xl text-sm leading-relaxed text-slate-500">
          {{ profile.daily.price ? `Last $${formatNumber(profile.daily.price)}. ` : '' }}
          {{ profile.episode_summary?.interpretation ?? '' }}
        </p>
      </div>

      <div class="flex shrink-0 items-center gap-4">
        <div class="relative h-20 w-20">
          <svg viewBox="0 0 72 72" class="h-20 w-20 -rotate-90">
            <circle cx="36" cy="36" r="30" fill="none" stroke="#e2e8f0" stroke-width="7" />
            <circle
              cx="36"
              cy="36"
              r="30"
              fill="none"
              :stroke="scoreColor"
              stroke-width="7"
              stroke-linecap="round"
              :stroke-dasharray="circumference"
              :stroke-dashoffset="dashOffset"
            />
          </svg>
          <div class="absolute inset-0 flex flex-col items-center justify-center">
            <span class="text-lg font-bold tabular-nums text-slate-900">{{ formatNumber(score, 0) }}</span>
            <span class="text-[9px] font-medium uppercase tracking-wide text-slate-400">score</span>
          </div>
        </div>
        <div class="text-xs text-slate-500">
          <div>Trend <span class="font-semibold text-slate-800">{{ formatRate(num(uptrend.trend_score)) }}</span></div>
          <div>6m <span class="font-semibold text-slate-800">{{ formatPercent(num(uptrend.return_6m_pct)) }}</span></div>
          <div>ATR <span class="font-semibold text-slate-800">{{ formatPercent(num(volatility.atr14_pct)) }}</span></div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-px border-y border-slate-100 bg-slate-100 sm:grid-cols-4">
      <div class="bg-white px-4 py-3">
        <div class="text-[11px] font-medium uppercase tracking-wide text-slate-400">5% range days</div>
        <div class="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
          {{ formatNumber(num(volatility.range_5pct_days_60d), 0) }}
          <span class="text-xs font-normal text-slate-400">/ 60d</span>
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-[11px] font-medium uppercase tracking-wide text-slate-400">Close dips</div>
        <div class="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
          {{ formatNumber(num(dips?.count), 0) }}
          <span class="text-xs font-normal text-slate-400">/ month {{ formatNumber(num(dips?.per_month), 1) }}</span>
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-[11px] font-medium uppercase tracking-wide text-slate-400">Fake rebound rate</div>
        <div class="mt-0.5 text-lg font-semibold tabular-nums text-amber-700">
          {{ formatRate(num(dips?.fake_rebound_rate)) }}
        </div>
      </div>
      <div class="bg-white px-4 py-3">
        <div class="text-[11px] font-medium uppercase tracking-wide text-slate-400">Liquidity</div>
        <div class="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
          {{ formatCompactMoney(num(volatility.avg_dollar_volume_60d)) }}
          <span class="text-xs font-normal text-slate-400">/day</span>
        </div>
      </div>
    </div>

    <div class="p-5">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-slate-900">Qualification checks</h2>
        <button v-if="reasons.length > 6" class="text-xs font-medium text-blue-600 hover:text-blue-700" type="button" @click="showAllReasons = !showAllReasons">
          {{ showAllReasons ? 'Show fewer' : `Show all ${reasons.length}` }}
        </button>
      </div>
      <div class="grid gap-1.5 sm:grid-cols-2">
        <div
          v-for="reason in visibleReasons"
          :key="reason.code"
          class="flex items-start justify-between gap-3 rounded-lg px-2.5 py-1.5 ring-1"
          :class="reasonTone(reason.passed)"
        >
          <div class="min-w-0">
            <div class="truncate text-xs font-medium">{{ reason.label }}</div>
            <div class="truncate text-[11px] opacity-70">{{ reason.target }}</div>
          </div>
          <div class="shrink-0 text-right text-xs font-semibold tabular-nums">{{ reason.value }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
