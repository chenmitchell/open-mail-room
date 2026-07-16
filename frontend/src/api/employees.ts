// 03-API-SPEC.md §2 「名錄與部門」endpoints.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type {
  Employee,
  EmployeeCreatePayload,
  EmployeeImportResult,
  EmployeeMatchCandidate,
  EmployeeUpdatePayload,
} from '@/types/api'

export interface EmployeesQuery {
  q?: string
  department_id?: string
  status?: 'active' | 'inactive'
  page?: number
  size?: number
}

export function listEmployees(query: EmployeesQuery = {}): Promise<ListResult<Employee>> {
  return apiClient.getList<Employee>(`/employees${toQueryString(query)}`)
}

export function createEmployee(payload: EmployeeCreatePayload): Promise<Employee> {
  return apiClient.post<Employee>('/employees', payload)
}

export function updateEmployee(id: string, payload: EmployeeUpdatePayload): Promise<Employee> {
  return apiClient.patch<Employee>(`/employees/${id}`, payload)
}

export function importEmployeesCsv(file: File): Promise<EmployeeImportResult> {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<EmployeeImportResult>('/employees/import', form)
}

// 01 §5 模糊比對: 姓名輸入即時呼叫,回候選 { employee_id, score }[]。
export function matchEmployees(q: string): Promise<EmployeeMatchCandidate[]> {
  if (!q.trim()) return Promise.resolve([])
  return apiClient.get<EmployeeMatchCandidate[]>(`/employees/match${toQueryString({ q })}`)
}
