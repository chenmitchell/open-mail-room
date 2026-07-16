// M9-FE 管理員「AI 設定」頁 — 03-API-SPEC.md admin/ai:
// `GET /admin/ai/status`, `GET /admin/ai/models`, `PUT /admin/ai/settings`.
import { apiClient } from './client'
import type { AiModelsResult, AiSettingsPayload, AiStatus } from '@/types/api'

export function getAiStatus(): Promise<AiStatus> {
  return apiClient.get<AiStatus>('/admin/ai/status')
}

// Throws ApiError('AI_NO_KEY') when no env key is configured, or
// ApiError('AI_MODELS_UNAVAILABLE') when the upstream ListModels call
// failed -- both handled by the page (see AiSettingsPage.vue).
export function getAiModels(): Promise<AiModelsResult> {
  return apiClient.get<AiModelsResult>('/admin/ai/models')
}

export function updateAiSettings(payload: AiSettingsPayload): Promise<AiStatus> {
  return apiClient.put<AiStatus>('/admin/ai/settings', payload)
}
