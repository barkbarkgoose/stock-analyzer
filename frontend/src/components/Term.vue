<script setup lang="ts">
import { computed, ref } from 'vue'
import { GLOSSARY, type GlossaryKey } from '@/utils/glossary'

const props = defineProps<{ k: GlossaryKey | string }>()

const entry = computed(() => GLOSSARY[props.k as GlossaryKey])

const el = ref<HTMLElement | null>(null)
const visible = ref(false)
const position = ref({ top: 0, left: 0 })

function show(): void {
  const node = el.value
  if (!node || !entry.value) return
  const rect = node.getBoundingClientRect()
  const half = 136
  const center = rect.left + rect.width / 2
  const clamped = Math.min(Math.max(center, half), window.innerWidth - half)
  position.value = { top: rect.bottom + 6, left: clamped }
  visible.value = true
}

function hide(): void {
  visible.value = false
}
</script>

<template>
  <span
    ref="el"
    class="help-term"
    tabindex="0"
    role="note"
    @mouseenter="show"
    @mouseleave="hide"
    @focus="show"
    @blur="hide"
  >
    <slot>{{ entry?.term ?? k }}</slot>
    <Teleport to="body">
      <span
        v-if="visible && entry"
        class="help-tip"
        :style="{ top: `${position.top}px`, left: `${position.left}px` }"
      >
        <strong class="help-tip__term">{{ entry.term }}</strong>
        <span class="help-tip__body">{{ entry.short }}</span>
      </span>
    </Teleport>
  </span>
</template>
