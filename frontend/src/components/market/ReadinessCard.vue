<script setup lang="ts">
import { computed } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import { formatNumber } from '@/utils/format'

const store = useAnalyzerStore()
const readiness = computed(() => store.profile?.automation_readiness)
const isSynthetic = computed(() => store.profile?.data.daily.source === 'synthetic')

const tone = computed(() => {
  switch (readiness.value?.status) {
    case 'promising':
      return 'border-emerald-200 bg-gradient-to-br from-emerald-50 to-white'
    case 'fragile':
      return 'border-amber-200 bg-gradient-to-br from-amber-50 to-white'
    case 'needs_more_data':
      return 'border-sky-200 bg-gradient-to-br from-sky-50 to-white'
    default:
      return 'border-rose-200 bg-gradient-to-br from-rose-50 to-white'
  }
})

const badgeTone = computed(() => {
  switch (readiness.value?.status) {
    case 'promising':
      return 'bg-emerald-600 text-white'
    case 'fragile':
      return 'bg-amber-500 text-white'
    case 'needs_more_data':
      return 'bg-sky-600 text-white'
    default:
      return 'bg-rose-600 text-white'
  }
})

const label = computed(() => {
  switch (readiness.value?.status) {
    case 'promising':
      return 'Promising'
    case 'fragile':
      return 'Fragile edge'
    case 'needs_more_data':
      return 'Needs more data'
    case 'no_edge':
      return 'No demonstrated edge'
    default:
      return 'Not qualified'
  }
})

function bulletTone(toneValue: string): string {
  if (toneValue === 'good') return 'bg-emerald-50 text-emerald-800 ring-emerald-100'
  if (toneValue === 'bad') return 'bg-rose-50 text-rose-800 ring-rose-100'
  if (toneValue === 'warn') return 'bg-amber-50 text-amber-800 ring-amber-100'
  return 'bg-white text-slate-700 ring-slate-200'
}
</script>

<template>
  <div v-if="readiness" class="rounded-xl border p-5 shadow-sm" :class="tone">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="max-w-3xl">
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide" :class="badgeTone">
            {{ label }}
          </span>
          <span class="text-[11px] font-medium uppercase tracking-wide text-slate-500">Automation readiness</span>
          <span v-if="isSynthetic" class="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700 ring-1 ring-violet-200">
            synthetic demo data
          </span>
        </div>
        <p class="mt-2 text-sm leading-relaxed text-slate-700">{{ readiness.summary }}</p>
      </div>
      <div class="shrink-0 text-right">
        <div class="text-3xl font-semibold tabular-nums text-slate-900">{{ formatNumber(readiness.score, 0) }}</div>
        <div class="text-[10px] uppercase tracking-wide text-slate-400">readiness / 100</div>
        <div class="mt-2 h-1.5 w-32 overflow-hidden rounded-full bg-white/70 ring-1 ring-slate-200">
          <div
            class="h-full rounded-full"
            :class="readiness.status === 'promising' ? 'bg-emerald-500' : readiness.status === 'fragile' ? 'bg-amber-400' : readiness.status === 'needs_more_data' ? 'bg-sky-500' : 'bg-rose-500'"
            :style="{ width: `${Math.max(2, readiness.score)}%` }"
          />
        </div>
      </div>
    </div>
    <div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      <div v-for="bullet in readiness.bullets" :key="bullet.label" class="rounded-lg px-3 py-2 text-xs ring-1" :class="bulletTone(bullet.tone)">
        <div class="text-[10px] font-medium uppercase tracking-wide opacity-60">{{ bullet.label }}</div>
        <div class="mt-0.5 font-semibold tabular-nums">{{ bullet.value }}</div>
      </div>
    </div>
    <p class="mt-3 text-[11px] text-slate-500">
      Readiness requires a qualified trend, enough sequential trades, a positive walk-forward estimate, and a hit-rate interval above 50%. It is still a historical estimate.
    </p>
  </div>
</template>
