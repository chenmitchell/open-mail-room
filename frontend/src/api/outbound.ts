// 03-API-SPEC.md §2 「交寄」endpoints.
import { apiClient, type ListResult } from './client'
import { toQueryString } from './queryString'
import type {
  CreateOutboundPayload,
  MarkShippedPayload,
  OutboundItem,
  OutboundQuery,
  UpdateOutboundPayload,
} from '@/types/api'

export function listOutbound(query: OutboundQuery = {}): Promise<ListResult<OutboundItem>> {
  return apiClient.getList<OutboundItem>(`/outbound${toQueryString(query)}`)
}

export function createOutbound(payload: CreateOutboundPayload): Promise<OutboundItem> {
  return apiClient.post<OutboundItem>('/outbound', payload)
}

export function updateOutbound(id: string, payload: UpdateOutboundPayload): Promise<OutboundItem> {
  return apiClient.patch<OutboundItem>(`/outbound/${id}`, payload)
}

// 03 §2 `POST /outbound/{id}/shipped { tracking_no?, attachment_id? }` —
// 01 §2.2 step 2: "交寄時拍託運單照片 → OCR 抽單號回填 → 狀態「已交寄」".
export function markOutboundShipped(id: string, payload: MarkShippedPayload): Promise<OutboundItem> {
  return apiClient.post<OutboundItem>(`/outbound/${id}/shipped`, payload)
}
