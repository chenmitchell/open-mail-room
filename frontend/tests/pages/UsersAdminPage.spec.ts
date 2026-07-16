import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { DOMWrapper } from '@vue/test-utils'
import { i18n } from '@/i18n'

// M7-FE task brief: admin 開帳號給其他人並設角色 — list/filter/create/edit/
// deactivate(LAST_ADMIN guard)/reset-password.
vi.mock('@/api/users', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetUserPassword: vi.fn(),
}))
import { createUser, listUsers, resetUserPassword, updateUser } from '@/api/users'
import { ApiError } from '@/api/client'
import UsersAdminPage from '@/pages/admin/UsersAdminPage.vue'
import type { AdminUser } from '@/types/api'

function user(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 'u1',
    email: 'admin@example.com',
    display_name: '王小明',
    role: 'admin',
    is_active: true,
    last_login_at: null,
    employee_id: null,
    employee_name: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  }
}

function mountPage() {
  return mount(UsersAdminPage, { global: { plugins: [i18n] }, attachTo: document.body })
}

// The page's own filter row (search text input + role/status <select>s) is
// mounted in the same document.body as the Teleported AppDialog once a
// dialog is open, and shares generic selectors (input[type="text"],
// <select>, <form>) with the dialog's own fields -- every dialog-field
// lookup below is scoped to `.app-dialog` to avoid hitting the filter row
// instead of the dialog.
function dialog() {
  return new DOMWrapper(document.body).find('.app-dialog')
}

