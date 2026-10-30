<script setup lang="ts">
import { computed } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import Term from '@/components/Term.vue'
import { formatNumber, formatPercent, formatRate } from '@/utils/format'

const store = useAnalyzerStore()
const bounces = computed(() => store.profile?.bounce_profile ?? null)
const target = computed(() => store.profile?.config.target_pct ?? 1)
</script>

<template>
  <div v-if="bounces" class="card overflow-hidden">
    <div class="border-b border-slate-100 px-5 py-3">
      <h2 class="text-sm font-semibold text-slate-900">How far this stock's dips bounce</h2>
      <p class="mt-0.5 text-xs text-slate-500">
        Not "did it fully recover?" — just how far the price climbed off the dip low before rolling over. That is the room a
        trade has to work with.
      </p>
    </div>

    <div v-if="!bounces.episodes" class="p-5 text-sm text-slate-500">{{ bounces.interpretation }}</div>

    <div v-else class="grid gap-5 p-5 lg:grid-cols-[1fr_1.2fr]">
      <div class="space-y-3">
        <p class="text-sm leading-relaxed text-slate-700">{{ bounces.interpretation }}</p>
        <div class="grid grid-cols-3 gap-2">
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">3 in 4 dips</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">≥ {{ formatPercent(bounces.p25_biggest_bounce_pct, 1) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Typical dip</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ formatPercent(bounces.median_biggest_bounce_pct, 1) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Typical attempt</div>
            <div class="text-sm font-semibold tabular-nums text-slate-900">{{ formatPercent(bounces.median_leg_pct, 1) }}</div>
          </div>
        </div>
        <div class="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-xs leading-relaxed text-amber-900">
          <div class="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
            <Term k="bounce_cutoff">Bounce cutoff</Term> · {{ bounces.cutoff_source }}
          </div>
          {{ bounces.cutoff_text }}
        </div>
      </div>

      <div>
        <div class="mb-2 flex items-baseline justify-between">
          <h3 class="text-[11px] font-semibold uppercase tracking-wider text-slate-400"><Term k="bounce_reach">Reached at least…</Term></h3>
          <span class="text-[10px] text-slate-400">{{ bounces.episodes }} dips · {{ bounces.legs }} bounce attempts</span>
        </div>
        <div class="space-y-1.5">
          <div
            v-for="row in bounces.reach"
            :key="row.level_pct"
            class="grid grid-cols-[3.5rem_1fr_1fr] items-center gap-3 rounded-md px-1.5 py-1 text-xs"
            :class="Math.abs(row.level_pct - target) < 1e-9 ? 'bg-blue-50 ring-1 ring-blue-200' : ''"
          >
            <span class="font-semibold tabular-nums text-slate-700">+{{ formatNumber(row.level_pct, 1) }}%</span>
            <div>
              <div class="flex justify-between text-[10px] text-slate-500">
                <span>dips</span><span class="tabular-nums">{{ row.episodes }} · {{ formatRate(row.episodes_pct, 0) }}</span>
              </div>
              <div class="mt-0.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div class="h-full rounded-full bg-emerald-500" :style="{ width: `${Math.round(row.episodes_pct * 100)}%` }" />
              </div>
            </div>
            <div>
              <div class="flex justify-between text-[10px] text-slate-500">
                <span>attempts</span><span class="tabular-nums">{{ row.legs }} · {{ formatRate(row.legs_pct, 0) }}</span>
              </div>
              <div class="mt-0.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div class="h-full rounded-full bg-amber-400" :style="{ width: `${Math.round(row.legs_pct * 100)}%` }" />
              </div>
            </div>
          </div>
        </div>
        <p class="mt-2 text-[11px] text-slate-400">"Attempts" includes fake bounces that rolled over into a new low. Your target is highlighted.</p>
      </div>
    </div>
  </div>
</template>
