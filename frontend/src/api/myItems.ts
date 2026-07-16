// ASSUMPTION (see src/types/api.ts `MyItemsQuery`): `GET /me/items` isn't in
// 03-API-SPEC.md §2's endpoint table, but the task brief pins this exact
// path for 06-UI-UX.md §1 「我的郵件」. Mirrors `GET /items`' paginated
// `ListResult<MailItem>` shape (src/api/items.ts), scoped server-side to the
// logged-in employee — no `recipient_employee_id` filter is sent from here.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type { MailItem, MyItemsQuery } from '@/types/api'

export function listMyItems(query: MyItemsQuery = {}): Promise<ListResult<MailItem>> {
  return apiClient.getList<MailItem>(`/me/items${toQueryString(query)}`)
}
