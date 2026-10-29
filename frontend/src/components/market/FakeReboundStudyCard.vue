<script setup lang="ts">
import { computed } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import { formatNumber, formatRate, formatSignedPercent } from '@/utils/format'
import type { BucketStat } from '@/types/market'

const store = useAnalyzerStore()
const profile = computed(() => store.profile)
const study = computed(() => profile.value?.fake_rebound_study ?? null)
const summary = computed(() => profile.value?.episode_summary)

const delta = computed(() => {
  if (!study.value) return 0
  return study.value.confirmed_first_attempt.hit_rate - study.value.baseline_first_attempt.hit_rate
})

function row(label: string, stat: BucketStat | null, tone: 'baseline' | 'confirmed'): {
  label: string
  stat: BucketStat | null
  tone: 'baseline' | 'confirmed'
} {
  return { label, stat, tone }
}

const rows = computed(() => {
  if (!study.value) return []
  return [
    row('Buy every dip — 1st attempt', study.value.baseline_first_attempt, 'baseline'),
    row(
      study.value.confirmed_label ?? 'Confirmed signal — 1st attempt',
      study.value.confirmed_first_attempt,
      'confirmed'
    ),
    row('Buy every dip — after failed bounce', study.value.baseline_after_failed_bounce, 'baseline'),
    row('Confirmed — after failed bounce', study.value.confirmed_after_failed_bounce, 'confirmed')
  ]
})
</script>

<template>
  <div class="card p-5">
    <div class="flex items-start justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">Fake-rebound study</h2>
        <p class="mt-0.5 text-xs text-slate-500">The exact pattern you want to avoid: dip → 1-2% bounce → new low.</p>
      </div>
      <div class="text-right">
        <div class="text-[10px] uppercase tracking-wide text-slate-400">1st-attempt lift</div>
        <div class="text-lg font-semibold tabular-nums" :class="delta >= 0 ? 'text-emerald-700' : 'text-rose-700'">
          {{ delta >= 0 ? '+' : '' }}{{ formatRate(delta) }}
        </div>
      </div>
    </div>

    <div v-if="summary" class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div class="rounded-lg bg-slate-50 px-3 py-2">
        <div class="text-[10px] uppercase tracking-wide text-slate-400">Episodes</div>
        <div class="text-sm font-semibold tabular-nums text-slate-900">{{ summary.count }}</div>
      </div>
      <div class="rounded-lg bg-slate-50 px-3 py-2">
        <div class="text-[10px] uppercase tracking-wide text-slate-400">Multi-leg</div>
        <div class="text-sm font-semibold tabular-nums text-amber-700">{{ formatRate(summary.multi_leg_rate) }}</div>
      </div>
      <div class="rounded-lg bg-slate-50 px-3 py-2">
        <div class="text-[10px] uppercase tracking-wide text-slate-400">Failed ≥1%</div>
        <div class="text-sm font-semibold tabular-nums text-rose-700">{{ formatRate(summary.fake_rebound_rate) }}</div>
      </div>
      <div class="rounded-lg bg-slate-50 px-3 py-2">
        <div class="text-[10px] uppercase tracking-wide text-slate-400">Per month</div>
        <div class="text-sm font-semibold tabular-nums text-slate-900">{{ formatNumber(summary.per_month, 1) }}</div>
      </div>
    </div>

    <div v-if="rows.length" class="mt-4 overflow-hidden rounded-lg border border-slate-200">
      <table class="min-w-full text-left text-xs">
        <thead class="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
          <tr>
            <th class="px-3 py-2 font-medium">Scenario</th>
            <th class="px-2 py-2 text-right font-medium">Signals</th>
            <th class="px-2 py-2 text-right font-medium">Hit rate</th>
            <th class="px-2 py-2 text-right font-medium">Net EV</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="entry in rows" :key="entry.label" :class="entry.tone === 'confirmed' ? 'bg-emerald-50/40' : ''">
            <td class="px-3 py-2 font-medium" :class="entry.tone === 'confirmed' ? 'text-emerald-900' : 'text-slate-700'">{{ entry.label }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ entry.stat?.signals ?? '—' }}</td>
            <td class="px-2 py-2 text-right font-semibold tabular-nums" :class="(entry.stat?.hit_rate ?? 0) >= 0.5 ? 'text-emerald-700' : 'text-rose-700'">
              {{ entry.stat ? formatRate(entry.stat.hit_rate) : '—' }}
            </td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">
              {{ entry.stat ? formatSignedPercent(entry.stat.net_ev_pct) : '—' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="study?.interpretation" class="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900 ring-1 ring-amber-100">
      {{ study.interpretation }}
    </p>
    <p v-else class="mt-4 text-sm text-slate-400">No fake-rebound comparison available.</p>
  </div>
</template>
