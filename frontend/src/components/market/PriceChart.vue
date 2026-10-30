<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createChart,
  type AreaData,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp
} from 'lightweight-charts'
import Term from '@/components/Term.vue'
import type { ChartBar, Trade, WatchBand } from '@/types/market'
import { formatMoney, formatPercent, formatTime } from '@/utils/format'

type Source = 'blind' | 'hindsight'

const props = defineProps<{
  bars: ChartBar[]
  trades: Trade[]
  bands: WatchBand[]
  timeframe: string
  source: Source
}>()
const emit = defineEmits<{ 'update:source': [value: Source] }>()

const BAND_COLORS: Record<WatchBand['kind'], string> = {
  watch: 'rgba(245, 158, 11, 0.13)',
  extended: 'rgba(14, 165, 233, 0.10)'
}

const container = ref<HTMLElement | null>(null)
const viewMode = ref<'recent' | 'all'>('recent')
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let volumeSeries: ISeriesApi<'Histogram'> | null = null
let bandSeries: ISeriesApi<'Area'> | null = null
let observer: ResizeObserver | null = null
let barTimes = new Set<string>()

const latest = computed(() => (props.bars.length ? props.bars[props.bars.length - 1] : null))
const changePct = computed(() => {
  if (props.bars.length < 2) return 0
  const prev = props.bars[props.bars.length - 2].close
  const next = props.bars[props.bars.length - 1].close
  return prev ? ((next - prev) / prev) * 100 : 0
})

function timeOf(iso: string): Time | null {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  if (props.timeframe === '1d') return iso.slice(0, 10)
  return Math.floor(date.getTime() / 1000) as UTCTimestamp
}

function timeKey(time: Time): string {
  if (typeof time === 'string') return time
  if (typeof time === 'number') return String(time)
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`
}

function formatTimeLabel(time: Time): string {
  if (typeof time === 'string') return time
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
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`
}

function buildMarkers(): SeriesMarker<Time>[] {
  if (!props.trades.length) return []
  const markers: SeriesMarker<Time>[] = []
  for (const trade of props.trades.slice(-40)) {
    const entry = timeOf(trade.entry_ts)
    const exit = timeOf(trade.exit_ts)
    if (entry && barTimes.has(timeKey(entry))) {
      markers.push({
        time: entry,
        position: 'belowBar',
        color: '#2563eb',
        shape: 'arrowUp',
        text: 'B'
      })
    }
    if (exit && barTimes.has(timeKey(exit))) {
      const color =
        trade.exit_reason === 'target' ? '#059669' : trade.exit_reason === 'stop' ? '#e11d48' : '#64748b'
      const text = trade.exit_reason === 'target' ? 'T' : trade.exit_reason === 'stop' ? 'S' : 'X'
      markers.push({
        time: exit,
        position: 'aboveBar',
        color,
        shape: 'arrowDown',
        text
      })
    }
  }
  return markers.sort((a, b) => {
    const ta = typeof a.time === 'number' ? a.time : String(a.time)
    const tb = typeof b.time === 'number' ? b.time : String(b.time)
    return ta < tb ? -1 : ta > tb ? 1 : 0
  })
}

// A full-height area, tinted per bar when the bar falls inside a band. An area
// (unlike histogram columns) leaves no gaps between bars when zoomed in.
function buildBandData(): AreaData[] {
  const bands = [...props.bands].sort((a, b) => a.start.localeCompare(b.start))
  const spans = bands.map((band) => ({
    kind: band.kind,
    start: new Date(band.start).getTime(),
    end: new Date(band.end).getTime()
  }))
  const out: AreaData[] = []
  let pointer = 0
  for (const bar of props.bars) {
    const time = timeOf(bar.ts)
    if (!time) continue
    const t = new Date(bar.ts).getTime()
    while (pointer < spans.length && spans[pointer].end < t) pointer += 1
    const span = spans[pointer]
    const inside = span && span.start <= t && t <= span.end
    const color = inside ? BAND_COLORS[span.kind] : 'rgba(0, 0, 0, 0)'
    out.push({ time, value: 1, topColor: color, bottomColor: color, lineColor: 'rgba(0, 0, 0, 0)' })
  }
  return out
}

function applyView(): void {
  if (!chart) return
  if (viewMode.value === 'all') {
    chart.timeScale().fitContent()
  } else if (props.bars.length) {
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, props.bars.length - 380),
      to: props.bars.length + 8
    })
  }
}