describe('UsersAdminPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('lists existing users with role/status badges', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [user()], meta: { total: 1, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('admin@example.com')
    expect(wrapper.text()).toContain('王小明')
    expect(wrapper.text()).toContain('管理員')
    expect(wrapper.text()).toContain('啟用')
    wrapper.unmount()
  })

  it('shows the empty state when there are no users', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('尚無使用者資料')
    wrapper.unmount()
  })

  it('validates the create form before submitting', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    const wrapper = mountPage()
    await flushPromises()

    const addButton = wrapper.findAll('button').find((b) => b.text() === '新增使用者')
    await addButton?.trigger('click')
    await flushPromises()

    await dialog().find('form').trigger('submit.prevent')
    await flushPromises()

    const body = dialog()
    expect(body.text()).toContain('請輸入 Email')
    expect(body.text()).toContain('請輸入顯示名稱')
    expect(body.text()).toContain('請選擇角色')
    expect(body.text()).toContain('請輸入密碼')
    expect(createUser).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows a friendly EMAIL_EXISTS error from the backend on create', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    vi.mocked(createUser).mockRejectedValue(new ApiError('EMAIL_EXISTS', 'email exists', 409))

    const wrapper = mountPage()
    await flushPromises()

    const addButton = wrapper.findAll('button').find((b) => b.text() === '新增使用者')
    await addButton?.trigger('click')
    await flushPromises()

    await dialog().find('input[type="email"]').setValue('dup@example.com')
    await dialog().find('input[type="text"]').setValue('新使用者')
    await dialog().find('select').setValue('counter')
    await dialog().find('input[type="password"]').setValue('longenoughpassword')
    await dialog().find('form').trigger('submit.prevent')
    await flushPromises()

    expect(dialog().text()).toContain('此 Email 已被使用')
    wrapper.unmount()
  })

  it('shows a friendly WEAK_PASSWORD error from the backend on create', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    vi.mocked(createUser).mockRejectedValue(new ApiError('WEAK_PASSWORD', 'weak password', 400))

    const wrapper = mountPage()
    await flushPromises()

    const addButton = wrapper.findAll('button').find((b) => b.text() === '新增使用者')
    await addButton?.trigger('click')
    await flushPromises()

    await dialog().find('input[type="email"]').setValue('ok@example.com')
    await dialog().find('input[type="text"]').setValue('新使用者')
    await dialog().find('select').setValue('counter')
    await dialog().find('input[type="password"]').setValue('short12345')
    await dialog().find('form').trigger('submit.prevent')
    await flushPromises()

    expect(dialog().text()).toContain('密碼長度至少需 10 個字元')
    wrapper.unmount()
  })

  it('creates a user with the submitted payload', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
    vi.mocked(createUser).mockResolvedValue(user({ email: 'ok@example.com' }))

    const wrapper = mountPage()
    await flushPromises()

    const addButton = wrapper.findAll('button').find((b) => b.text() === '新增使用者')
    await addButton?.trigger('click')
    await flushPromises()

    await dialog().find('input[type="email"]').setValue('ok@example.com')
    await dialog().find('input[type="text"]').setValue('新使用者')
    await dialog().find('select').setValue('counter')
    await dialog().find('input[type="password"]').setValue('longenoughpassword')
    await dialog().find('form').trigger('submit.prevent')
    await flushPromises()

    expect(createUser).toHaveBeenCalledWith(
      expect.objectContaining({
        email: 'ok@example.com',
        display_name: '新使用者',
        role: 'counter',
        password: 'longenoughpassword',
      }),
    )
    wrapper.unmount()
  })

  it('edit dialog keeps email read-only and lets role/status/display name be changed', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [user()], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(updateUser).mockResolvedValue(user({ display_name: '王大明' }))

    const wrapper = mountPage()
    await flushPromises()

    const editButton = wrapper.findAll('button').find((b) => b.text() === '編輯')
    await editButton?.trigger('click')
    await flushPromises()

    // email is rendered read-only (no editable email input inside the dialog)
    expect(dialog().find('input[type="email"]').exists()).toBe(false)
    expect(dialog().text()).toContain('admin@example.com')

    // displayName is the first text input in the edit dialog (email is a
    // read-only <span>, not an <input>); employeeId is the second.
    await dialog().findAll('input[type="text"]')[0].setValue('王大明')
    await dialog().find('form').trigger('submit.prevent')
    await flushPromises()

    expect(updateUser).toHaveBeenCalledWith(
      'u1',
      expect.objectContaining({ display_name: '王大明', role: 'admin', is_active: true }),
    )
    wrapper.unmount()
  })

  it('deactivating a user requires confirmation and shows a friendly LAST_ADMIN error', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [user()], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(updateUser).mockRejectedValue(new ApiError('LAST_ADMIN', 'last admin', 400))

    const wrapper = mountPage()
    await flushPromises()

    const deactivateButton = wrapper.findAll('button').find((b) => b.text() === '停用')
    await deactivateButton?.trigger('click')
    await flushPromises()

    expect(dialog().text()).toContain('確定要停用')
    expect(updateUser).not.toHaveBeenCalled()

    const confirmButton = dialog()
      .findAll('button')
      .find((b) => b.text() === '停用' && b.classes().some((c) => c.includes('danger')))
    await confirmButton?.trigger('click')
    await flushPromises()

    expect(updateUser).toHaveBeenCalledWith('u1', { is_active: false })
    expect(new DOMWrapper(document.body).text()).toContain('不能停用或降級最後一位管理員')
    wrapper.unmount()
  })

  it('activating a user does not require confirmation', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [user({ is_active: false })], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(updateUser).mockResolvedValue(user({ is_active: true }))

    const wrapper = mountPage()
    await flushPromises()

    const activateButton = wrapper.findAll('button').find((b) => b.text() === '啟用')
    await activateButton?.trigger('click')
    await flushPromises()

    expect(updateUser).toHaveBeenCalledWith('u1', { is_active: true })
    wrapper.unmount()
  })

  it('resets a password and shows a success message', async () => {
    vi.mocked(listUsers).mockResolvedValue({ items: [user()], meta: { total: 1, page: 1, size: 20 } })
    vi.mocked(resetUserPassword).mockResolvedValue({ ok: true })

    const wrapper = mountPage()
    await flushPromises()

    const resetButton = wrapper.findAll('button').find((b) => b.text() === '重設密碼')
    await resetButton?.trigger('click')
    await flushPromises()

    await dialog().find('input[type="password"]').setValue('brandnewpassword')
    // Scope to the dialog footer -- the row action button has the same
    // "重設密碼" label as the dialog's submit button.
    const submitButton = dialog()
      .find('.app-dialog__footer')
      .findAll('button')
      .find((b) => b.text() === '重設密碼')
    await submitButton?.trigger('click')
    await flushPromises()

    expect(resetUserPassword).toHaveBeenCalledWith('u1', { new_password: 'brandnewpassword' })
    expect(wrapper.text()).toContain('已重設「admin@example.com」的密碼')
    wrapper.unmount()
  })
})
