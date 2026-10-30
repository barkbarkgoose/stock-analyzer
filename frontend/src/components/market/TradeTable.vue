<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import {
  formatDateTime,
  formatHold,
  formatMoney,
  formatNumber,
  formatPercent,
  formatRate,
  formatSignedPercent
} from '@/utils/format'

type Filter = 'all' | 'wins' | 'stops' | 'timeouts'
const props = defineProps<{ source: 'blind' | 'hindsight' }>()
const store = useAnalyzerStore()
const filter = ref<Filter>('all')
const showAll = ref(false)

const isBlind = computed(() => props.source === 'blind')
const stats = computed(() =>
  isBlind.value ? store.profile?.blind.summary : store.profile?.recommended?.stats
)
const timeframe = computed(() => store.profile?.meta.timeframe ?? '5m')
const trades = computed(() =>
  [...((isBlind.value ? store.profile?.blind.trades : store.profile?.trades) ?? [])].reverse()
)
const ruleNames = computed(
  () => new Map((store.profile?.rules ?? []).map((rule) => [rule.rule_id, rule.name ?? rule.rule_id]))
)
const filtered = computed(() => {
  if (filter.value === 'wins') return trades.value.filter((trade) => trade.success)
  if (filter.value === 'stops') return trades.value.filter((trade) => trade.exit_reason === 'stop')
  if (filter.value === 'timeouts') return trades.value.filter((trade) => trade.exit_reason === 'timeout')
  return trades.value
})
const visible = computed(() => (showAll.value ? filtered.value : filtered.value.slice(0, 60)))

function reasonTone(reason: string): string {
  if (reason === 'target') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (reason === 'stop') return 'bg-rose-50 text-rose-700 ring-rose-200'
  return 'bg-slate-100 text-slate-600 ring-slate-200'
}
</script>

<template>
  <div class="card overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">{{ isBlind ? 'Blind trade log' : 'Hindsight trade log' }}</h2>
        <p class="mt-0.5 text-xs text-slate-500">
          {{ isBlind
            ? 'Every trade the blind simulation made, with the rule it had chosen that day.'
            : 'The best rule picked after seeing all the history.' }}
          One position at a time. Entry is the next bar's open; stop-first on ambiguous bars.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <select v-model="filter" class="input h-8 py-0 text-xs">
          <option value="all">All trades</option>
          <option value="wins">Wins</option>
          <option value="stops">Stops</option>
          <option value="timeouts">Timeouts</option>
        </select>
        <span v-if="stats" class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
          {{ stats.trades }} trades · {{ formatRate(stats.hit_rate) }} hit
        </span>
      </div>
    </div>

    <div v-if="!trades.length" class="p-5 text-sm text-slate-400">
      {{ isBlind ? 'The blind simulation made no trades.' : 'No simulated trades for the recommended rule.' }}
    </div>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full text-left text-xs">
        <thead class="border-b border-slate-100 bg-slate-50/70 text-[10px] uppercase tracking-wide text-slate-400">
          <tr>
            <th class="px-3 py-2 font-medium">Entry</th>
            <th v-if="isBlind" class="px-2 py-2 font-medium">Rule</th>
            <th class="px-2 py-2 text-right font-medium">Price</th>
            <th class="px-2 py-2 text-right font-medium">Exit</th>
            <th class="px-2 py-2 text-right font-medium">Return</th>
            <th class="px-2 py-2 font-medium">Reason</th>
            <th class="px-2 py-2 text-right font-medium">Hold</th>
            <th v-if="!isBlind" class="px-2 py-2 text-right font-medium">P(win)</th>
            <th class="px-2 py-2 text-right font-medium">Attempt</th>
            <th class="px-2 py-2 text-right font-medium">Failed</th>
            <th class="px-2 py-2 text-right font-medium">Run-up</th>
            <th class="px-2 py-2 text-right font-medium">Dip</th>
            <th class="px-2 py-2 text-right font-medium">MFE / MAE</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="trade in visible" :key="`${trade.signal_index}-${trade.entry_ts}`" class="hover:bg-slate-50">
            <td class="whitespace-nowrap px-3 py-2 text-slate-600">{{ formatDateTime(trade.entry_ts) }}</td>
            <td v-if="isBlind" class="whitespace-nowrap px-2 py-2 text-slate-600">{{ ruleNames.get(trade.rule_id) ?? trade.rule_id }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-700">{{ formatMoney(trade.entry_price) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-700">{{ formatMoney(trade.exit_price) }}</td>
            <td class="px-2 py-2 text-right font-semibold tabular-nums" :class="trade.net_return_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'">
              {{ formatSignedPercent(trade.net_return_pct) }}
            </td>
            <td class="px-2 py-2">
              <span class="rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1" :class="reasonTone(trade.exit_reason)">
                {{ trade.exit_reason }}
              </span>
            </td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ formatHold(trade.holding_trading_minutes, timeframe) }}</td>
            <td v-if="!isBlind" class="px-2 py-2 text-right tabular-nums text-slate-500">{{ formatRate(trade.probability) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">#{{ trade.features.attempt_number }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ trade.features.failed_bounces_1pct }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ formatPercent(trade.features.runup_from_low_pct) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">{{ formatPercent(trade.features.episode_depth_pct) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-500">
              {{ formatPercent(trade.mfe_pct) }} / {{ formatPercent(trade.mae_pct) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="filtered.length > 60" class="border-t border-slate-100 px-5 py-2 text-center">
      <button class="text-xs font-medium text-blue-600 hover:text-blue-700" type="button" @click="showAll = !showAll">
        {{ showAll ? 'Show recent 60' : `Show all ${filtered.length}` }}
      </button>
    </div>
    <div class="border-t border-slate-100 px-5 py-2 text-[11px] text-slate-400">
      Net returns include {{ formatNumber(store.profile?.config.entry_slippage_bps ?? 0, 0) }} bps entry + {{ formatNumber(store.profile?.config.exit_slippage_bps ?? 0, 0) }} bps exit slippage and {{ formatNumber(store.profile?.config.commission_bps ?? 0, 0) }} bps/side commission. Not financial advice.
    </div>
  </div>
</template>
