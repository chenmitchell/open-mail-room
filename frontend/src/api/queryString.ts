// Shared `?a=1&b=2` builder for GET endpoints with optional filters (03 §2:
// GET /items, GET /employees, ...). Omits undefined/null/empty-string values
// so callers can pass a full filter object without manually pruning it.
export function toQueryString(params: Record<string, unknown>): string {
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    usp.set(key, String(value))
  }
  const qs = usp.toString()
  return qs ? `?${qs}` : ''
}
