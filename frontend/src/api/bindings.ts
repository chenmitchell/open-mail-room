// 03-API-SPEC.md §2 「通知綁定(員工自助)」endpoints, 05-NOTIFICATIONS.md §3.
import { apiClient } from './client'
import type {
  BindingStartResult,
  CreateBindingPayload,
  NotificationBinding,
  NotificationChannel,
  TelegramBindingStartResult,
} from '@/types/api'

export function listMyBindings(): Promise<NotificationBinding[]> {
  return apiClient.get<NotificationBinding[]>('/me/bindings')
}

// 05 §3 步驟 1: 產生 6 位綁定碼(10 分鐘有效);員工加 LINE 官方帳號好友後傳送
// 綁定碼,webhook 收到後完成綁定 — see src/notifications/pollBinding.ts for
// how the wizard detects completion.
export function startLineBinding(): Promise<BindingStartResult> {
  return apiClient.post<BindingStartResult>('/me/bindings/line/start')
}

// ASSUMPTION: mirrors `startLineBinding` 1:1 per 05 §3 point 4 "Telegram 同理
// (deep link t.me/bot?start=<code> 更簡單)" — 03 §2 doesn't spell out a
// telegram-specific start endpoint the way it does for line, so this is
// inferred symmetric to it pending backend M3-01 confirmation.
export function startTelegramBinding(): Promise<TelegramBindingStartResult> {
  return apiClient.post<TelegramBindingStartResult>('/me/bindings/telegram/start')
}

// Direct-entry channels (email/slack/discord/webhook — 05 §2 adapter table)
// skip the code wizard and bind an address straight away.
export function createBinding(
  channel: NotificationChannel,
  payload: CreateBindingPayload,
): Promise<NotificationBinding> {
  return apiClient.post<NotificationBinding>(`/me/bindings/${channel}`, payload)
}

export function deleteBinding(id: string): Promise<void> {
  return apiClient.delete<void>(`/me/bindings/${id}`)
}
