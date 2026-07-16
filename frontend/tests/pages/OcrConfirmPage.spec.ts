import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { i18n } from '@/i18n'
import { useOcrConfirmQueueStore } from '@/stores/ocrConfirmQueue'

// 06-UI-UX.md §1 OCR 確認頁: "左圖右表...欄位可改...信心低欄位標黃". This
// spec drives the page end-to-end against mocked API modules (the polling /
// draft / carrier / item-creation calls) to prove a prefilled OCR field can
// be edited by the counter and that the edited value — not the AI's guess —
// is what gets POSTed to /items.
//
// FE-STABILITY regression coverage: the confirm page used to render photos
// from an in-memory `URL.createObjectURL` blob handed off by the
// capture/upload pages (`QueuedOcrJob.photoUrls`). Those URLs die the moment
// the tab reloads (page refresh, or a PWA service-worker update swapping the
// document), leaving a blank/broken image even though the upload itself
// succeeded. The fix loads photos straight from the server via
// `GET /api/v1/uploads/{attachment_id}` (built by `getUploadUrl`), keyed off
// `QueuedOcrJob.attachmentIds` — which survives a reload because it's part
// of the job data returned by the backend, not a browser-memory handle.
vi.mock('@/api/carriers', () => ({ listCarriers: vi.fn() }))
vi.mock('@/api/employees', () => ({ matchEmployees: vi.fn() }))
vi.mock('@/api/items', () => ({ createItem: vi.fn() }))
vi.mock('@/api/ocr', () => ({ getOcrJob: vi.fn(), getOcrDraft: vi.fn() }))

import { listCarriers } from '@/api/carriers'
import { createItem } from '@/api/items'
import { getOcrDraft, getOcrJob } from '@/api/ocr'
import { getUploadUrl } from '@/api/uploads'
import OcrConfirmPage from '@/pages/inbound/OcrConfirmPage.vue'

function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: { template: '<div />' } },
      { path: '/photo', name: 'inbound-photo', component: { template: '<div />' } },
    ],
  })
  return mount(OcrConfirmPage, {
    global: { plugins: [i18n, router] },
  })
}

describe('OcrConfirmPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())

    vi.mocked(listCarriers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    vi.mocked(getOcrJob).mockResolvedValue({
      id: 'job-1',
      attachment_ids: ['att-1'],
      status: 'succeeded',
    })
    vi.mocked(getOcrDraft).mockResolvedValue({
      job_id: 'job-1',
      status: 'succeeded',
      draft: {
        tracking_no: null,
        carrier_guess: null,
        sender_name: '王大明',
        sender_org: null,
        sender_phone: null,
        recipient_name: '陳小華',
        recipient_dept_hint: null,
        is_handwritten: false,
        confidence: 0.5, // below the 0.7 threshold -> non-empty AI fields flagged low-confidence
      },
      employee_candidates: [],
    })
    vi.mocked(createItem).mockResolvedValue({
      id: 'item-1',
      item_no: 'IN-20260711-0001',
      mail_type: 'parcel',
      recipient_name_raw: '陳小華',
      received_at: '2026-07-11T00:00:00+08:00',
      status: 'received',
      is_confidential: false,
      is_cod: false,
      refrigeration: 'none',
      remind_count: 0,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('prefills the form from the OCR draft, preferring the barcode-scanned tracking number over the AI guess', async () => {
    const queue = useOcrConfirmQueueStore()
    queue.push({
      jobId: 'job-1',
      attachmentIds: ['att-1'],
      barcodeHint: '9988776655',
    })

    const wrapper = mountPage()
    await flushPromises()

    const inputs = wrapper.findAll('input')
    const trackingInput = inputs[0]
    const senderNameInput = inputs[1]
    const recipientInput = inputs[3]

    // 04 §1: "單號若條碼已取得,AI 結果不覆蓋" — barcode value wins even though
    // the draft's own tracking_no is null here.
    expect(trackingInput.element.value).toBe('9988776655')
    expect(senderNameInput.element.value).toBe('王大明')
    expect(recipientInput.element.value).toBe('陳小華')

    // Low-confidence AI fields (confidence 0.5 < 0.7) are visibly flagged —
    // colour is never the only signal (06 §3), so the wrapper carries both a
    // background class and a hint string.
    expect(wrapper.find('.ocr-confirm-page__field--low-confidence').exists()).toBe(true)
    expect(wrapper.text()).toContain('AI 辨識信心偏低')
  })

  it('renders the photo from the server-side attachment endpoint, not a memory blob URL', async () => {
    const queue = useOcrConfirmQueueStore()
    queue.push({
      jobId: 'job-1',
      attachmentIds: ['att-1'],
      barcodeHint: '9988776655',
    })

    const wrapper = mountPage()
    await flushPromises()

    // getUploadUrl is the same builder used elsewhere (src/api/reports.ts's
    // getExportUrl pattern) — asserting against it (rather than a hardcoded
    // string) keeps this test in sync if the API base path ever changes.
    const photo = wrapper.find('img')
    expect(photo.exists()).toBe(true)
    expect(photo.attributes('src')).toBe(getUploadUrl('att-1'))
    expect(photo.attributes('src')).not.toMatch(/^blob:/)
    expect(photo.attributes('alt')).toBeTruthy()
  })

  it('shows fallback text instead of a broken image when a photo fails to load', async () => {
    const queue = useOcrConfirmQueueStore()
    queue.push({
      jobId: 'job-1',
      attachmentIds: ['att-1'],
      barcodeHint: '9988776655',
    })

    const wrapper = mountPage()
    await flushPromises()

    const photo = wrapper.find('img')
    expect(photo.exists()).toBe(true)
    await photo.trigger('error')

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('照片載入失敗')
  })

  it('lets the counter edit a prefilled field, and the edited value (not the OCR guess) is submitted', async () => {
    const queue = useOcrConfirmQueueStore()
    queue.push({
      jobId: 'job-1',
      attachmentIds: ['att-1'],
      barcodeHint: null,
    })

    const wrapper = mountPage()
    await flushPromises()

    // Fill in the one field the OCR prompt never produces (04 §3: mail_type
    // is not extracted) so validation passes, then correct the OCR's
    // sender-name guess.
    await wrapper.findAll('select')[0].setValue('parcel')
    const senderNameInput = wrapper.findAll('input')[1]
    await senderNameInput.setValue('更正後的寄件人')

    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createItem).toHaveBeenCalledWith(
      expect.objectContaining({
        mail_type: 'parcel',
        sender_name: '更正後的寄件人',
        recipient_name_raw: '陳小華',
        ocr_job_id: 'job-1',
        attachment_ids: ['att-1'],
      }),
    )
    expect(wrapper.text()).toContain('IN-20260711-0001')
    // Confirming advances the queue — nothing left to confirm.
    expect(queue.remaining).toBe(0)
  })

  it('shows the empty state and a link back to the photo page when the confirm queue is empty', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('目前沒有待確認的辨識結果')
    expect(wrapper.findComponent({ name: 'RouterLink' }).exists() || wrapper.find('a').exists()).toBe(
      true,
    )
  })
})
