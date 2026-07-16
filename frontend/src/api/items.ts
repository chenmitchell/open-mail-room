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

export function forwardItem(id: string): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/forward`)
}

export function notifyItem(id: string): Promise<MailItem> {
  return apiClient.post<MailItem>(`/items/${id}/notify`)
}
