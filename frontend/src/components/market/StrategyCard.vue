<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import Term from '@/components/Term.vue'
import type { ChecklistItem } from '@/types/market'
import {
  formatMoney,
  formatPercent,
  formatRate,
  formatSignedPercent,
  formatTime,
  statusTone
} from '@/utils/format'

const store = useAnalyzerStore()
const strategy = computed(() => store.profile?.strategy ?? null)
const read = computed(() => store.liveRead ?? store.profile?.signal_read ?? null)
const symbol = computed(() => store.profile?.meta.symbol ?? store.symbol)

const presetTargets = [1, 1.5, 2, 2.5]
const currentTarget = computed(() => strategy.value?.sell.target_pct ?? store.effectiveConfig?.target_pct ?? 1)
const defaultTarget = computed(() => store.config?.target_pct ?? 1)
const hasOverride = computed(() => store.symbolOverride.target_pct !== undefined)
const customTarget = ref<number | null>(null)
watch(currentTarget, (value) => {
  customTarget.value = presetTargets.includes(value) ? null : value
}, { immediate: true })

function useTarget(value: number | null): void {
  if (value !== null && (!Number.isFinite(value) || value <= 0)) return
  store.setSymbolTarget(value)
  void store.analyze(false)
}

function onCustom(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value) && value > 0) useTarget(value)
}

const stateLabel = computed(() => {
  switch (read.value?.state) {
    case 'signal':
      return 'Buy signal'
    case 'watching':
      return 'Watching'
    case 'extended':
      return 'Extended'
    case 'no_setup':
      return 'No setup'
    default:
      return 'No data'
  }
})

const watchItems = computed<ChecklistItem[]>(() => read.value?.watch_checklist ?? [])
const dipItem = computed(() => watchItems.value[0])
const otherWatchItems = computed(() => watchItems.value.slice(2))
const buyItems = computed<ChecklistItem[]>(() => read.value?.buy_checklist ?? [])
const offLow = computed(() => read.value?.off_low_pct ?? 0)
const cutoff = computed(() => read.value?.cutoff_pct ?? strategy.value?.stop_watching.cutoff_pct ?? 0)
const roomUsed = computed(() =>
  cutoff.value > 0 ? Math.min(100, Math.max(0, (offLow.value / cutoff.value) * 100)) : 0
)
const inDip = computed(() => Boolean(read.value?.episode_active))
const track = computed(() => strategy.value?.track_record)
const levels = computed(() => read.value?.levels)
</script>

