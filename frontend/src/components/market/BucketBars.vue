<script setup lang="ts">
import type { BucketStat } from '@/types/market'
import { formatRate, formatSignedPercent } from '@/utils/format'

defineProps<{
  title: string
  rows: BucketStat[]
  empty?: string
}>()

function barColor(rate: number): string {
  if (rate >= 0.65) return 'bg-emerald-500'
  if (rate >= 0.5) return 'bg-amber-400'
  return 'bg-rose-400'
}
</script>

<template>
  <div>
    <div class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{{ title }}</div>
    <div v-if="rows.length" class="space-y-2">
      <div v-for="row in rows" :key="row.bucket" class="text-xs">
        <div class="flex items-center justify-between gap-2">
          <span class="truncate font-medium text-slate-700">{{ row.bucket }}</span>
          <span class="shrink-0 tabular-nums text-slate-500">
            {{ formatRate(row.hit_rate) }} · {{ row.signals }} sig · {{ formatSignedPercent(row.net_ev_pct) }}
          </span>
        </div>
        <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div class="h-full rounded-full" :class="barColor(row.hit_rate)" :style="{ width: `${Math.max(2, Math.round(row.hit_rate * 100))}%` }" />
        </div>
      </div>
    </div>
    <p v-else class="text-xs text-slate-400">{{ empty || 'No samples in this split.' }}</p>
  </div>
</template>
