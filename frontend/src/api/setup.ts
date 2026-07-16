// SETUP-WIZARD: first-run "create the initial administrator" endpoints
// (backend/app/api/v1/setup.py). Both are reachable with no session --
// GET /setup/status is a plain read, and POST /setup is exempt from CSRF
// the same way POST /auth/login is (see client.ts's SAFE_METHODS handling
// -- a missing csrf_token cookie at this point in the app's life just means
// no X-CSRF-Token header gets attached, which the backend expects here).
import { apiClient } from './client'

export interface SetupStatus {
  needs_setup: boolean
}

export function getSetupStatus(): Promise<SetupStatus> {
  return apiClient.get<SetupStatus>('/setup/status')
}

export interface SetupCreateAdminPayload {
  email: string
  display_name: string
  password: string
}

export interface SetupCreateAdminResult {
  ok: boolean
}

export function createInitialAdmin(
  payload: SetupCreateAdminPayload,
): Promise<SetupCreateAdminResult> {
  return apiClient.post<SetupCreateAdminResult>('/setup', payload)
}
