import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { i18n } from '@/i18n'

vi.mock('@/api/employees', () => ({
  listEmployees: vi.fn(),
  createEmployee: vi.fn(),
  updateEmployee: vi.fn(),
  importEmployeesCsv: vi.fn(),
}))
vi.mock('@/api/departments', () => ({ listDepartments: vi.fn() }))
import { listEmployees } from '@/api/employees'
import { listDepartments } from '@/api/departments'
import EmployeesAdminPage from '@/pages/admin/EmployeesAdminPage.vue'

function mountPage() {
  vi.mocked(listEmployees).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 100 } })
  vi.mocked(listDepartments).mockResolvedValue({ items: [], meta: { total: 0, page: 1, size: 20 } })
  return mount(EmployeesAdminPage, { global: { plugins: [i18n] } })
}

// M6-HELP 範本: client-generated CSV template download (name/aliases/
// department_code/ext/email/phone columns, per help.hint.employeesCsvTemplate).
describe('EmployeesAdminPage CSV template download', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders a "下載 CSV 範本" button next to the CSV import button', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const button = wrapper.findAll('button').find((b) => b.text() === '下載 CSV 範本')
    expect(button).toBeTruthy()
  })

  it('clicking the template button builds a CSV Blob with the expected header + example rows and triggers a download', async () => {
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-template-url')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clickSpy = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') el.click = clickSpy
      return el
    })

    const wrapper = mountPage()
    await flushPromises()

    const button = wrapper.findAll('button').find((b) => b.text() === '下載 CSV 範本')
    await button!.trigger('click')

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    const blob = createObjectURLSpy.mock.calls[0][0] as Blob
    const content = await blob.text()
    expect(content).toContain('name,aliases,department_code,ext,email,phone')
    expect(content).toContain('王小明,小明;Ming,SALES,1234,ming@example.com,0912345678')
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-template-url')

    createElementSpy.mockRestore()
  })

  it('shows a HelpHint next to the template button explaining the expected CSV format', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const tooltips = wrapper.findAll('[role="tooltip"]').map((t) => t.text())
    expect(tooltips).toContain(
      'CSV 欄位需為:name(姓名)、aliases(別名,以分號分隔)、department_code(部門代碼)、ext(分機)、email、phone。下載範本依格式填寫後即可匯入。',
    )
  })
})
