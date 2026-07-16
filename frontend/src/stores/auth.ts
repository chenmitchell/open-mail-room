import { defineStore } from 'pinia'
import { apiClient, ApiError, onUnauthorized } from '@/api/client'
import { useOfflineQueueStore } from '@/stores/offlineQueue'
import type { AuthUser } from '@/types/api'

// M2-R1 suggestion (adopted): the offline capture queue (src/offline/queue.ts)
// stores captured photos + typed-in fields un-encrypted in IndexedDB. Clearing
// it whenever a session ends (explicit logout, or the API client's own 401
// auto-logout) bounds a shared/kiosk device's exposure window -- see
// stores/offlineQueue.ts#clearOnLogout for the full rationale. Never allowed
// to throw: it's wrapped there specifically so it can be fired-and-forgotten.
function clearOfflineQueueOnSessionEnd(): void {
  void useOfflineQueueStore().clearOnLogout()
}

interface AuthState {
  user: AuthUser | null
  status: 'idle' | 'loading' | 'ready' | 'error'
  error: string | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    status: 'idle',
    error: null,
  }),

  getters: {
    isAuthenticated: (state) => state.user !== null,
    role: (state) => state.user?.role ?? null,
  },

  actions: {
    // 03-API-SPEC.md §1: POST /auth/login sets an HttpOnly session cookie.
    // `data` is the logged-in user (AuthUser), matching what GET /auth/me
    // returns.
    //
    // M4-02 bug fix: this previously sent `{ username, password }`, but
    // backend/app/api/v1/auth.py `LoginRequest` is `{ email, password }`
    // (validated as an email shape server-side) — every login attempt 422'd.
    // Renamed the parameter to `email` end-to-end (see LoginPage.vue) so the
    // mismatch can't silently come back.
    async login(email: string, password: string): Promise<void> {
      this.status = 'loading'
      this.error = null
      try {
        const user = await apiClient.post<AuthUser>(
          '/auth/login',
          { email, password },
          { skipAuthRedirect: true },
        )
        this.user = user
        this.status = 'ready'
      } catch (err) {
        this.user = null
        this.status = 'error'
        // POLISH-AUDIT.md Should-fix #12: this used to hardcode the zh-TW
        // string here, bypassing i18n entirely for an en-locale session.
        // `auth.loginGenericError` already exists in both locale files (see
        // LoginPage.vue, which independently derives the same copy from
        // ApiError.status rather than reading this field) -- store the i18n
        // *key* so any future consumer of `store.error` can translate it,
        // instead of baking in one language's text.
        this.error = err instanceof ApiError ? err.message : 'auth.loginGenericError'
        throw err
      }
    },

    // ASSUMPTION: POST /auth/logout and GET /auth/me are not enumerated in
    // 03-API-SPEC.md §2 (only POST /auth/login is listed). Both are inferred
    // as standard companions to the login endpoint — confirm with backend
    // (A 組) before/while M1 wires up the real auth endpoints.
    async logout(): Promise<void> {
      try {
        await apiClient.post<void>('/auth/logout', undefined, { skipAuthRedirect: true })
      } finally {
        this.user = null
        this.status = 'idle'
        clearOfflineQueueOnSessionEnd()
      }
    },

    async fetchMe(): Promise<void> {
      this.status = 'loading'
      try {
        const user = await apiClient.get<AuthUser>('/auth/me', { skipAuthRedirect: true })
        this.user = user
        this.status = 'ready'
      } catch {
        this.user = null
        this.status = 'idle'
      }
    },
  },
})

/**
 * Wires the API client's 401 handler to the auth store + a caller-supplied
 * redirect (typically router.push to the login page). Call once from
 * main.ts, after both pinia and the router have been installed.
 */
export function registerAuthRedirect(onUnauthorizedRedirect: () => void): void {
  onUnauthorized(() => {
    const store = useAuthStore()
    store.user = null
    store.status = 'idle'
    clearOfflineQueueOnSessionEnd()
    onUnauthorizedRedirect()
  })
}
