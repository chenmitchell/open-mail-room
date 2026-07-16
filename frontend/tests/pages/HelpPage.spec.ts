import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import HelpPage from '@/pages/HelpPage.vue'
import type { UserRole } from '@/types/api'

// M6-HELP: /help renders common sections for every role, plus additive
// role-specific blocks -- admin is a superset of counter (RBAC 01 §1: admin
// can reach every counter-only page), so admin should see the counter
// walkthrough *and* the admin-only material, not just the latter.
function mountHelp(role: UserRole) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { id: 'u1', display_name: '王小明', email: 'a@b.com', role }
  return mount(HelpPage, { global: { plugins: [i18n, pinia] } })
}

describe('HelpPage', () => {
  it('always renders the common sections (系統簡介/登入登出/我的郵件) regardless of role', () => {
    const wrapper = mountHelp('viewer')
    expect(wrapper.text()).toContain('系統簡介')
    expect(wrapper.text()).toContain('如何登入/登出')
    expect(wrapper.text()).toContain('如何看自己的郵件')
  })

  it('employee: shows the employee block, not the counter or admin blocks', () => {
    const wrapper = mountHelp('employee')

    expect(wrapper.text()).toContain('一般員工')
    expect(wrapper.text()).toContain('綁定通知(LINE/Email…)')
    expect(wrapper.text()).toContain('取件碼怎麼用')

    expect(wrapper.text()).not.toContain('收件登記(手動/拍照/批次)')
    expect(wrapper.text()).not.toContain('員工名錄管理與 CSV 匯入')
  })

  it('counter: shows the counter block, not the employee-only or admin-only blocks', () => {
    const wrapper = mountHelp('counter')

    expect(wrapper.text()).toContain('櫃台')
    expect(wrapper.text()).toContain('收件登記(手動/拍照/批次)')
    expect(wrapper.text()).toContain('OCR 確認')
    expect(wrapper.text()).toContain('領取核銷')
    expect(wrapper.text()).toContain('交寄')

    expect(wrapper.text()).not.toContain('取件碼怎麼用')
    expect(wrapper.text()).not.toContain('員工名錄管理與 CSV 匯入')
  })

  it('admin: shows both the counter block and the admin-only block (RBAC superset)', () => {
    const wrapper = mountHelp('admin')

    expect(wrapper.text()).toContain('收件登記(手動/拍照/批次)')
    expect(wrapper.text()).toContain('員工名錄管理與 CSV 匯入')
    expect(wrapper.text()).toContain('AI 設定')
    expect(wrapper.text()).toContain('通知 Webhook')
    expect(wrapper.text()).toContain('稽核紀錄')
    expect(wrapper.text()).toContain('保存期限')

    expect(wrapper.text()).not.toContain('取件碼怎麼用')
  })

  it('viewer: shows only the read-only note, none of the other role blocks', () => {
    const wrapper = mountHelp('viewer')

    expect(wrapper.text()).toContain('唯讀權限說明')
    expect(wrapper.text()).not.toContain('收件登記(手動/拍照/批次)')
    expect(wrapper.text()).not.toContain('取件碼怎麼用')
    expect(wrapper.text()).not.toContain('員工名錄管理與 CSV 匯入')
  })

  it('gives each section an anchor id matching its table-of-contents link', () => {
    const wrapper = mountHelp('employee')
    const link = wrapper.findAll('a').find((a) => a.text() === '取件碼怎麼用')
    expect(link).toBeTruthy()
    expect(link!.attributes('href')).toBe('#help-employee-pickup-code')
    expect(wrapper.find('#help-employee-pickup-code').exists()).toBe(true)
  })
})
