// Pure bar-chart data helper for the 報表頁 (task brief: "卡片+簡單長條圖
// (不裝圖表庫,用 CSS/SVG 自繪)"). Kept dependency-free and framework-free so
// it's directly unit-testable — ReportsPage.vue only maps this over
// `<rect>`/`<text>` elements, no chart library involved.
import type { ReportSummaryRow } from '@/types/api'

export interface BarDatum {
  key: string
  label: string
  value: number
  /** 0-100, value relative to the largest bar in the set (0 when every value is 0). */
  percent: number
}

export type BarChartMetric = 'received_count' | 'picked_up_count' | 'unclaimed_count'

/**
 * Converts report rows into bar chart data for a single metric. Every row
 * becomes one bar, in the order given by the backend (group_by=day rows are
 * assumed chronological, department/carrier rows in whatever order `GET
 * /reports/summary` returns them).
 */
export function buildBarChart(rows: ReportSummaryRow[], metric: BarChartMetric = 'received_count'): BarDatum[] {
  const max = rows.reduce((acc, row) => Math.max(acc, row[metric] ?? 0), 0)
  return rows.map((row) => {
    const value = row[metric] ?? 0
    return {
      key: row.key,
      label: row.label,
      value,
      percent: max > 0 ? Math.round((value / max) * 100) : 0,
    }
  })
}