function buildChart(): void {
  if (!container.value) return
  if (chart) {
    chart.remove()
    chart = null
    candleSeries = null
    volumeSeries = null
    bandSeries = null
  }
  if (!props.bars.length) {
    barTimes = new Set()
    return
  }

  chart = createChart(container.value, {
    height: 430,
    layout: {
      background: { color: '#ffffff' },
      textColor: '#64748b',
      fontSize: 11
    },
    grid: {
      vertLines: { color: '#f1f5f9' },
      horzLines: { color: '#f1f5f9' }
    },
    rightPriceScale: { borderColor: '#e2e8f0' },
    timeScale: {
      borderColor: '#e2e8f0',
      timeVisible: props.timeframe !== '1d',
      secondsVisible: false,
      rightOffset: 6
    },
    crosshair: { mode: 0 },
    localization: { timeFormatter: formatTimeLabel }
  })

  // Added first so the shading sits behind the candles.
  bandSeries = chart.addAreaSeries({
    priceScaleId: 'bands',
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
    lineWidth: 1,
    lineColor: 'rgba(0, 0, 0, 0)',
    // Pin the hidden scale to 0..1 so a value of 1 reaches the top edge.
    autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 1 } })
  })
  chart.priceScale('bands').applyOptions({ visible: false, scaleMargins: { top: 0, bottom: 0 } })

  candleSeries = chart.addCandlestickSeries({
    upColor: '#16a34a',
    downColor: '#dc2626',
    borderVisible: false,
    wickUpColor: '#16a34a',
    wickDownColor: '#dc2626'
  })
  volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: ''
  })
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 }
  })

  const candles: CandlestickData[] = []
  const volumes: HistogramData[] = []
  barTimes = new Set()
  for (const bar of props.bars) {
    const time = timeOf(bar.ts)
    if (!time) continue
    barTimes.add(timeKey(time))
    candles.push({
      time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close
    })
    volumes.push({
      time,
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(22, 163, 74, 0.20)' : 'rgba(220, 38, 38, 0.20)'
    })
  }
  candleSeries.setData(candles)
  volumeSeries.setData(volumes)
  bandSeries.setData(buildBandData())
  candleSeries.setMarkers(buildMarkers())
  applyView()

  observer?.disconnect()
  observer = new ResizeObserver(() => {
    if (chart && container.value) {
      chart.applyOptions({ width: container.value.clientWidth })
    }
  })
  observer.observe(container.value)
  chart.applyOptions({ width: container.value.clientWidth })
}

onMounted(buildChart)
// Post-flush: the container only exists once bars render, so build after the DOM updates.
watch(() => props.bars, buildChart, { deep: false, flush: 'post' })
watch(() => props.trades, () => {
  if (candleSeries) candleSeries.setMarkers(buildMarkers())
}, { deep: false })
watch(() => props.bands, () => {
  if (bandSeries) bandSeries.setData(buildBandData())
}, { deep: false })
watch(viewMode, applyView)

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
      <div class="flex items-baseline gap-3">
        <h2 class="text-sm font-semibold text-slate-900">Price &amp; signals</h2>
        <span v-if="latest" class="text-xs tabular-nums text-slate-500">
          {{ formatMoney(latest.close) }}
          <span :class="changePct >= 0 ? 'text-emerald-600' : 'text-rose-600'">{{ formatPercent(changePct) }}</span>
        </span>
        <span v-if="latest" class="text-[11px] text-slate-400">{{ formatTime(latest.ts) }} ET</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[11px] text-slate-400">{{ bars.length.toLocaleString() }} bars · {{ timeframe }}</span>
        <div class="flex rounded-lg border border-slate-200 p-0.5 text-[11px]">
          <button
            type="button"
            class="rounded-md px-2 py-1 font-medium transition"
            :class="source === 'blind' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:text-slate-800'"
            @click="emit('update:source', 'blind')"
          >
            Blind trades
          </button>
          <button
            type="button"
            class="rounded-md px-2 py-1 font-medium transition"
            :class="source === 'hindsight' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'"
            @click="emit('update:source', 'hindsight')"
          >
            Hindsight trades
          </button>
        </div>
        <div class="flex rounded-lg border border-slate-200 p-0.5 text-[11px]">
          <button
            type="button"
            class="rounded-md px-2 py-1 font-medium transition"
            :class="viewMode === 'recent' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'"
            @click="viewMode = 'recent'"
          >
            Recent
          </button>
          <button
            type="button"
            class="rounded-md px-2 py-1 font-medium transition"
            :class="viewMode === 'all' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'"
            @click="viewMode = 'all'"
          >
            Fit all
          </button>
        </div>
      </div>
    </div>
    <div v-if="!bars.length" class="flex h-96 items-center justify-center text-sm text-slate-400">
      Build a profile to load the price chart.
    </div>
    <div v-else ref="container" class="w-full" />
    <div v-if="bars.length" class="flex flex-wrap items-center gap-3 border-t border-slate-100 px-5 py-2 text-[11px] text-slate-400">
      <span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-blue-600" /> buy</span>
      <span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-emerald-600" /> target</span>
      <span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-rose-600" /> stop</span>
      <span class="flex items-center gap-1"><span class="h-2 w-2 rounded-full bg-slate-500" /> timeout</span>
      <span class="flex items-center gap-1"><span class="h-2.5 w-3 rounded-sm bg-amber-400/40" /> <Term k="watch_state">watching</Term></span>
      <span class="flex items-center gap-1"><span class="h-2.5 w-3 rounded-sm bg-sky-400/30" /> extended</span>
      <span class="ml-auto">
        {{ source === 'blind'
          ? 'Trades the blind simulation made, with the cutoff it knew at the time.'
          : 'Trades of the best rule picked with hindsight.' }}
      </span>
    </div>
  </div>
</template>
