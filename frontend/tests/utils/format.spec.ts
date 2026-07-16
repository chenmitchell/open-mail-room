import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { formatDate, formatDateTime } from '@/utils/format'

// Bug fix regression test: the backend always stores/returns UTC timestamps
// (e.g. `received_at`), and every user-facing timestamp must render in
// Asia/Taipei (台北時間) regardless of the browser/OS's own default
// timezone. Before the fix, formatDateTime/formatDate omitted `timeZone:
// 'Asia/Taipei'` from the Intl.DateTimeFormat options and so silently fell
// back to the runtime's local timezone -- correct only by accident on a
// Taipei-configured machine, wrong everywhere else (e.g. a UTC server, or a
// browser in another timezone).
//
// These tests force `process.env.TZ` to a non-Taipei zone before each
// assertion so the pass/fail signal doesn't depend on this machine's
// timezone already happening to be Asia/Taipei.
describe('formatDateTime / formatDate (Asia/Taipei display timezone)', () => {
  const originalTz = process.env.TZ

  beforeEach(() => {
    process.env.TZ = 'America/New_York'
  })

  afterEach(() => {
    process.env.TZ = originalTz
  })

  it('formats a UTC timestamp as Taipei time (UTC+8), not the runtime-local timezone', () => {
    // 2026-01-01T23:15:00Z + 8h = 2026-01-02 07:15 Taipei time. In
    // America/New_York (UTC-5 in January) the same instant is still
    // 2026-01-01 18:15 -- a different calendar day -- so this also proves
    // the fix isn't just "off by a few hours" but resolves to the correct
    // Taipei wall-clock date/time.
    const result = formatDateTime('2026-01-01T23:15:00Z')
    expect(result).toContain('2026/1/2')
    expect(result).toContain('7:15')
    expect(result).not.toContain('2026/1/1')
  })

  it('formats a UTC timestamp with a negative-offset-crossing date as the Taipei calendar date', () => {
    // 2026-07-12T20:00:00Z + 8h = 2026-07-13 04:00 Taipei time.
    const result = formatDateTime('2026-07-12T20:00:00Z')
    expect(result).toContain('2026/7/13')
  })

  it('formatDate resolves the Taipei calendar date, independent of runtime timezone', () => {
    // 2026-01-01T23:15:00Z is still "2026-01-01" in America/New_York but
    // "2026-01-02" in Asia/Taipei.
    expect(formatDate('2026-01-01T23:15:00Z')).toBe('2026/1/2')
  })

  it('returns an empty string for null/undefined/invalid input', () => {
    expect(formatDateTime(null)).toBe('')
    expect(formatDateTime(undefined)).toBe('')
    expect(formatDateTime('not-a-date')).toBe('')
    expect(formatDate(null)).toBe('')
    expect(formatDate('not-a-date')).toBe('')
  })
})
