import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ScreenRun } from '@/types/market'

// Keeping the last run here (and its id in localStorage) lets you drill into a
// symbol on the Analyzer and come back to the same result list, and lets the
// Analyzer offer a "back to screener results" link.
const RUN_ID_KEY = 'dipwork.screener.runId.v1'

function readStoredId(): number | null {
  const raw = localStorage.getItem(RUN_ID_KEY)
  if (!raw) return null
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

export const useScreenerStore = defineStore('screener', () => {
  const run = ref<ScreenRun | null>(null)
  const runId = ref<number | null>(readStoredId())

  function setRun(next: ScreenRun): void {
    run.value = next
    runId.value = next.id
    localStorage.setItem(RUN_ID_KEY, String(next.id))
  }

  function setRunId(id: number | null): void {
    runId.value = id
    if (id === null) {
      run.value = null
      localStorage.removeItem(RUN_ID_KEY)
    } else {
      localStorage.setItem(RUN_ID_KEY, String(id))
    }
  }

  function clear(): void {
    run.value = null
    setRunId(null)
  }

  return { run, runId, setRun, setRunId, clear }
})
