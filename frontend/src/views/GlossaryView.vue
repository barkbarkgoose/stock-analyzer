<script setup lang="ts">
import Term from '@/components/Term.vue'
import { glossaryByGroup } from '@/utils/glossary'

const sections = glossaryByGroup()
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <div class="mx-auto max-w-[1000px] px-4 py-6 sm:px-6">
      <div class="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Reference</div>
      <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">Glossary</h1>
      <p class="mt-1 max-w-2xl text-sm text-slate-500">
        Every term in plain language. Anywhere you see a
        <Term k="hit_rate">dotted underline</Term>
        like this, hover (or focus) it for the short definition.
      </p>

      <div class="mt-6 space-y-6">
        <section v-for="section in sections" :key="section.group" class="card overflow-hidden">
          <div class="border-b border-slate-100 bg-slate-50/70 px-5 py-3">
            <h2 class="text-sm font-semibold text-slate-900">{{ section.group }}</h2>
          </div>
          <dl class="divide-y divide-slate-100">
            <div v-for="item in section.entries" :key="item.key" class="grid gap-1 px-5 py-3.5 sm:grid-cols-3 sm:gap-4">
              <dt class="text-xs font-semibold text-slate-900">{{ item.entry.term }}</dt>
              <dd class="text-xs leading-relaxed text-slate-600 sm:col-span-2">
                <p>{{ item.entry.detail }}</p>
                <p class="mt-1 text-[11px] text-slate-400">{{ item.entry.short }}</p>
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  </div>
</template>
