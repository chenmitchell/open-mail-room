// SETUP-WIZARD: shared "does the app still need first-run setup" state for
// the router guard (src/router/index.ts). Split into its own module so:
//   1. It can be unit tested without mounting the router/pinia/i18n.
//   2. SetupPage.vue can call `markSetupComplete()` right after a
//      successful POST /setup, so the very next navigation (to /login)
//      doesn't have to make (and wait on) a redundant GET /setup/status
//      round-trip that would just repeat what the POST already told us.
import { getSetupStatus } from '@/api/setup'

let cache: boolean | null = null
let pending: Promise<boolean> | null = null

/**
 * Resolves to whether the app still needs the first-run setup wizard.
 * Result is cached for the lifetime of the page load (a fresh admin is
 * only ever created once, and the cache is explicitly invalidated by
 * `markSetupComplete()` right when that happens) -- so this only ever hits
 * the network once per page load, not once per navigation. Concurrent
 * callers (e.g. the guard firing again before the first check resolves)
 * share the same in-flight request rather than each starting their own.
 */
export async function needsSetup(): Promise<boolean> {
  if (cache !== null) return cache
  if (!pending) {
    pending = getSetupStatus()
      .then((status) => {
        cache = status.needs_setup
        return cache
      })
      .catch(() => {
        // Fail-safe: if the status check itself fails (network blip, API
        // briefly unreachable), don't trap every navigation behind /setup
        // forever -- treat as "no setup needed" so the normal auth guard
        // runs. If setup genuinely is still needed, visiting /setup
        // directly still works; POST /setup itself is the real gate.
        cache = false
        return cache
      })
      .finally(() => {
        pending = null
      })
  }
  return pending
}

/** Called right after a successful `POST /setup` (SetupPage.vue) so the
 * guard's very next check reflects reality without another round-trip. */
export function markSetupComplete(): void {
  cache = false
}

/** Test helper: drop the cached/in-flight status so the next `needsSetup()`
 * call re-fetches. */
export function resetSetupStatusCache(): void {
  cache = null
  pending = null
}

/**
 * Pure decision function the router guard (src/router/index.ts) delegates
 * to, kept side-effect-free and separate from `needsSetup()`'s async
 * fetch/cache so the redirect *logic* itself (avoiding the infinite-loop
 * traps a naive "always redirect to /setup" guard would fall into) can be
 * unit tested directly.
 *
 * - needs setup, not already headed to /setup -> go to /setup.
 * - setup already done, but still headed to /setup -> bounce to /login
 *   (an operator revisiting /setup after the wizard already ran).
 * - otherwise -> no redirect (`null`), let the normal auth guard decide.
 */
export function resolveSetupRedirect(
  setupNeeded: boolean,
  currentRouteName: string | symbol | null | undefined,
): 'setup' | 'login' | null {
  if (setupNeeded) {
    return currentRouteName === 'setup' ? null : 'setup'
  }
  return currentRouteName === 'setup' ? 'login' : null
}
