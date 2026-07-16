// M7-FE — admin 使用者管理 + 自助改密碼. Backend contract (already live):
// GET /admin/users?page=&size=&q=&role=&is_active= (paginated envelope),
// POST /admin/users, PATCH /admin/users/{id},
// POST /admin/users/{id}/reset-password, POST /me/password.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type {
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  AdminUsersQuery,
  ChangeMyPasswordPayload,
  ResetPasswordPayload,
} from '@/types/api'

export function listUsers(query: AdminUsersQuery = {}): Promise<ListResult<AdminUser>> {
  return apiClient.getList<AdminUser>(`/admin/users${toQueryString(query)}`)
}

export function createUser(payload: AdminUserCreatePayload): Promise<AdminUser> {
  return apiClient.post<AdminUser>('/admin/users', payload)
}

export function updateUser(id: string, payload: AdminUserUpdatePayload): Promise<AdminUser> {
  return apiClient.patch<AdminUser>(`/admin/users/${id}`, payload)
}

export function resetUserPassword(id: string, payload: ResetPasswordPayload): Promise<{ ok: boolean }> {
  return apiClient.post<{ ok: boolean }>(`/admin/users/${id}/reset-password`, payload)
}

// Self-service password change — available to every authenticated role, not
// just admins (contract: POST /me/password).
export function changeMyPassword(payload: ChangeMyPasswordPayload): Promise<{ ok: boolean }> {
  return apiClient.post<{ ok: boolean }>('/me/password', payload)
}
