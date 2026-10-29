<script setup lang="ts">
import { useAnalyzerStore } from '@/stores/analyzer'
import type { AnalysisConfig } from '@/types/market'

const store = useAnalyzerStore()

function setField(key: keyof AnalysisConfig, value: string | number | boolean): void {
  if (!store.config) return
  store.updateConfig({ [key]: value } as Partial<AnalysisConfig>)
}

function onNumber(key: keyof AnalysisConfig, event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
  setField(key, Number.isFinite(value) ? value : 0)
}

function onText(key: keyof AnalysisConfig, event: Event): void {
  setField(key, (event.target as HTMLInputElement | HTMLSelectElement).value)
}

function onBool(key: keyof AnalysisConfig, event: Event): void {
  setField(key, (event.target as HTMLInputElement).checked)
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div>
        <h2 class="text-sm font-semibold text-slate-900">Study config</h2>
        <p class="mt-0.5 text-xs text-slate-500">Changes apply on the next build.</p>
      </div>
      <button class="btn-ghost text-xs" type="button" @click="store.resetConfig()">Reset</button>
    </div>

    <div v-if="!store.config" class="p-4 text-sm text-slate-500">Loading config…</div>

    <div v-else class="divide-y divide-slate-100">
      <section v-for="section in store.schema" :key="section.id" class="p-4">
        <h3 class="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {{ section.label }}
        </h3>
        <div class="space-y-3">
          <div v-for="field in section.fields" :key="field.key">
            <label class="mb-1 block text-xs font-medium text-slate-600" :for="`cfg-${field.key}`">
              {{ field.label }}
            </label>
            <select
              v-if="field.type === 'select'"
              :id="`cfg-${field.key}`"
              class="input"
              :value="String(store.config[field.key] ?? '')"
              @change="onText(field.key, $event)"
            >
              <option v-for="option in field.options" :key="option" :value="option">
                {{ option }}
              </option>
            </select>
            <label
              v-else-if="field.type === 'boolean'"
              class="flex cursor-pointer items-center gap-2 text-sm text-slate-700"
            >
              <input
                :id="`cfg-${field.key}`"
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                :checked="Boolean(store.config[field.key])"
                @change="onBool(field.key, $event)"
              >
              Enabled
            </label>
            <input
              v-else
              :id="`cfg-${field.key}`"
              class="input tabular-nums"
              type="number"
              :min="field.min"
              :max="field.max"
              :step="field.step ?? 1"
              :value="Number(store.config[field.key] ?? 0)"
              @input="onNumber(field.key, $event)"
            >
          </div>
        </div>
      </section>

      <details class="group p-4" open>
        <summary class="cursor-pointer text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Model &amp; data
        </summary>
        <div class="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Daily history (d)</label>
            <input class="input tabular-nums" type="number" min="120" max="4000" :value="store.config.daily_history_days" @input="onNumber('daily_history_days', $event)">
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Intraday history (d)</label>
            <input class="input tabular-nums" type="number" min="5" max="2000" :value="store.config.intraday_history_days" @input="onNumber('intraday_history_days', $event)">
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Min model samples</label>
            <input class="input tabular-nums" type="number" min="20" max="1000" :value="store.config.min_samples_for_model" @input="onNumber('min_samples_for_model', $event)">
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Walk-forward folds</label>
            <input class="input tabular-nums" type="number" min="2" max="8" :value="store.config.walk_forward_folds" @input="onNumber('walk_forward_folds', $event)">
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Min trades / rule</label>
            <input class="input tabular-nums" type="number" min="1" max="100" :value="store.config.min_trades_for_rule" @input="onNumber('min_trades_for_rule', $event)">
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-600">Model threshold</label>
            <input class="input tabular-nums" type="number" min="0.05" max="0.95" step="0.05" :value="store.config.model_threshold" @input="onNumber('model_threshold', $event)">
          </div>
        </div>
      </details>
    </div>

    <div class="border-t border-slate-100 p-4">
      <button class="btn-primary w-full" type="button" :disabled="store.loading" @click="store.analyze(false)">
        {{ store.loading ? 'Building…' : 'Build profile' }}
      </button>
      <button class="btn-secondary mt-2 w-full" type="button" :disabled="store.loading" @click="store.analyze(true)">
        Refresh data &amp; rebuild
      </button>
      <p class="mt-2 text-center text-[11px] text-slate-400">
        {{ store.config ? `${store.config.timeframe} · target ${store.config.target_pct}% · stop ${store.config.stop_pct}%` : '' }}
      </p>
    </div>
  </div>
</template>
