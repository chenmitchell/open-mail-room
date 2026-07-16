// 03-API-SPEC.md §2 `GET /admin/audit-logs`.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type { AuditLogEntry, AuditLogsQuery } from '@/types/api'

export function listAuditLogs(query: AuditLogsQuery = {}): Promise<ListResult<AuditLogEntry>> {
  return apiClient.getList<AuditLogEntry>(`/admin/audit-logs${toQueryString(query)}`)
}
