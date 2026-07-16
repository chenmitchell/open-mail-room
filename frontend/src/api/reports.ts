// 03-API-SPEC.md §2 `GET /reports/summary?from=&to=&group_by=` and
// `GET /exports/items.csv|xlsx` (+ ASSUMPTION `outbound.csv`, same
// export-endpoint family, needed by the task brief's "匯出按鈕
// (items.csv/outbound.csv 下載)").
import { apiClient } from './client'
import { toQueryString } from './queryString'
import type { ReportSummary, ReportSummaryQuery } from '@/types/api'

const API_BASE = '/api/v1'

export function getReportSummary(query: ReportSummaryQuery): Promise<ReportSummary> {
  return apiClient.get<ReportSummary>(`/reports/summary${toQueryString(query)}`)
}

export interface ExportDateRange {
  date_from?: string
  date_to?: string
}

/**
 * Pure URL builder (kept separate from the DOM side effect below so it's
 * directly unit-testable). ASSUMPTION: 03 doesn't document query params for
 * the export endpoints — reusing `date_from`/`date_to`, the same convention
 * `GET /items` already uses (src/types/api.ts `ItemsQuery`).
 */
export function getExportUrl(kind: 'items' | 'outbound', range: ExportDateRange = {}): string {
  return `${API_BASE}/exports/${kind}.csv${toQueryString(range)}`
}

/**
 * Triggers a same-origin file download for an export URL. Uses a
 * programmatic `<a download>` click (not `window.location`/`window.open`)
 * so the current SPA route never navigates away — the browser sends the
 * HttpOnly session cookie automatically since this is a same-origin GET
 * (safe method, no CSRF header needed per src/api/client.ts's
 * `SAFE_METHODS` convention).
 */
export function triggerExportDownload(url: string): void {
  const link = document.createElement('a')
  link.href = url
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}
