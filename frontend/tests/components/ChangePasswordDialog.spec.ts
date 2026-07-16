import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { DOMWrapper } from '@vue/test-utils'
import { i18n } from '@/i18n'

// M7-FE task brief: self-service password change, available to every
// authenticated role (see AppShell.vue's nav entry).
vi.mock('@/api/users', () => ({ changeMyPassword: vi.fn() }))
import { changeMyPassword } from '@/api/users'
import { ApiError } from '@/api/client'
import ChangePasswordDialog from '@/components/ChangePasswordDialog.vue'

function mountDialog(open = true) {
  return mount(ChangePasswordDialog, {
    props: { open },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
}

describe('ChangePasswordDialog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('validates required fields before submitting', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const body = new DOMWrapper(document.body)
    await body.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(body.text()).toContain('請輸入目前密碼')
    expect(body.text()).toContain('密碼長度至少需 10 個字元')
    expect(changeMyPassword).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('submits current + new password and shows a success message', async () => {
    vi.mocked(changeMyPassword).mockResolvedValue({ ok: true })
    const wrapper = mountDialog()
    await flushPromises()

    const body = new DOMWrapper(document.body)
    const inputs = body.findAll('input[type="password"]')
    await inputs[0].setValue('oldpassword')
    await inputs[1].setValue('brandnewpassword')
    await body.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(changeMyPassword).toHaveBeenCalledWith({
      current_password: 'oldpassword',
      new_password: 'brandnewpassword',
    })
    expect(body.text()).toContain('密碼已修改成功')
    wrapper.unmount()
  })

  it('shows a friendly CURRENT_PASSWORD_INVALID error', async () => {
    vi.mocked(changeMyPassword).mockRejectedValue(new ApiError('CURRENT_PASSWORD_INVALID', 'nope', 400))
    const wrapper = mountDialog()
    await flushPromises()

    const body = new DOMWrapper(document.body)
    const inputs = body.findAll('input[type="password"]')
    await inputs[0].setValue('wrongpassword')
    await inputs[1].setValue('brandnewpassword')
    await body.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(body.text()).toContain('目前密碼不正確')
    wrapper.unmount()
  })

  it('resets its fields each time it is re-opened', async () => {
    vi.mocked(changeMyPassword).mockResolvedValue({ ok: true })
    const wrapper = mountDialog(false)
    await wrapper.setProps({ open: true })
    await flushPromises()

    const body = new DOMWrapper(document.body)
    const inputs = body.findAll('input[type="password"]')
    await inputs[0].setValue('oldpassword')
    await inputs[1].setValue('brandnewpassword')
    await body.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(body.text()).toContain('密碼已修改成功')

    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    await flushPromises()

    expect(body.text()).not.toContain('密碼已修改成功')
    const reopenedInputs = body.findAll('input[type="password"]')
    expect((reopenedInputs[0].element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })
})
