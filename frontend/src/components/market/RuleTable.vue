<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import BucketBars from '@/components/market/BucketBars.vue'
import {
  formatHold,
  formatNumber,
  formatRate,
  formatSignedPercent
} from '@/utils/format'

const store = useAnalyzerStore()
const selected = ref<string | null>(null)
const rules = computed(() => store.profile?.rules ?? [])
const recommendedId = computed(() => store.profile?.recommended?.rule_id ?? null)
const selectedRule = computed(() => rules.value.find((rule) => rule.rule_id === selected.value) ?? null)
const timeframe = computed(() => store.profile?.meta.timeframe ?? '5m')

function toggle(id: string): void {
  selected.value = selected.value === id ? null : id
}

function confidence(row: { hit_rate_low: number; hit_rate_high: number }): string {
  return `${formatRate(row.hit_rate_low)}–${formatRate(row.hit_rate_high)}`
}
</script>

<template>
  <div class="card overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">Signal rule comparison</h2>
        <p class="mt-0.5 text-xs text-slate-500">
          Same entries, same triple-barrier labels. Ranked by shrunk weekly return minus drawdown.
        </p>
      </div>
      <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
        {{ rules.length }} rules
      </span>
    </div>

    <div class="overflow-x-auto">
      <table class="min-w-full text-left text-xs">
        <thead class="border-b border-slate-100 bg-slate-50/70 text-[10px] uppercase tracking-wide text-slate-400">
          <tr>
            <th class="px-3 py-2 font-medium">Rule</th>
            <th class="px-2 py-2 text-right font-medium">Trades</th>
            <th class="px-2 py-2 text-right font-medium">Hit</th>
            <th class="px-2 py-2 text-right font-medium">95% CI</th>
            <th class="px-2 py-2 text-right font-medium">Net EV</th>
            <th class="px-2 py-2 text-right font-medium">Weekly</th>
            <th class="px-2 py-2 text-right font-medium">/wk</th>
            <th class="px-2 py-2 text-right font-medium">Stop</th>
            <th class="px-2 py-2 text-right font-medium">Fast</th>
            <th class="px-2 py-2 text-right font-medium">Hold</th>
            <th class="px-2 py-2 text-right font-medium">Max DD</th>
            <th class="px-2 py-2 text-right font-medium">Score</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr
            v-for="rule in rules"
            :key="rule.rule_id"
            class="cursor-pointer transition hover:bg-slate-50"
            :class="rule.rule_id === recommendedId ? 'bg-emerald-50/40' : ''"
            @click="toggle(rule.rule_id)"
          >
            <td class="px-3 py-2">
              <div class="flex items-center gap-1.5">
                <span v-if="rule.rule_id === recommendedId" class="rounded bg-emerald-600 px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">pick</span>
                <span class="font-medium text-slate-900">{{ rule.name || rule.rule_id }}</span>
              </div>
              <div class="mt-0.5 flex flex-wrap gap-1">
                <span class="rounded bg-slate-100 px-1 py-0.5 text-[9px] font-medium text-slate-500">{{ rule.family }}</span>
                <span v-for="confirmation in rule.confirmations?.slice(0, 3)" :key="confirmation" class="rounded bg-slate-50 px-1 py-0.5 text-[9px] text-slate-400">{{ confirmation }}</span>
              </div>
            </td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-700">{{ rule.trades }}</td>
            <td class="px-2 py-2 text-right font-semibold tabular-nums" :class="rule.hit_rate >= 0.5 ? 'text-emerald-700' : 'text-amber-700'">{{ formatRate(rule.hit_rate) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-400">{{ confidence(rule) }}</td>
            <td class="px-2 py-2 text-right tabular-nums" :class="rule.net_ev_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatSignedPercent(rule.net_ev_pct) }}</td>
            <td class="px-2 py-2 text-right tabular-nums" :class="rule.weekly_return_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatSignedPercent(rule.weekly_return_pct) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatNumber(rule.trades_per_week, 2) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatRate(rule.stop_rate) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatRate(rule.fast_hit_rate) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatHold(rule.median_holding_minutes, timeframe) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-rose-600">{{ formatNumber(rule.max_drawdown_pct, 1) }}%</td>
            <td class="px-2 py-2 text-right font-semibold tabular-nums text-slate-900">{{ formatNumber(rule.rank_score ?? 0, 2) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selectedRule" class="border-t border-slate-100 bg-slate-50/50 p-5">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 class="text-sm font-semibold text-slate-900">{{ selectedRule.name }}</h3>
          <p class="mt-0.5 max-w-3xl text-xs text-slate-500">{{ selectedRule.description }}</p>
        </div>
        <span class="text-[11px] text-slate-400">
          {{ selectedRule.signals }} raw signals → {{ selectedRule.trades }} sequential trades.
          Splits below use all raw signals.
        </span>
      </div>
      <div class="mt-4 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <BucketBars title="By attempt" :rows="selectedRule.by_attempt" />
        <BucketBars title="By failed bounce" :rows="selectedRule.by_failed_bounce" />
        <BucketBars title="By dip depth" :rows="selectedRule.by_depth" />
        <BucketBars title="By time of day" :rows="selectedRule.by_time_of_day" empty="Daily timeframe." />
        <BucketBars title="By run-up at entry" :rows="selectedRule.by_runup" />
        <div class="rounded-lg border border-slate-200 bg-white p-3">
          <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Outcome mix</div>
          <div class="mt-2 space-y-1 text-xs text-slate-600">
            <div class="flex justify-between"><span>Target</span><span class="font-semibold tabular-nums">{{ formatRate(selectedRule.hit_rate) }}</span></div>
            <div class="flex justify-between"><span>Stop</span><span class="font-semibold tabular-nums">{{ formatRate(selectedRule.stop_rate) }}</span></div>
            <div class="flex justify-between"><span>Timeout</span><span class="font-semibold tabular-nums">{{ formatRate(selectedRule.timeout_rate) }}</span></div>
            <div class="flex justify-between"><span>Avg MFE</span><span class="font-semibold tabular-nums">{{ formatSignedPercent(selectedRule.avg_mfe_pct) }}</span></div>
            <div class="flex justify-between"><span>Avg MAE</span><span class="font-semibold tabular-nums">{{ formatSignedPercent(selectedRule.avg_mae_pct) }}</span></div>
            <div class="flex justify-between"><span>Exposure</span><span class="font-semibold tabular-nums">{{ formatRate(selectedRule.exposure_pct) }}</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
