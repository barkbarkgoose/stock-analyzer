<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import Term from '@/components/Term.vue'
import type { RuleStats } from '@/types/market'
import {
  formatNumber,
  formatRate,
  formatSignedPercent
} from '@/utils/format'

type Tab = 'overview' | 'calibration' | 'thresholds' | 'walk'
const store = useAnalyzerStore()
const activeTab = ref<Tab>('overview')
const model = computed(() => store.profile?.model)
const ruleWalk = computed(() => store.profile?.walk_forward)

const features = computed(() => (model.value?.features ?? []).slice(0, 10))
const maxImportance = computed(() =>
  Math.max(0.01, ...features.value.map((feature) => Math.abs(feature.coefficient)))
)
const filtered = computed(() => {
  const value = model.value?.filtered_stats
  return value && Object.keys(value).length ? (value as RuleStats) : null
})
const unfiltered = computed(() => {
  const value = model.value?.unfiltered_oos_stats
  return value && Object.keys(value).length ? (value as RuleStats) : null
})
const recommendedThreshold = computed(() => model.value?.recommended_threshold ?? 0.5)

const tabs: Array<{ id: Tab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'thresholds', label: 'Thresholds' },
  { id: 'walk', label: 'Walk-forward' }
]
</script>

<template>
  <div class="card overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">Probability model</h2>
        <p class="mt-0.5 text-xs text-slate-500">
          P(hit target before stop) from the episode/confirmation context.
        </p>
      </div>
      <div v-if="model?.available" class="flex rounded-lg border border-slate-200 p-0.5 text-[11px]">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="rounded-md px-2.5 py-1 font-medium transition"
          :class="activeTab === tab.id ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div v-if="!model" class="p-5 text-sm text-slate-400">Build a profile to train the model.</div>

    <div v-else-if="!model.available" class="p-5">
      <div class="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <p class="font-medium text-slate-800">Model not available yet</p>
        <p class="mt-1 text-xs leading-relaxed">{{ model.reason }}</p>
        <p class="mt-2 text-xs text-slate-500">
          The rule comparison is still valid. Add more historical data or loosen the sample requirements to train a model.
        </p>
      </div>
    </div>

    <div v-else class="p-5">
      <div v-if="activeTab === 'overview'" class="space-y-5">
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="auc">AUC</Term></div>
            <div class="text-lg font-semibold tabular-nums" :class="(model.auc ?? 0) >= 0.55 ? 'text-emerald-700' : 'text-slate-900'">{{ formatNumber(model.auc, 3) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="brier">Brier</Term></div>
            <div class="text-lg font-semibold tabular-nums text-slate-900">{{ formatNumber(model.brier, 3) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="base_rate">Base rate</Term></div>
            <div class="text-lg font-semibold tabular-nums text-slate-900">{{ formatRate(model.base_rate) }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400">Samples</div>
            <div class="text-lg font-semibold tabular-nums text-slate-900">{{ model.samples }}</div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-slate-400"><Term k="oos">OOS</Term> test</div>
            <div class="text-lg font-semibold tabular-nums text-slate-900">{{ model.test_samples }}</div>
          </div>
          <div class="rounded-lg bg-blue-50 px-3 py-2">
            <div class="text-[10px] uppercase tracking-wide text-blue-500"><Term k="threshold">Threshold</Term></div>
            <div class="text-lg font-semibold tabular-nums text-blue-800">{{ formatNumber(recommendedThreshold, 2) }}</div>
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <div>
            <div class="mb-2 flex items-center justify-between">
              <h3 class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Feature weights</h3>
              <span class="text-[10px] text-slate-400">standardised logistic coefficients</span>
            </div>
            <div class="space-y-2">
              <div v-for="feature in features" :key="feature.name" class="text-xs">
                <div class="flex items-center justify-between gap-2">
                  <span class="truncate font-medium text-slate-700">{{ feature.name.replace(/_/g, ' ') }}</span>
                  <span class="shrink-0 tabular-nums" :class="feature.coefficient >= 0 ? 'text-emerald-700' : 'text-rose-700'">
                    {{ feature.coefficient >= 0 ? '+' : '' }}{{ formatNumber(feature.coefficient, 2) }}
                  </span>
                </div>
                <div class="mt-1 flex h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    class="h-full rounded-full"
                    :class="feature.coefficient >= 0 ? 'bg-emerald-500' : 'bg-rose-400'"
                    :style="{ width: `${Math.max(2, Math.round((Math.abs(feature.coefficient) / maxImportance) * 100))}%` }"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="space-y-4">
            <div>
              <div class="mb-2 flex items-center justify-between">
                <h3 class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Model filter vs unfiltered (held-out OOS)</h3>
                <span class="rounded-full px-2 py-0.5 text-[10px] font-medium" :class="model.use_filter ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'">
                  {{ model.use_filter ? 'filter on' : 'filter off' }}
                </span>
              </div>
              <p v-if="model.filter_eval?.method" class="mb-2 text-[10px] leading-snug text-slate-400">
                {{ model.filter_eval.method }} · select {{ model.filter_eval.selection_samples }} / eval {{ model.filter_eval.eval_samples }}.
              </p>
              <div class="overflow-hidden rounded-lg border border-slate-200">
                <table class="min-w-full text-left text-xs">
                  <thead class="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
                    <tr>
                      <th class="px-2 py-1.5 font-medium">Variant</th>
                      <th class="px-2 py-1.5 text-right font-medium">Trades</th>
                      <th class="px-2 py-1.5 text-right font-medium">Hit</th>
                      <th class="px-2 py-1.5 text-right font-medium">Net EV</th>
                      <th class="px-2 py-1.5 text-right font-medium">Weekly</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr>
                      <td class="px-2 py-1.5 text-slate-600">Unfiltered</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ unfiltered?.trades ?? '—' }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ unfiltered ? formatRate(unfiltered.hit_rate) : '—' }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ unfiltered ? formatSignedPercent(unfiltered.net_ev_pct) : '—' }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ unfiltered ? formatSignedPercent(unfiltered.weekly_return_pct) : '—' }}</td>
                    </tr>
                    <tr class="bg-blue-50/40">
                      <td class="px-2 py-1.5 font-medium text-blue-900">Filtered</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ filtered?.trades ?? '—' }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ filtered ? formatRate(filtered.hit_rate) : '—' }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ filtered ? formatSignedPercent(filtered.net_ev_pct) : '—' }}</td>
                      <td class="px-2 py-1.5 text-right tabular-nums">{{ filtered ? formatSignedPercent(filtered.weekly_return_pct) : '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-if="model.fast" class="rounded-lg bg-slate-50 p-3 text-xs">
              <div class="font-medium text-slate-700">Fast-horizon model</div>
              <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-slate-500">
                <span>AUC <span class="font-semibold text-slate-800">{{ formatNumber(model.fast.auc, 3) }}</span></span>
                <span>Brier <span class="font-semibold text-slate-800">{{ formatNumber(model.fast.brier, 3) }}</span></span>
                <span>Base <span class="font-semibold text-slate-800">{{ formatRate(model.fast.base_rate) }}</span></span>
                <span>Samples <span class="font-semibold text-slate-800">{{ model.fast.samples }}</span></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="activeTab === 'calibration'" class="space-y-3">
        <p class="text-xs text-slate-500">
          Predicted probability vs realised hit rate on out-of-sample signals. A well-calibrated model tracks the diagonal.
        </p>
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-xs">
            <thead class="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
              <tr>
                <th class="px-2 py-2 font-medium">Probability bin</th>
                <th class="px-2 py-2 text-right font-medium">Count</th>
                <th class="px-2 py-2 text-right font-medium">Predicted</th>
                <th class="px-2 py-2 text-right font-medium">Actual</th>
                <th class="px-2 py-2 font-medium">Calibration</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="bin in model.calibration" :key="bin.bin">
                <td class="px-2 py-2 tabular-nums text-slate-600">{{ formatRate(bin.low, 0) }}–{{ formatRate(bin.high, 0) }}</td>
                <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ bin.count }}</td>
                <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatRate(bin.predicted) }}</td>
                <td class="px-2 py-2 text-right font-semibold tabular-nums text-slate-900">{{ formatRate(bin.actual) }}</td>
                <td class="px-2 py-2">
                  <div class="flex items-center gap-1">
                    <div class="h-2 flex-1 rounded-full bg-slate-100">
                      <div class="h-full rounded-full bg-blue-500" :style="{ width: `${Math.round(bin.predicted * 100)}%` }" />
                    </div>
                    <div class="h-2 flex-1 rounded-full bg-slate-100">
                      <div class="h-full rounded-full bg-emerald-500" :style="{ width: `${Math.round(bin.actual * 100)}%` }" />
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex gap-4 text-[11px] text-slate-400">
          <span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-blue-500" /> predicted</span>
          <span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-emerald-500" /> actual</span>
        </div>
      </div>

      <div v-else-if="activeTab === 'thresholds'" class="space-y-3">
        <p class="text-xs text-slate-500">
          Trade count, hit rate and weekly return at different probability cutoffs on the selection window.
          The threshold is then evaluated on the held-out OOS window above.
        </p>
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-xs">
            <thead class="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
              <tr>
                <th class="px-2 py-2 font-medium">Threshold</th>
                <th class="px-2 py-2 text-right font-medium">Trades</th>
                <th class="px-2 py-2 text-right font-medium">Hit</th>
                <th class="px-2 py-2 text-right font-medium">Net EV</th>
                <th class="px-2 py-2 text-right font-medium">Trades/wk</th>
                <th class="px-2 py-2 text-right font-medium">Weekly</th>
                <th class="px-2 py-2 text-right font-medium">Max DD</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr
                v-for="row in model.threshold_curve"
                :key="row.threshold"
                :class="Math.abs(row.threshold - recommendedThreshold) < 1e-9 ? 'bg-blue-50/50' : ''"
              >
                <td class="px-2 py-2 font-medium tabular-nums text-slate-700">
                  {{ formatNumber(row.threshold, 2) }}
                  <span v-if="Math.abs(row.threshold - recommendedThreshold) < 1e-9" class="ml-1 rounded bg-blue-600 px-1 py-0.5 text-[9px] font-bold uppercase text-white">pick</span>
                </td>
                <td class="px-2 py-2 text-right tabular-nums">{{ row.trades }}</td>
                <td class="px-2 py-2 text-right tabular-nums">{{ formatRate(row.hit_rate) }}</td>
                <td class="px-2 py-2 text-right tabular-nums">{{ formatSignedPercent(row.net_ev_pct) }}</td>
                <td class="px-2 py-2 text-right tabular-nums">{{ formatNumber(row.trades_per_week, 2) }}</td>
                <td class="px-2 py-2 text-right tabular-nums">{{ formatSignedPercent(row.weekly_return_pct) }}</td>
                <td class="px-2 py-2 text-right tabular-nums text-rose-600">{{ formatNumber(row.max_drawdown_pct, 1) }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="space-y-5">
        <div>
          <h3 class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Model folds</h3>
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-xs">
              <thead class="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                <tr>
                  <th class="px-2 py-2 font-medium">Fold</th>
                  <th class="px-2 py-2 font-medium">Test start</th>
                  <th class="px-2 py-2 text-right font-medium">Train</th>
                  <th class="px-2 py-2 text-right font-medium">Test</th>
                  <th class="px-2 py-2 text-right font-medium">AUC</th>
                  <th class="px-2 py-2 text-right font-medium">Brier</th>
                  <th class="px-2 py-2 text-right font-medium">Base</th>
                  <th class="px-2 py-2 text-right font-medium">Accuracy</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="fold in model.walk_forward" :key="fold.fold">
                  <td class="px-2 py-2 tabular-nums">{{ fold.fold }}</td>
                  <td class="px-2 py-2 text-slate-500">{{ fold.test_start?.slice(0, 10) }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ fold.train_samples }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ fold.test_samples }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatNumber(fold.auc, 3) }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatNumber(fold.brier, 3) }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatRate(fold.base_rate) }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatRate(fold.accuracy) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="ruleWalk?.folds?.length">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Rule-selection folds</h3>
            <span class="text-[10px] text-slate-400">train picks a rule; test measures it</span>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-xs">
              <thead class="border-b border-slate-100 text-[10px] uppercase tracking-wide text-slate-400">
                <tr>
                  <th class="px-2 py-2 font-medium">Fold</th>
                  <th class="px-2 py-2 font-medium">Test start</th>
                  <th class="px-2 py-2 font-medium">Selected</th>
                  <th class="px-2 py-2 text-right font-medium">Train trades</th>
                  <th class="px-2 py-2 text-right font-medium">Test trades</th>
                  <th class="px-2 py-2 text-right font-medium">Hit</th>
                  <th class="px-2 py-2 text-right font-medium">Net EV</th>
                  <th class="px-2 py-2 text-right font-medium">Weekly</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="fold in ruleWalk.folds" :key="fold.fold">
                  <td class="px-2 py-2 tabular-nums">{{ fold.fold }}</td>
                  <td class="px-2 py-2 text-slate-500">{{ fold.test_start?.slice(0, 10) }}</td>
                  <td class="px-2 py-2 font-medium text-slate-700">{{ fold.selected_rule || '—' }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ fold.train_trades ?? '—' }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ fold.test_trades ?? '—' }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatRate(fold.test_hit_rate) }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatSignedPercent(fold.test_net_ev_pct) }}</td>
                  <td class="px-2 py-2 text-right tabular-nums">{{ formatSignedPercent(fold.test_weekly_return_pct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="ruleWalk.oos" class="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            OOS selection process:
            <span class="font-semibold text-slate-900">{{ ruleWalk.oos.trades }} trades</span>,
            hit {{ formatRate(ruleWalk.oos.hit_rate) }},
            net EV {{ formatSignedPercent(ruleWalk.oos.net_ev_pct) }},
            {{ formatSignedPercent(ruleWalk.oos.weekly_return_pct) }}/wk.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
