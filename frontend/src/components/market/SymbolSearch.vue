<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { searchSymbols } from '@/services/market'
import { useAnalyzerStore } from '@/stores/analyzer'
import type { SearchResult } from '@/types/market'

const emit = defineEmits<{ select: [symbol: string] }>()
const store = useAnalyzerStore()

const query = ref(store.symbol)
const results = ref<SearchResult[]>([])
const open = ref(false)
const searching = ref(false)
const root = ref<HTMLElement | null>(null)
let timer: number | undefined
let requestId = 0

const examples = computed(() =>
  String(store.provider?.name ?? '') === 'synthetic'
    ? ['DEMO', 'SYNTH-FAKE', 'SYNTH-CLEAN', 'SYNTH-DOWN', 'SYNTH-QUIET']
    : ['AAPL', 'TSLA', 'NVDA', 'AMD', 'META']
)

async function runSearch(): Promise<void> {
  const text = query.value.trim()
  if (text.length < 1) {
    results.value = []
    return
  }
  const id = ++requestId
  searching.value = true
  try {
    const found = await searchSymbols(text)
    if (id === requestId) {
      results.value = found
      open.value = true
    }
  } catch {
    if (id === requestId) results.value = []
  } finally {
    if (id === requestId) searching.value = false
  }
}

function scheduleSearch(): void {
  window.clearTimeout(timer)
  timer = window.setTimeout(runSearch, 220)
}

function choose(symbol: string): void {
  store.setSymbol(symbol)
  query.value = symbol
  open.value = false
  results.value = []
  emit('select', symbol)
}

function submit(): void {
  const text = query.value.trim().toUpperCase()
  const exact = results.value.find((result) => result.symbol === text)
  if (exact) {
    choose(exact.symbol)
  } else if (results.value.length) {
    choose(results.value[0].symbol)
  } else if (text) {
    choose(text)
  }
}

function onDocumentClick(event: MouseEvent): void {
  if (root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

watch(
  () => store.symbol,
  (value) => {
    if (value) query.value = value
  }
)

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  window.clearTimeout(timer)
})
</script>

<template>
  <div ref="root" class="relative w-full">
    <div class="relative">
      <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path stroke-linecap="round" d="m20 20-3.5-3.5" />
      </svg>
      <input
        v-model="query"
        class="input pl-9 pr-24 font-semibold uppercase"
        placeholder="Search a ticker…"
        aria-label="Search a ticker"
        @input="scheduleSearch"
        @focus="open = true"
        @keydown.enter.prevent="submit"
        @keydown.esc="open = false"
      >
      <button
        class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
        type="button"
        :disabled="store.loading"
        @click="submit"
      >
        {{ store.loading ? 'Working' : 'Analyze' }}
      </button>
    </div>

    <div v-if="open" class="absolute z-40 mt-2 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
      <div v-if="searching" class="px-3 py-2 text-xs text-slate-500">Searching…</div>
      <button
        v-for="result in results"
        :key="result.symbol"
        type="button"
        class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition hover:bg-slate-50"
        @click="choose(result.symbol)"
      >
        <span>
          <span class="text-sm font-semibold text-slate-900">{{ result.symbol }}</span>
          <span class="ml-2 text-xs text-slate-500">{{ result.name }}</span>
        </span>
        <span class="text-[11px] text-slate-400">{{ result.sector || (result.in_database ? 'cached' : 'fetch') }}</span>
      </button>
      <button
        v-if="!results.length && query.trim()"
        type="button"
        class="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-50"
        @click="submit"
      >
        <span class="text-sm text-slate-700">Analyze <span class="font-semibold">{{ query.trim().toUpperCase() }}</span></span>
        <span class="text-[11px] text-slate-400">Enter</span>
      </button>
      <div class="flex flex-wrap gap-1.5 border-t border-slate-100 bg-slate-50/70 px-3 py-2">
        <button
          v-for="example in examples"
          :key="example"
          type="button"
          class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:border-blue-300 hover:text-blue-700"
          @click="choose(example)"
        >
          {{ example }}
        </button>
      </div>
    </div>
  </div>
</template>