<template>
  <div v-if="strategy" class="card overflow-hidden">
    <div class="flex flex-col gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Strategy for {{ symbol }}</span>
          <span v-if="read" class="rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1" :class="statusTone(read.state)">
            <Term k="watch_state">{{ stateLabel }}</Term>
          </span>
          <span v-if="read?.ts" class="text-[11px] text-slate-400">as of {{ formatTime(read.ts) }} ET</span>
        </div>
        <h2 class="mt-1.5 text-lg font-semibold tracking-tight text-slate-900">{{ strategy.headline }}</h2>
        <p v-if="read" class="mt-0.5 text-sm text-slate-600">{{ read.detail }}</p>
      </div>
    </div>

    <ol class="grid divide-y divide-slate-100 md:grid-cols-2 md:divide-y-0 xl:grid-cols-4 xl:divide-x">
      <li class="p-4">
        <div class="step-label"><span class="step-num">1</span> Watch</div>
        <p class="mt-2 text-sm leading-relaxed text-slate-700">{{ strategy.watch.text }}</p>
        <div v-if="dipItem" class="mt-3 flex items-start gap-1.5 text-xs" :class="dipItem.ok ? 'text-emerald-700' : 'text-slate-500'">
          <span class="check-dot" :class="dipItem.ok ? 'check-dot--ok' : ''">{{ dipItem.ok ? '✓' : '·' }}</span>
          <span>
            {{ dipItem.ok ? `In a dip now: ${formatPercent(read?.episode_depth_pct ?? 0, 1)} down` : 'Not in a dip right now' }}
          </span>
        </div>
      </li>

      <li class="p-4">
        <div class="step-label"><span class="step-num">2</span> <Term k="bounce_cutoff">Stop watching</Term></div>
        <p class="mt-2 text-sm leading-relaxed text-slate-700">{{ strategy.stop_watching.text }}</p>
        <div v-if="inDip" class="mt-3">
          <div class="flex justify-between text-[11px] text-slate-500">
            <span>Now {{ formatPercent(offLow) }} off the low</span>
            <span>cutoff {{ formatPercent(cutoff) }}</span>
          </div>
          <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              class="h-full rounded-full"
              :class="roomUsed >= 100 ? 'bg-sky-500' : 'bg-amber-400'"
              :style="{ width: `${Math.max(2, roomUsed)}%` }"
            />
          </div>
        </div>
      </li>

      <li class="p-4">
        <div class="step-label"><span class="step-num">3</span> Buy</div>
        <template v-if="strategy.buy">
          <p class="mt-2 text-sm leading-relaxed text-slate-700">{{ strategy.buy.text }}</p>
          <ul v-if="inDip && buyItems.length" class="mt-3 space-y-1">
            <li v-for="item in [...otherWatchItems, ...buyItems]" :key="item.label" class="flex items-start gap-1.5 text-xs" :class="item.ok ? 'text-emerald-700' : 'text-slate-500'">
              <span class="check-dot" :class="item.ok ? 'check-dot--ok' : ''">{{ item.ok ? '✓' : '·' }}</span>
              <span>{{ item.label }}</span>
            </li>
          </ul>
          <ul v-else class="mt-3 space-y-1">
            <li v-for="check in strategy.buy.checks" :key="check" class="flex items-start gap-1.5 text-xs text-slate-500">
              <span class="check-dot">·</span>
              <span>{{ check }}</span>
            </li>
          </ul>
        </template>
        <template v-else>
          <p class="mt-2 text-sm font-medium text-slate-800">Sit out — don't buy this stock yet.</p>
          <p class="mt-1 text-xs leading-relaxed text-slate-500">{{ strategy.note }}</p>
        </template>
      </li>

      <li class="p-4">
        <div class="step-label"><span class="step-num">4</span> Sell</div>
        <p class="mt-2 text-sm leading-relaxed text-slate-700">{{ strategy.sell.text }}</p>
        <div v-if="read?.state === 'signal' || read?.state === 'watching'" class="mt-3 grid grid-cols-3 gap-1.5 text-center">
          <div class="rounded-md bg-slate-50 px-1.5 py-1">
            <div class="text-[9px] uppercase tracking-wide text-slate-400">Entry ~</div>
            <div class="text-xs font-semibold tabular-nums text-slate-800">{{ formatMoney(levels?.entry_estimate) }}</div>
          </div>
          <div class="rounded-md bg-emerald-50 px-1.5 py-1">
            <div class="text-[9px] uppercase tracking-wide text-emerald-600">Target</div>
            <div class="text-xs font-semibold tabular-nums text-emerald-800">{{ formatMoney(levels?.target) }}</div>
          </div>
          <div class="rounded-md bg-rose-50 px-1.5 py-1">
            <div class="text-[9px] uppercase tracking-wide text-rose-600">Stop</div>
            <div class="text-xs font-semibold tabular-nums text-rose-800">{{ formatMoney(levels?.stop) }}</div>
          </div>
        </div>
      </li>
    </ol>

    <div class="flex flex-col gap-3 border-t border-slate-100 bg-slate-50/60 px-5 py-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="font-medium text-slate-600">Target for {{ symbol }}</span>
        <div class="flex rounded-lg border border-slate-200 bg-white p-0.5">
          <button
            v-for="value in presetTargets"
            :key="value"
            type="button"
            class="rounded-md px-2 py-1 font-medium tabular-nums transition"
            :class="currentTarget === value ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'"
            :disabled="store.loading"
            @click="useTarget(value)"
          >
            +{{ value }}%
          </button>
        </div>
        <input
          class="input h-7 w-20 py-0 text-xs tabular-nums"
          type="number"
          min="0.25"
          max="10"
          step="0.25"
          placeholder="custom"
          :value="customTarget ?? ''"
          :disabled="store.loading"
          @change="onCustom"
        >
        <button v-if="hasOverride" class="btn-ghost text-[11px]" type="button" :disabled="store.loading" @click="useTarget(null)">
          reset to default (+{{ defaultTarget }}%)
        </button>
        <span v-if="store.loading" class="text-[11px] text-slate-400">re-running…</span>
      </div>
      <div v-if="track" class="text-xs text-slate-600">
        <Term k="blind_replay">Blind simulation</Term>:
        <template v-if="track.trades">
          <span class="font-semibold text-slate-900">{{ track.trades }} trades</span>,
          {{ formatRate(track.hit_rate, 0) }} hit target,
          <span class="font-semibold" :class="(track.total_return_pct ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'">
            {{ formatSignedPercent(track.total_return_pct) }}
          </span>
          total
        </template>
        <span v-else class="text-slate-500">no trades yet</span>
      </div>
    </div>
  </div>
</template>

