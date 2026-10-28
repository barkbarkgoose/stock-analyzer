/**
 * Pull the first human-readable message out of a DRF error body.
 * Handles `{detail: "..."}` as well as field-keyed errors like
 * `{password: ["This password is too common."]}`.
 */
export function firstError(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  for (const value of Object.values(data as Record<string, unknown>)) {
    if (typeof value === 'string') return value
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  }
  return null
}
