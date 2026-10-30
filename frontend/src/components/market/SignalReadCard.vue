<script setup lang="ts">
import { computed } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import {
  formatMoney,
  formatNumber,
  formatPercent,
  formatRate,
  formatTime,
  riskTone,
  statusTone
} from '@/utils/format'

const store = useAnalyzerStore()
const read = computed(() => store.liveRead ?? store.profile?.signal_read ?? null)
const fastLabel = computed(() => store.profile?.meta.fast_horizon_label ?? 'fast horizon')
const levels = computed(() => read.value?.levels)
const firedRules = computed(() => read.value?.fired_rules ?? [])
const risk = computed(
  () => read.value?.fake_rebound_risk ?? { level: 'n/a', detail: 'No risk read available.' }
)
const confirmations = computed(() => firedRules.value.filter((rule) => !rule.baseline))
const baseline = computed(() => firedRules.value.find((rule) => rule.baseline))
</script>

<template>
  <div v-if="read" class="card overflow-hidden">
    <div class="flex flex-col gap-4 border-b border-slate-100 p-5 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ring-1" :class="statusTone(read.state)">
            {{ read.state.replace('_', ' ') }}
          </span>
          <span v-if="read.ts" class="text-xs text-slate-400">latest {{ formatTime(read.ts) }} ET</span>
          <span v-if="read.recommended_fire" class="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700 ring-1 ring-blue-200">
            recommended rule firing
          </span>
          <span v-if="store.profile?.recommended?.use_model_filter" class="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700 ring-1 ring-indigo-200">
            model filter ≥ {{ formatNumber(store.profile?.recommended?.threshold, 2) }}
          </span>
        </div>
        <p class="mt-2 text-sm text-slate-600">{{ read.detail }}</p>
      </div>
    </div>

    <div class="grid gap-5 p-5 lg:grid-cols-[1.15fr_0.85fr]">
      <div>
        <div v-if="read.candidate || read.state === 'signal'">
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div class="rounded-lg bg-slate-50 px-3 py-2">
              <div class="text-[10px] font-medium uppercase tracking-wide text-slate-400">Entry ~</div>
              <div class="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">{{ formatMoney(levels?.entry_estimate) }}</div>
            </div>
            <div class="rounded-lg bg-emerald-50 px-3 py-2">
              <div class="text-[10px] font-medium uppercase tracking-wide text-emerald-600">Target</div>
              <div class="mt-0.5 text-sm font-semibold tabular-nums text-emerald-800">{{ formatMoney(levels?.target) }}</div>
            </div>
            <div class="rounded-lg bg-rose-50 px-3 py-2">
              <div class="text-[10px] font-medium uppercase tracking-wide text-rose-600">Stop</div>
              <div class="mt-0.5 text-sm font-semibold tabular-nums text-rose-800">{{ formatMoney(levels?.stop) }}</div>
            </div>
            <div class="rounded-lg bg-slate-50 px-3 py-2">
              <div class="text-[10px] font-medium uppercase tracking-wide text-slate-400">R:R</div>
              <div class="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
                {{ formatNumber((levels?.target_pct ?? 0) / Math.max(0.01, levels?.stop_pct ?? 1), 2) }}
              </div>
            </div>
          </div>

          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-slate-200 p-3">
              <div class="flex items-center justify-between text-xs">
                <span class="font-medium text-slate-600">P(+{{ formatPercent(levels?.target_pct ?? 1, 2) }} before stop) · if entered now</span>
                <span class="font-semibold tabular-nums text-slate-900">{{ formatRate(read.probability) }}</span>
              </div>
              <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div class="h-full rounded-full bg-blue-500" :style="{ width: `${Math.round((read.probability ?? 0) * 100)}%` }" />
              </div>
              <div class="mt-1 text-[11px] text-slate-400">full holding window</div>
            </div>
            <div class="rounded-lg border border-slate-200 p-3">
              <div class="flex items-center justify-between text-xs">
                <span class="font-medium text-slate-600">P(hit within {{ fastLabel }}) · if entered now</span>
                <span class="font-semibold tabular-nums text-slate-900">{{ formatRate(read.probability_fast) }}</span>
              </div>
              <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div class="h-full rounded-full bg-emerald-500" :style="{ width: `${Math.round((read.probability_fast ?? 0) * 100)}%` }" />
              </div>
              <div class="mt-1 text-[11px] text-slate-400">time-to-target estimate</div>
            </div>
          </div>
        </div>
        <div v-else class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-xs text-slate-500">
          No active setup. Entry, target and stop levels appear once a >= dip episode is in progress and a confirmation is being evaluated.
        </div>

        <div class="mt-4">
          <div class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">All rules firing now</div>
          <div v-if="confirmations.length" class="flex flex-wrap gap-1.5">
            <span v-for="rule in confirmations" :key="rule.id" class="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
              {{ rule.name }}
            </span>
          </div>
          <div v-else class="text-xs text-slate-500">
            None yet{{ baseline ? ' — the dip baseline is active, but no confirmation has triggered.' : '.' }}
          </div>
        </div>
      </div>

      <div class="space-y-3">
        <div class="rounded-lg border p-3" :class="riskTone(risk.level)">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-semibold uppercase tracking-wide">Fake-rebound risk</span>
            <span class="rounded-full bg-white/60 px-2 py-0.5 text-[11px] font-semibold capitalize">{{ risk.level }}</span>
          </div>
          <p class="mt-1 text-xs leading-relaxed opacity-80">{{ risk.detail }}</p>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Dip depth</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ formatPercent(read.episode_depth_pct) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Off the low / cutoff</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ formatPercent(read.off_low_pct ?? read.runup_from_low_pct) }} / {{ formatPercent(read.cutoff_pct) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Attempt</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">#{{ read.attempt_number ?? 1 }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Failed bounces</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ read.failed_bounces_1pct ?? 0 }} ≥1%</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Bars since low</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ read.bars_since_episode_low ?? 0 }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Volume ratio</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ formatNumber(read.volume_ratio20, 2) }}x</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
