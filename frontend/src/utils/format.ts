// Small formatting helpers shared by the inbound/pickup/search pages.
// Kept dependency-free (no date-fns/dayjs) to match the existing scaffold's
// minimal-dependency style.

/**
 * Parses an ISO timestamp from the API.
 *
 * The API contract is "always UTC, always offset-bearing". This helper stays
 * defensive about the offset-less form anyway, because getting it wrong is
 * silent and 8 hours large: `new Date("2026-07-16T06:30:05")` is parsed by JS
 * as *local* time, so an offset-less UTC timestamp would render 8 hours early
 * for a Taipei browser. (That was a real bug -- SQLite drops tzinfo, so the
 * backend used to emit exactly that form; fixed by `UtcDateTime` server-side.
 * This guard means a stale cache, an older backend, or a future regression
 * degrades to "correct" instead of "quietly wrong".)
 */
export function parseApiDate(iso: string): Date {
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso)
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso)
  return new Date(hasOffset || dateOnly ? iso : `${iso}Z`)
}

/**
 * Formats an ISO timestamp for display. The backend returns UTC timestamps;
 * the UI always renders them in Asia/Taipei (台北時間) regardless of the
 * browser's local timezone, per the product requirement that every
 * user-facing timestamp is Taipei time.
 */
export function formatDateTime(iso: string | null | undefined, locale = 'zh-TW'): string {
  if (!iso) return ''
  const date = parseApiDate(iso)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'Asia/Taipei',
  }).format(date)
}

/** Same Asia/Taipei display-timezone policy as {@link formatDateTime}, date-only. */
export function formatDate(iso: string | null | undefined, locale = 'zh-TW'): string {
  if (!iso) return ''
  const date = parseApiDate(iso)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeZone: 'Asia/Taipei' }).format(date)
}

/** `<input type="datetime-local">` value for "now", in the local timezone. */
export function nowForDateTimeLocalInput(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`
}

/** `<input type="date">` value for "today", in the local timezone. */
export function todayForDateInput(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
