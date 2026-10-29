<script setup lang="ts">
defineProps<{
  label: string
  value: string
  hint?: string
  tone?: 'default' | 'good' | 'bad' | 'warn'
}>()
</script>

<template>
  <div class="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
    <div class="text-[11px] font-medium uppercase tracking-wide text-slate-400">{{ label }}</div>
    <div
      class="mt-0.5 text-lg font-semibold tabular-nums"
      :class="{
        'text-emerald-700': tone === 'good',
        'text-rose-700': tone === 'bad',
        'text-amber-700': tone === 'warn',
        'text-slate-900': !tone || tone === 'default'
      }"
    >
      {{ value }}
    </div>
    <div v-if="hint" class="mt-0.5 text-[11px] leading-tight text-slate-400">{{ hint }}</div>
  </div>
</template>
