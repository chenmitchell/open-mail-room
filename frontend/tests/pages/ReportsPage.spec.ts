import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

// 06-UI-UX.md §1 「查詢/報表」(counter/viewer): 日期區間+group_by 切換
// (部門/承運商/日),卡片+簡單長條圖(不裝圖表庫)+表格 fallback,匯出按鈕.
vi.mock('@/api/reports', () => ({
  getReportSummary: vi.fn(),
  getExportUrl: vi.fn((kind: string) => `/api/v1/exports/${kind}.csv`),
  triggerExportDownload: vi.fn(),
}))
import { getExportUrl, getReportSummary, triggerExportDownload } from '@/api/reports'
import ReportsPage from '@/pages/reports/ReportsPage.vue'
import type { ReportSummary } from '@/types/api'

function summary(overrides: Partial<ReportSummary> = {}): ReportSummary {
  return {
    group_by: 'department',
    from: '2026-06-12',
    to: '2026-07-12',
    rows: [
      {
        key: 'd1', label: '行銷部', received_count: 10, picked_up_count: 8, unclaimed_count: 1,
        outbound_shipped_count: 5,
      },
      {
        key: 'd2', label: '總務部', received_count: 4, picked_up_count: 4, unclaimed_count: 0,
        outbound_shipped_count: 2,
      },
    ],
    totals: {
      received_count: 14, picked_up_count: 12, unclaimed_count: 1, avg_pickup_hours: 3.5,
      outbound_shipped_count: 7,
    },
    ...overrides,
  }
}

function mountPage() {
  return mount(ReportsPage, { global: { plugins: [i18n] } })
}

describe('ReportsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the default (department) summary on mount and renders stat card totals', async () => {
    vi.mocked(getReportSummary).mockResolvedValue(summary())
    const wrapper = mountPage()
    await flushPromises()

    expect(getReportSummary).toHaveBeenCalledWith(expect.objectContaining({ group_by: 'department' }))
    expect(wrapper.text()).toContain('14')
    expect(wrapper.text()).toContain('12')
    // RC-FIX #7: 交寄量 (outbound_shipped_count) stat card + table column.
    expect(wrapper.text()).toContain('7')
  })

  it('renders one bar and one table row per report row, plus a chart aria-label (table fallback)', async () => {
    vi.mocked(getReportSummary).mockResolvedValue(summary())
    const wrapper = mountPage()
    await flushPromises()

    const bars = wrapper.findAll('.reports-page__bar-row')
    expect(bars).toHaveLength(2)

    const chart = wrapper.find('[role="img"]')
    expect(chart.exists()).toBe(true)
    expect(chart.attributes('aria-label')).toBeTruthy()

    const tableRows = wrapper.findAll('.reports-page__table tbody tr')
    expect(tableRows).toHaveLength(2)
    expect(tableRows[0].text()).toContain('行銷部')
    expect(tableRows[0].text()).toContain('10')
    expect(tableRows[0].text()).toContain('5')
  })

  it('switching group_by re-queries the summary and re-renders the chart/table for the new grouping', async () => {
    vi.mocked(getReportSummary).mockResolvedValueOnce(summary())
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.findAll('.reports-page__bar-row')).toHaveLength(2)

    vi.mocked(getReportSummary).mockResolvedValueOnce(
      summary({
        group_by: 'carrier',
        rows: [
          { key: 'c1', label: '黑貓', received_count: 3, picked_up_count: 3, unclaimed_count: 0, outbound_shipped_count: 1 },
          { key: 'c2', label: '新竹', received_count: 6, picked_up_count: 5, unclaimed_count: 1, outbound_shipped_count: 0 },
          { key: 'c3', label: '順豐', received_count: 2, picked_up_count: 2, unclaimed_count: 0, outbound_shipped_count: 4 },
        ],
      }),
    )

    await wrapper.find('select').setValue('carrier')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(getReportSummary).toHaveBeenLastCalledWith(expect.objectContaining({ group_by: 'carrier' }))
    expect(wrapper.findAll('.reports-page__bar-row')).toHaveLength(3)
    expect(wrapper.findAll('.reports-page__table tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('黑貓')
  })

  it('shows the empty state when the range has no rows', async () => {
    vi.mocked(getReportSummary).mockResolvedValue(summary({ rows: [] }))
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('此區間沒有資料')
    expect(wrapper.findAll('.reports-page__bar-row')).toHaveLength(0)
  })

  it('exporting items/outbound triggers a download for the matching export URL', async () => {
    vi.mocked(getReportSummary).mockResolvedValue(summary())
    const wrapper = mountPage()
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const itemsBtn = buttons.find((b) => b.text().includes('items.csv'))
    const outboundBtn = buttons.find((b) => b.text().includes('outbound.csv'))

    await itemsBtn?.trigger('click')
    expect(getExportUrl).toHaveBeenCalledWith('items', expect.any(Object))
    expect(triggerExportDownload).toHaveBeenCalledWith('/api/v1/exports/items.csv')

    await outboundBtn?.trigger('click')
    expect(getExportUrl).toHaveBeenCalledWith('outbound', expect.any(Object))
    expect(triggerExportDownload).toHaveBeenCalledWith('/api/v1/exports/outbound.csv')
  })
})
