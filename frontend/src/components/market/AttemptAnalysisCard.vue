<script setup lang="ts">
import { computed } from 'vue'
import { useAnalyzerStore } from '@/stores/analyzer'
import BucketBars from '@/components/market/BucketBars.vue'

const store = useAnalyzerStore()
const analysis = computed(() => store.profile?.attempt_analysis ?? null)
</script>

<template>
  <div class="card p-5">
    <div class="flex items-start justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">First bounce vs later attempts</h2>
        <p class="mt-0.5 text-xs text-slate-500">Does waiting for a failed first bounce help?</p>
      </div>
      <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">{{ analysis?.rule_id || '—' }}</span>
    </div>
    <div v-if="analysis" class="mt-4 space-y-4">
      <div class="grid gap-4 sm:grid-cols-2">
        <BucketBars title="By attempt number" :rows="analysis.by_attempt" />
        <BucketBars title="By prior failed bounce" :rows="analysis.by_failed_bounce" />
      </div>
      <p v-if="analysis.interpretation" class="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
        {{ analysis.interpretation }}
      </p>
    </div>
    <p v-else class="mt-4 text-sm text-slate-400">No attempt breakdown available for this sample.</p>
  </div>
</template>
