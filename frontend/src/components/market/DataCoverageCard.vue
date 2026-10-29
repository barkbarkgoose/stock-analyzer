<script setup lang="ts">
import { computed } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import { formatDate, formatDateTime, formatNumber, formatRate } from '@/utils/format'

const store = useAnalyzerStore()
const profile = computed(() => store.profile)
const data = computed(() => profile.value?.data)
const quality = computed(() => data.value?.quality ?? {})
const warnings = computed(() => {
  const list = [
    ...(store.providerWarnings ?? []),
    ...(profile.value?.warnings ?? [])
  ]
  return [...new Set(list)]
})
const providerName = computed(() => String(store.provider?.name ?? data.value?.daily.source ?? '—'))
const providerNote = computed(() => String(store.provider?.note ?? ''))
</script>

<template>
  <div class="card mt-4 p-4">
    <div class="flex items-start justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">Data coverage</h2>
        <p class="mt-0.5 text-xs text-slate-500">Cached incrementally; ranges are never fetched twice.</p>
      </div>
      <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">{{ providerName }}</span>
    </div>

    <div v-if="data?.daily" class="mt-3 space-y-2 text-xs">
      <div class="rounded-lg border border-slate-200 p-2.5">
        <div class="flex items-center justify-between">
          <span class="font-medium text-slate-700">Daily</span>
          <span class="tabular-nums text-slate-500">{{ (data.daily?.bars ?? 0).toLocaleString() }} bars</span>
        </div>
        <div class="mt-0.5 text-[11px] text-slate-400">
          {{ formatDate(data.daily?.start) }} → {{ formatDate(data.daily?.end) }} · {{ data.daily?.source || '—' }}
        </div>
      </div>
      <div class="rounded-lg border border-slate-200 p-2.5">
        <div class="flex items-center justify-between">
          <span class="font-medium text-slate-700">Intraday {{ data.timeframe }}</span>
          <span class="tabular-nums text-slate-500">{{ (data.intraday?.bars ?? 0).toLocaleString() }} bars</span>
        </div>
        <div class="mt-0.5 text-[11px] text-slate-400">
          {{ formatDate(data.intraday?.start) }} → {{ formatDate(data.intraday?.end) }} · {{ data.intraday?.source || '—' }}
        </div>
        <div v-if="!data.intraday.used" class="mt-1 text-[11px] font-medium text-amber-600">
          Not used — profile is running on daily bars.
        </div>
      </div>
      <div v-if="quality.sessions" class="grid grid-cols-2 gap-2">
        <div class="rounded-lg bg-slate-50 px-2.5 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Sessions</div>
          <div class="text-sm font-semibold tabular-nums text-slate-800">{{ quality.sessions }}</div>
        </div>
        <div class="rounded-lg bg-slate-50 px-2.5 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Bar coverage</div>
          <div class="text-sm font-semibold tabular-nums text-slate-800">{{ formatRate((quality.coverage_pct ?? 0) / 100) }}</div>
        </div>
        <div class="rounded-lg bg-slate-50 px-2.5 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Median bars/session</div>
          <div class="text-sm font-semibold tabular-nums text-slate-800">{{ formatNumber(quality.median_bars_per_session, 0) }}</div>
        </div>
        <div class="rounded-lg bg-slate-50 px-2.5 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Expected</div>
          <div class="text-sm font-semibold tabular-nums text-slate-800">{{ quality.expected_bars_per_session }}</div>
        </div>
      </div>
      <div v-if="profile?.cache" class="rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] text-slate-500">
        {{ profile.cache.cached ? 'Served from cache' : 'Freshly built' }} ·
        built {{ formatDateTime(profile.cache.built_at) }} ·
        data v{{ profile.cache.data_version }}
      </div>
    </div>
    <p v-else class="mt-3 text-xs text-slate-400">{{ providerNote || 'Build a profile to fetch and cache bars.' }}</p>

    <div v-if="warnings.length" class="mt-3 space-y-1.5">
      <div v-for="warning in warnings.slice(0, 8)" :key="warning" class="flex gap-1.5 text-[11px] leading-snug text-amber-800">
        <span class="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
        <span>{{ warning }}</span>
      </div>
    </div>
  </div>
</template>
