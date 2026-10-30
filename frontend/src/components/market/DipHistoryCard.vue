<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import Term from '@/components/Term.vue'
import { formatDateTime, formatMoney, formatPercent } from '@/utils/format'
import type { Episode } from '@/types/market'

const store = useAnalyzerStore()
const showAll = ref(false)
const episodes = computed(() => [...(store.profile?.episodes ?? [])].reverse())
const visible = computed(() => (showAll.value ? episodes.value : episodes.value.slice(0, 12)))
const target = computed(() => store.profile?.config.target_pct ?? 1)

function outcome(episode: Episode): { label: string; tone: string } {
  if (!episode.end) return { label: 'in progress', tone: 'bg-amber-50 text-amber-700 ring-amber-200' }
  if (episode.recovered) return { label: 'recovered', tone: 'bg-emerald-50 text-emerald-700 ring-emerald-200' }
  return { label: 'timed out', tone: 'bg-slate-100 text-slate-600 ring-slate-200' }
}
</script>

<template>
  <div v-if="episodes.length" class="card overflow-hidden">
    <div class="border-b border-slate-100 px-5 py-3">
      <h2 class="text-sm font-semibold text-slate-900"><Term k="episode">Dips</Term> that actually happened</h2>
      <p class="mt-0.5 text-xs text-slate-500">
        Every dip in the window, newest first. "Fake bounces" rose at least 1% and then fell to a new low.
      </p>
    </div>
    <div class="overflow-x-auto">
      <table class="min-w-full text-left text-xs">
        <thead class="border-b border-slate-100 bg-slate-50/70 text-[10px] uppercase tracking-wide text-slate-400">
          <tr>
            <th class="px-3 py-2 font-medium">Started</th>
            <th class="px-2 py-2 text-right font-medium">From</th>
            <th class="px-2 py-2 text-right font-medium">Low</th>
            <th class="px-2 py-2 text-right font-medium">Depth</th>
            <th class="px-2 py-2 text-right font-medium">Fake bounces</th>
            <th class="px-2 py-2 text-right font-medium">Best bounce</th>
            <th class="px-2 py-2 font-medium">Outcome</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="episode in visible" :key="episode.id" class="hover:bg-slate-50">
            <td class="whitespace-nowrap px-3 py-2 text-slate-600">{{ formatDateTime(episode.start) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatMoney(episode.reference_high) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ formatMoney(episode.low) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-rose-700">-{{ formatPercent(episode.depth_pct, 1) }}</td>
            <td class="px-2 py-2 text-right tabular-nums text-slate-600">{{ episode.failed_bounces_1pct }}</td>
            <td
              class="px-2 py-2 text-right font-semibold tabular-nums"
              :class="episode.max_bounce_pct >= target ? 'text-emerald-700' : 'text-slate-500'"
            >
              +{{ formatPercent(episode.max_bounce_pct, 1) }}
            </td>
            <td class="px-2 py-2">
              <span class="rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1" :class="outcome(episode).tone">{{ outcome(episode).label }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="episodes.length > 12" class="border-t border-slate-100 px-5 py-2 text-center">
      <button class="text-xs font-medium text-blue-600 hover:text-blue-700" type="button" @click="showAll = !showAll">
        {{ showAll ? 'Show recent 12' : `Show all ${episodes.length}` }}
      </button>
    </div>
  </div>
</template>
