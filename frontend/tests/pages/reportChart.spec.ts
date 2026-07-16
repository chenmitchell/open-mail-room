import { describe, expect, it } from 'vitest'
import { buildBarChart } from '@/pages/reports/reportChart'
import type { ReportSummaryRow } from '@/types/api'

function row(overrides: Partial<ReportSummaryRow>): ReportSummaryRow {
  return {
    key: overrides.key ?? 'k1',
    label: overrides.label ?? 'Label',
    received_count: 0,
    picked_up_count: 0,
    unclaimed_count: 0,
    outbound_shipped_count: 0,
    ...overrides,
  }
}

describe('buildBarChart', () => {
  it('returns one bar per row, in the same order', () => {
    const rows = [
      row({ key: 'dept-a', label: '行銷部', received_count: 10 }),
      row({ key: 'dept-b', label: '總務部', received_count: 5 }),
    ]
    const bars = buildBarChart(rows)
    expect(bars.map((b) => b.key)).toEqual(['dept-a', 'dept-b'])
    expect(bars.map((b) => b.label)).toEqual(['行銷部', '總務部'])
  })

  it('scales percent relative to the largest value in the set', () => {
    const rows = [
      row({ key: 'a', received_count: 10 }),
      row({ key: 'b', received_count: 5 }),
      row({ key: 'c', received_count: 20 }),
    ]
    const bars = buildBarChart(rows)
    expect(bars[0].percent).toBe(50)
    expect(bars[1].percent).toBe(25)
    expect(bars[2].percent).toBe(100)
  })

  it('does not divide by zero when every row is zero', () => {
    const rows = [row({ key: 'a', received_count: 0 }), row({ key: 'b', received_count: 0 })]
    const bars = buildBarChart(rows)
    expect(bars.every((b) => b.percent === 0)).toBe(true)
  })

  it('switches which metric drives the bars based on the metric argument (group_by 切換情境)', () => {
    const rows = [
      row({ key: 'a', received_count: 4, picked_up_count: 2, unclaimed_count: 9 }),
      row({ key: 'b', received_count: 8, picked_up_count: 6, unclaimed_count: 1 }),
    ]
    expect(buildBarChart(rows, 'received_count').map((b) => b.value)).toEqual([4, 8])
    expect(buildBarChart(rows, 'picked_up_count').map((b) => b.value)).toEqual([2, 6])
    expect(buildBarChart(rows, 'unclaimed_count').map((b) => b.value)).toEqual([9, 1])
  })

  it('returns an empty array for an empty row set', () => {
    expect(buildBarChart([])).toEqual([])
  })
})
