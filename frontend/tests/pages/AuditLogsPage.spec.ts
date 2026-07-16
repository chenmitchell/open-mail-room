import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

// 01-REQUIREMENTS.md §4 稽核紀錄 / 03-API-SPEC.md §2 `GET /admin/audit-logs`.
// 06 §1 管理後台(admin): 稽核 — 分頁表格+篩選.
vi.mock('@/api/audit', () => ({ listAuditLogs: vi.fn() }))
import { listAuditLogs } from '@/api/audit'
import AuditLogsPage from '@/pages/admin/AuditLogsPage.vue'
import type { AuditLogEntry } from '@/types/api'

function entry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'a1',
    actor_type: 'user',
    actor_id: 'u1',
    actor_name: '王小明',
    action: 'mail_item.create',
    target_type: 'mail_item',
    target_id: 'i1',
    at: '2026-07-12T09:00:00+08:00',
    ...overrides,
  }
}

function mountPage() {
  return mount(AuditLogsPage, { global: { plugins: [i18n] } })
}

describe('AuditLogsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads and renders audit log entries on mount', async () => {
    vi.mocked(listAuditLogs).mockResolvedValue({ items: [entry()], meta: { total: 1, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('王小明')
    expect(wrapper.text()).toContain('mail_item.create')
  })

  it('shows the empty state when there are no matching entries', async () => {
    vi.mocked(listAuditLogs).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('沒有符合條件的稽核紀錄')
  })

  it('applies the target_type filter and re-queries', async () => {
    vi.mocked(listAuditLogs).mockResolvedValue({ items: [entry()], meta: { total: 1, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    // The filter form has 4 text inputs (actor/action/target_type/target_id)
    // then 2 date inputs, in that DOM order — target_type is the 3rd.
    const textInputs = wrapper.findAll('input:not([type="date"])')
    await textInputs[2].setValue('mail_item')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(listAuditLogs).toHaveBeenLastCalledWith(expect.objectContaining({ target_type: 'mail_item', page: 1 }))
  })

  it('opens a dialog showing the diff_json for an entry', async () => {
    vi.mocked(listAuditLogs).mockResolvedValue({
      items: [entry({ diff_json: { status: { from: 'received', to: 'notified' } } })],
      meta: { total: 1, page: 1, size: 20 },
    })
    const wrapper = mount(AuditLogsPage, { global: { plugins: [i18n] }, attachTo: document.body })
    await flushPromises()

    const viewDiffButton = wrapper.findAll('button').find((b) => b.text() === '檢視變更內容')
    expect(viewDiffButton).toBeTruthy()
    await viewDiffButton?.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('received')
    expect(document.body.textContent).toContain('notified')
    wrapper.unmount()
  })
})
