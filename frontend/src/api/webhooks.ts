// 03-API-SPEC.md §2 「管理」`GET|POST|PATCH /admin/webhooks`,
// `POST /admin/webhooks/{id}/test`. 02 `webhook_endpoints` / 03 §3 對外 webhook.
import { apiClient, type ListResult } from './client'
import type {
  WebhookEndpoint,
  WebhookEndpointCreated,
  WebhookEndpointPayload,
  WebhookTestResult,
} from '@/types/api'

export function listWebhooks(): Promise<ListResult<WebhookEndpoint>> {
  return apiClient.getList<WebhookEndpoint>('/admin/webhooks')
}

// ASSUMPTION: response includes the raw HMAC `secret` once — see
// `WebhookEndpointCreated` in src/types/api.ts for the rationale.
export function createWebhook(payload: WebhookEndpointPayload): Promise<WebhookEndpointCreated> {
  return apiClient.post<WebhookEndpointCreated>('/admin/webhooks', payload)
}

export function updateWebhook(
  id: string,
  payload: Partial<WebhookEndpointPayload>,
): Promise<WebhookEndpoint> {
  return apiClient.patch<WebhookEndpoint>(`/admin/webhooks/${id}`, payload)
}

export function testWebhook(id: string): Promise<WebhookTestResult> {
  return apiClient.post<WebhookTestResult>(`/admin/webhooks/${id}/test`)
}
