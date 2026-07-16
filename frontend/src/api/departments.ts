// 03-API-SPEC.md §2 「名錄與部門」endpoints.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type { Department, DepartmentCreatePayload, DepartmentUpdatePayload } from '@/types/api'

export function listDepartments(
  query: { q?: string; is_active?: boolean } = {},
): Promise<ListResult<Department>> {
  return apiClient.getList<Department>(`/departments${toQueryString(query)}`)
}

export function createDepartment(payload: DepartmentCreatePayload): Promise<Department> {
  return apiClient.post<Department>('/departments', payload)
}

export function updateDepartment(
  id: string,
  payload: DepartmentUpdatePayload,
): Promise<Department> {
  return apiClient.patch<Department>(`/departments/${id}`, payload)
}
