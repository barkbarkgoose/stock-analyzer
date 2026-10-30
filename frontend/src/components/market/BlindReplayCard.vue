<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import Term from '@/components/Term.vue'
import {
  formatDate,
  formatMinutes,
  formatNumber,
  formatPercent,
  formatRate,
  formatSignedPercent
} from '@/utils/format'

const store = useAnalyzerStore()
const blind = computed(() => store.profile?.blind ?? null)
const summary = computed(() => blind.value?.summary ?? null)
const hindsight = computed(() => blind.value?.hindsight_summary ?? null)
const showDecisions = ref(false)
const decisions = computed(() => [...(blind.value?.decisions ?? [])].reverse())

const beatsBreakeven = computed(() =>
  summary.value && blind.value ? summary.value.hit_rate >= blind.value.breakeven_hit_rate : false
)

function useTarget(value: number): void {
  store.setSymbolTarget(value)
  void store.analyze(false)
}

function returnTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'text-slate-400'
  return value >= 0 ? 'text-emerald-700' : 'text-rose-700'
}
</script>

<template>
  <div v-if="blind" class="card overflow-hidden">
    <div class="border-b border-slate-100 px-5 py-3">
      <h2 class="text-sm font-semibold text-slate-900"><Term k="blind_replay">Blind simulation</Term></h2>
      <p class="mt-0.5 max-w-3xl text-xs leading-relaxed text-slate-500">
        Walks through history one day at a time. Each morning it picks the buy rule and the bounce cutoff using only what
        had already happened, then trades that day — one position at a time, never seeing a later bar.
        The first {{ blind.warmup_sessions }} sessions are watch-only warm-up.
      </p>
    </div>

    <div v-if="!blind.available" class="p-5 text-sm text-slate-500">{{ blind.reason }}</div>

    <div v-else class="space-y-5 p-5">
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <div class="rounded-lg bg-slate-50 px-3 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Trades</div>
          <div class="text-lg font-semibold tabular-nums text-slate-900">{{ summary?.trades ?? 0 }}</div>
          <div class="text-[10px] text-slate-400">{{ formatNumber(summary?.trades_per_week ?? 0, 1) }}/wk</div>
        </div>
        <div class="rounded-lg px-3 py-2" :class="beatsBreakeven ? 'bg-emerald-50' : 'bg-rose-50'">
          <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="hit_rate">Hit target</Term></div>
          <div class="text-lg font-semibold tabular-nums" :class="beatsBreakeven ? 'text-emerald-800' : 'text-rose-800'">
            {{ formatRate(summary?.hit_rate, 0) }}
          </div>
          <div class="text-[10px] text-slate-500">
            need <Term k="breakeven">{{ formatRate(blind.breakeven_hit_rate, 0) }}</Term>
          </div>
        </div>
        <div class="rounded-lg bg-slate-50 px-3 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="net_ev">Net / trade</Term></div>
          <div class="text-lg font-semibold tabular-nums" :class="returnTone(summary?.net_ev_pct)">{{ formatSignedPercent(summary?.net_ev_pct) }}</div>
        </div>
        <div class="rounded-lg bg-slate-50 px-3 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Total</div>
          <div class="text-lg font-semibold tabular-nums" :class="returnTone(summary?.total_return_pct)">{{ formatSignedPercent(summary?.total_return_pct) }}</div>
          <div class="text-[10px] text-slate-400">since {{ formatDate(blind.start) }}</div>
        </div>
        <div class="rounded-lg bg-slate-50 px-3 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="max_drawdown">Max drawdown</Term></div>
          <div class="text-lg font-semibold tabular-nums text-rose-700">{{ formatNumber(summary?.max_drawdown_pct ?? 0, 1) }}%</div>
        </div>
        <div class="rounded-lg bg-slate-50 px-3 py-2">
          <div class="text-[10px] uppercase tracking-wide text-slate-400">Sat out</div>
          <div class="text-lg font-semibold tabular-nums text-slate-900">{{ blind.sessions_sat_out ?? 0 }}</div>
          <div class="text-[10px] text-slate-400">of {{ blind.sessions_decided ?? 0 }} days</div>
        </div>
      </div>

      <p class="text-sm leading-relaxed text-slate-700">{{ blind.interpretation }}</p>

      <div class="grid gap-3 sm:grid-cols-2">
        <div class="rounded-lg border border-slate-200 p-3">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Blind (what you'd have gotten)</div>
          <div class="mt-1 text-xl font-semibold tabular-nums" :class="returnTone(summary?.total_return_pct)">
            {{ formatSignedPercent(summary?.total_return_pct ?? 0) }}
          </div>
          <div class="text-[11px] text-slate-500">{{ summary?.trades ?? 0 }} trades · {{ formatRate(summary?.hit_rate, 0) }} hit</div>
        </div>
        <div class="rounded-lg border border-dashed border-slate-200 p-3">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400"><Term k="hindsight">Hindsight</Term> (same days, best rule picked after the fact)</div>
          <div class="mt-1 text-xl font-semibold tabular-nums text-slate-500">
            {{ hindsight ? formatSignedPercent(hindsight.total_return_pct) : '—' }}
          </div>
          <div class="text-[11px] text-slate-500">
            {{ hindsight ? `${hindsight.trades} trades · ${formatRate(hindsight.hit_rate, 0)} hit` : 'no hindsight rule traded these days' }}
          </div>
        </div>
      </div>

      <div v-if="blind.rule_usage?.length" class="flex flex-wrap items-center gap-1.5 text-[11px]">
        <span class="font-medium text-slate-500">Rules the trader used:</span>
        <span
          v-for="usage in blind.rule_usage"
          :key="usage.rule_id ?? 'none'"
          class="rounded-full px-2 py-0.5 ring-1"
          :class="usage.rule_id ? 'bg-blue-50 text-blue-700 ring-blue-200' : 'bg-slate-100 text-slate-500 ring-slate-200'"
        >
          {{ usage.name }} · {{ usage.sessions }}d · {{ usage.trades }} trades
        </span>
      </div>
    </div>

    <div class="border-t border-slate-100">
      <div class="flex flex-wrap items-baseline justify-between gap-2 px-5 pt-4">
        <h3 class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <Term k="target_ladder">What if the target were higher?</Term>
        </h3>
        <span class="text-[11px] text-slate-400">each row is a full blind simulation · stop stays -{{ formatNumber(blind.stop_pct, 2) }}%</span>
      </div>
      <div class="overflow-x-auto px-2 pb-2">
        <table class="min-w-full text-left text-xs">
          <thead class="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
            <tr>
              <th class="px-3 py-2 font-medium">Target</th>
              <th class="px-2 py-2 text-right font-medium">Trades</th>
              <th class="px-2 py-2 text-right font-medium">Hit</th>
              <th class="px-2 py-2 text-right font-medium">Need</th>
              <th class="px-2 py-2 text-right font-medium">Net / trade</th>
              <th class="px-2 py-2 text-right font-medium">Total</th>
              <th class="px-2 py-2 text-right font-medium">Max DD</th>
              <th class="px-2 py-2 text-right font-medium">Median hold</th>
              <th class="px-2 py-2" />
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="row in blind.ladder" :key="row.target_pct" :class="row.current ? 'bg-blue-50/60' : 'hover:bg-slate-50'">
              <td class="px-3 py-2 font-semibold tabular-nums text-slate-800">+{{ formatNumber(row.target_pct, 2) }}%</td>
              <td class="px-2 py-2 text-right tabular-nums">{{ row.trades }}</td>
              <td
                class="px-2 py-2 text-right font-medium tabular-nums"
                :class="row.trades ? ((row.hit_rate ?? 0) >= row.breakeven_hit_rate ? 'text-emerald-700' : 'text-rose-700') : 'text-slate-400'"
              >
                {{ row.trades ? formatRate(row.hit_rate, 0) : '—' }}
              </td>
              <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ formatRate(row.breakeven_hit_rate, 0) }}</td>
              <td class="px-2 py-2 text-right tabular-nums" :class="returnTone(row.net_ev_pct)">{{ formatSignedPercent(row.net_ev_pct) }}</td>
              <td class="px-2 py-2 text-right font-semibold tabular-nums" :class="returnTone(row.total_return_pct)">{{ formatSignedPercent(row.total_return_pct) }}</td>
              <td class="px-2 py-2 text-right tabular-nums text-rose-600">{{ row.max_drawdown_pct !== null ? `${formatNumber(row.max_drawdown_pct, 1)}%` : '—' }}</td>
              <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ formatMinutes(row.median_holding_minutes) }}</td>
              <td class="px-2 py-2 text-right">
                <span v-if="row.current" class="text-[10px] font-semibold uppercase tracking-wide text-blue-700">in use</span>
                <button v-else class="btn-ghost text-[11px]" type="button" :disabled="store.loading" @click="useTarget(row.target_pct)">use</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="px-5 pb-4 text-[11px] leading-relaxed text-slate-400">
        "Need" is the <Term k="breakeven">break-even hit rate</Term> after costs. Picking the best row by eye is a little
        hindsight of its own — prefer a target whose neighbours also hold up.
      </p>
    </div>

    <div v-if="decisions.length" class="border-t border-slate-100 px-5 py-3">
      <button class="text-xs font-medium text-blue-600 hover:text-blue-700" type="button" @click="showDecisions = !showDecisions">
        {{ showDecisions ? 'Hide' : 'Show' }} the trader's daily decisions ({{ decisions.length }})
      </button>
      <div v-if="showDecisions" class="mt-3 max-h-80 overflow-auto">
        <table class="min-w-full text-left text-xs">
          <thead class="sticky top-0 border-b border-slate-100 bg-white text-[10px] uppercase tracking-wide text-slate-400">
            <tr>
              <th class="px-2 py-2 font-medium">Day</th>
              <th class="px-2 py-2 font-medium">Rule chosen</th>
              <th class="px-2 py-2 text-right font-medium">Cutoff</th>
              <th class="px-2 py-2 font-medium">Why</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="decision in decisions" :key="decision.session">
              <td class="whitespace-nowrap px-2 py-1.5 text-slate-600">{{ decision.session }}</td>
              <td class="px-2 py-1.5 font-medium" :class="decision.rule_name ? 'text-slate-800' : 'text-slate-400'">{{ decision.rule_name ?? 'Sit out' }}</td>
              <td class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-slate-500">
                {{ formatPercent(decision.cutoff_pct) }}
                <span class="text-[10px] text-slate-400">{{ decision.cutoff_source }}</span>
              </td>
              <td class="px-2 py-1.5 text-slate-500">{{ decision.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
