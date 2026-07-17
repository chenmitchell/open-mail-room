// 03-API-SPEC.md §2 「收件」endpoints.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type { CreateMailItemPayload, ItemsQuery, MailItem, PickupPayload } from '@/types/api'

export function listItems(query: ItemsQuery = {}): Promise<ListResult<MailItem>> {
  return apiClient.getList<MailItem>(`/items${toQueryString(query)}`)
}

export function getItem(id: string): Promise<MailItem> {
  return apiClient.get<MailItem>(`/items/${id}`)
}

export function createItem(payload: CreateMailItemPayload): Promise<MailItem> {
  return apiClient.post<MailItem>('/items', payload)
}

export function pickupItem(id: string, payload: PickupPayload): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/pickup`, payload)
}

export function returnItem(id: string): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/return`)
}

/**
 * 作廢一筆登記錯的件(重複登記、拍錯照、按錯送出)。
 *
 * `reason` 是後端必填的:作廢是唯一一個「這筆紀錄是個錯誤」的轉換,
 * 沒有理由的話稽核只會記到「有人把某筆抹掉了」而不知道為什麼 —— 那比
 * 沒有這個功能更糟。已領取的件不能作廢(那個簽名記錄的是真的發生過的事)。
 */
export function voidItem(id: string, reason: string): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/void`, { reason })
}

export function forwardItem(id: string): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/forward`)
}

export function notifyItem(id: string): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/notify`)
}
