<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createChart,
  type IChartApi,
  type LineData,
  type Time,
  type UTCTimestamp
} from 'lightweight-charts'
import { useAnalyzerStore } from '@/stores/analyzer'
import { formatSignedPercent } from '@/utils/format'

const store = useAnalyzerStore()
const container = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let series: ReturnType<IChartApi['addLineSeries']> | null = null
let observer: ResizeObserver | null = null

const points = computed(() => store.profile?.equity_curve ?? [])
const timeframe = computed(() => store.profile?.meta.timeframe ?? '5d')
const totalReturn = computed(() => {
  const last = points.value[points.value.length - 1]
  return last ? (last.equity - 1) * 100 : 0
})
const maxDrawdown = computed(() => {
  let peak = 0
  let worst = 0
  for (const point of points.value) {
    peak = Math.max(peak, point.equity)
    if (peak > 0) worst = Math.min(worst, (point.equity / peak - 1) * 100)
  }
  return worst
})

function timeOf(iso: string): Time {
  if (timeframe.value === '1d') return iso.slice(0, 10)
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

function build(): void {
  if (!container.value) return
  if (chart) {
    chart.remove()
    chart = null
    series = null
  }
  if (!points.value.length) return
  chart = createChart(container.value, {
    height: 230,
    layout: { background: { color: '#ffffff' }, textColor: '#64748b', fontSize: 11 },
    grid: { vertLines: { color: '#f8fafc' }, horzLines: { color: '#f1f5f9' } },
    rightPriceScale: { borderColor: '#e2e8f0' },
    timeScale: { borderColor: '#e2e8f0', timeVisible: timeframe.value !== '1d', secondsVisible: false },
    crosshair: { mode: 0 },
    localization: {
      timeFormatter: (time: Time) => {
        if (typeof time === 'number') {
          return new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/New_York',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
          }).format(new Date(time * 1000))
        }
        return String(time)
      }
    }
  })
  series = chart.addLineSeries({
    color: '#2563eb',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true
  })
  const data: LineData[] = points.value.map((point) => ({
    time: timeOf(point.ts),
    value: point.equity
  }))
  series.setData(data)
  series.createPriceLine({
    price: 1,
    color: '#94a3b8',
    lineWidth: 1,
    lineStyle: 2,
    axisLabelVisible: false,
    title: 'start'
  })
  chart.timeScale().fitContent()
  observer?.disconnect()
  observer = new ResizeObserver(() => {
    if (chart && container.value) chart.applyOptions({ width: container.value.clientWidth })
  })
  observer.observe(container.value)
  chart.applyOptions({ width: container.value.clientWidth })
}

onMounted(build)
watch(points, build, { deep: false })
onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.remove()
  chart = null
})
</script>

<template>
  <div class="card overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">Compounded equity</h2>
        <p class="mt-0.5 text-xs text-slate-500">Sequential trades, full notional, net of costs.</p>
      </div>
      <div class="flex gap-4 text-xs">
        <span>Return <span class="font-semibold tabular-nums" :class="totalReturn >= 0 ? 'text-emerald-700' : 'text-rose-700'">{{ formatSignedPercent(totalReturn) }}</span></span>
        <span>Max DD <span class="font-semibold tabular-nums text-rose-700">{{ formatSignedPercent(maxDrawdown) }}</span></span>
      </div>
    </div>
    <div v-if="!points.length" class="flex h-48 items-center justify-center text-sm text-slate-400">
      No equity curve yet.
    </div>
    <div v-else ref="container" class="w-full" />
  </div>
</template>
