import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

// task brief M9-FE 「AI 設定」頁: 狀態區/模型下拉/每日上限/儲存, 對接已上線的
// GET/PUT /admin/ai/status|models|settings 契約.
vi.mock('@/api/ai', () => ({
  getAiStatus: vi.fn(),
  getAiModels: vi.fn(),
  updateAiSettings: vi.fn(),
}))
import { getAiModels, getAiStatus, updateAiSettings } from '@/api/ai'
import { ApiError } from '@/api/client'
import AiSettingsPage from '@/pages/admin/AiSettingsPage.vue'
import type { AiStatus } from '@/types/api'

function status(overrides: Partial<AiStatus> = {}): AiStatus {
  return {
    env_key_present: true,
    provider: 'gemini',
    effective_model: 'gemini-1.5-pro',
    daily_request_limit: 10000,
    used_today: 12,
    has_db_config: true,
    ...overrides,
  }
}

function mountPage() {
  return mount(AiSettingsPage, { global: { plugins: [i18n] } })
}

describe('AiSettingsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the AI key present/provider/usage status', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status())
    vi.mocked(getAiModels).mockResolvedValue({ models: ['gemini-1.5-pro', 'gemini-1.5-flash'] })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('已設定')
    expect(wrapper.text()).toContain('gemini')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('10000')
    wrapper.unmount()
  })

  it('shows the env-var explanation when no key is configured', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status({ env_key_present: false }))
    vi.mocked(getAiModels).mockRejectedValue(new ApiError('AI_NO_KEY', 'no key', 400))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('未設定')
    expect(wrapper.text()).toContain('AI_API_KEY')
    expect(wrapper.text()).toContain('GEMINI_API_KEY')
    wrapper.unmount()
  })

  it('fills the model dropdown from getAiModels, plus an auto-detect option, with effective_model selected', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status({ effective_model: 'gemini-1.5-flash' }))
    vi.mocked(getAiModels).mockResolvedValue({ models: ['gemini-1.5-pro', 'gemini-1.5-flash'] })

    const wrapper = mountPage()
    await flushPromises()

    const select = wrapper.find('select')
    const optionValues = select.findAll('option').map((o) => o.element.value)
    expect(optionValues).toEqual(['', 'gemini-1.5-pro', 'gemini-1.5-flash'])
    expect((select.element as HTMLSelectElement).value).toBe('gemini-1.5-flash')
    wrapper.unmount()
  })

  it('shows effective_model "" as the auto-detect option selected', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status({ effective_model: '' }))
    vi.mocked(getAiModels).mockResolvedValue({ models: ['gemini-1.5-pro'] })

    const wrapper = mountPage()
    await flushPromises()

    const select = wrapper.find('select')
    expect((select.element as HTMLSelectElement).value).toBe('')
    wrapper.unmount()
  })

  it('disables the model dropdown and shows a warning on AI_NO_KEY', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status({ env_key_present: false }))
    vi.mocked(getAiModels).mockRejectedValue(new ApiError('AI_NO_KEY', 'no key', 400))

    const wrapper = mountPage()
    await flushPromises()

    const select = wrapper.find('select')
    expect(select.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('請先設定環境變數金鑰')
    wrapper.unmount()
  })

  it('shows an error but keeps the dropdown usable on AI_MODELS_UNAVAILABLE', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status())
    vi.mocked(getAiModels).mockRejectedValue(
      new ApiError('AI_MODELS_UNAVAILABLE', 'upstream timeout', 400),
    )

    const wrapper = mountPage()
    await flushPromises()

    const select = wrapper.find('select')
    expect(select.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('upstream timeout')
    // Auto-detect stays selectable even though the real model list failed.
    const optionValues = select.findAll('option').map((o) => o.element.value)
    expect(optionValues).toEqual([''])
    wrapper.unmount()
  })

  it('saves with the selected model and daily limit payload, then reloads the status', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status({ effective_model: 'gemini-1.5-pro', daily_request_limit: 10000 }))
    vi.mocked(getAiModels).mockResolvedValue({ models: ['gemini-1.5-pro', 'gemini-1.5-flash'] })
    vi.mocked(updateAiSettings).mockResolvedValue(
      status({ effective_model: 'gemini-1.5-flash', daily_request_limit: 500 }),
    )

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('select').setValue('gemini-1.5-flash')
    await wrapper.find('input[type="number"]').setValue('500')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(updateAiSettings).toHaveBeenCalledWith({ model: 'gemini-1.5-flash', daily_request_limit: 500 })
    expect(wrapper.text()).toContain('設定已儲存')
    wrapper.unmount()
  })

  it('sends model: null when the auto-detect option is chosen', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status({ effective_model: 'gemini-1.5-pro' }))
    vi.mocked(getAiModels).mockResolvedValue({ models: ['gemini-1.5-pro'] })
    vi.mocked(updateAiSettings).mockResolvedValue(status({ effective_model: '' }))

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('select').setValue('')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(updateAiSettings).toHaveBeenCalledWith(
      expect.objectContaining({ model: null }),
    )
    wrapper.unmount()
  })

  it('validates the daily limit is between 1 and 100000 before saving', async () => {
    vi.mocked(getAiStatus).mockResolvedValue(status())
    vi.mocked(getAiModels).mockResolvedValue({ models: ['gemini-1.5-pro'] })

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('input[type="number"]').setValue('0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('請輸入 1 到 100000 之間的整數')
    expect(updateAiSettings).not.toHaveBeenCalled()

    await wrapper.find('input[type="number"]').setValue('100001')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(updateAiSettings).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows a load error state when getAiStatus fails', async () => {
    vi.mocked(getAiStatus).mockRejectedValue(new ApiError('SERVER_ERROR', 'boom', 500))
    vi.mocked(getAiModels).mockResolvedValue({ models: [] })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('boom')
    wrapper.unmount()
  })
})
