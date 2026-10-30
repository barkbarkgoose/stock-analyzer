const NY = 'America/New_York'

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

export function formatRate(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toFixed(digits)}%`
}

export function formatSignedPercent(
  value: number | null | undefined,
  digits = 2
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

export function formatMoney(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  }).format(value)
}

export function formatCompactMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return `$${value.toFixed(0)}`
}

export function formatMinutes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (value < 60) return `${Math.round(value)}m`
  const hours = value / 60
  return hours < 10 ? `${hours.toFixed(1)}h` : `${hours.toFixed(0)}h`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: NY
  }).format(date)
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: NY
  }).format(date)
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: NY
  }).format(date)
}

export function statusTone(status: string | null | undefined): string {
  switch (status) {
    case 'qualified':
    case 'signal':
      return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
    case 'watch':
    case 'watching':
      return 'bg-amber-50 text-amber-700 ring-amber-200'
    case 'reject':
      return 'bg-rose-50 text-rose-700 ring-rose-200'
    case 'extended':
      return 'bg-sky-50 text-sky-700 ring-sky-200'
    default:
      return 'bg-slate-100 text-slate-600 ring-slate-200'
  }
}

export function riskTone(level: string | null | undefined): string {
  switch (level) {
    case 'lower':
      return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
    case 'moderate':
      return 'bg-amber-50 text-amber-700 ring-amber-200'
    case 'high':
    case 'elevated':
      return 'bg-rose-50 text-rose-700 ring-rose-200'
    default:
      return 'bg-slate-100 text-slate-600 ring-slate-200'
  }
}

export function reasonTone(passed: boolean): string {
  return passed
    ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
    : 'bg-rose-50 text-rose-700 ring-rose-200'
}

export function formatHold(minutes: number | null | undefined, timeframe: string): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return '—'
  if (timeframe === '1d') {
    const days = minutes / 390
    if (days < 0.5) return 'intraday'
    return `${days.toFixed(days < 10 ? 1 : 0)}d`
  }
  return formatMinutes(minutes)
}
