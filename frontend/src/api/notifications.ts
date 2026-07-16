// ASSUMPTION (see src/types/api.ts `NotificationRecord`): 03-API-SPEC.md §2
// doesn't enumerate a `GET /notifications` list endpoint (only
// `POST /items/{id}/notify` for manual resend). 05 §5 "失敗...dead 狀態進
// 「通知失敗」清單,櫃台可見並手動處理" requires a way to list them though,
// so this mirrors the standard paginated-list convention (`GET /items`,
// `GET /employees`) against an inferred `/notifications` collection, filtered
// to `status=dead` by the 通知失敗清單 page. Resending reuses the already
// -documented `notifyItem` (src/api/items.ts, `POST /items/{id}/notify`).
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type { NotificationRecord, NotificationRecordStatus } from '@/types/api'

export interface NotificationsQuery {
  status?: NotificationRecordStatus
  page?: number
  size?: number
}

export function listNotifications(query: NotificationsQuery = {}): Promise<ListResult<NotificationRecord>> {
  return apiClient.getList<NotificationRecord>(`/notifications${toQueryString(query)}`)
}
