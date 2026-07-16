// Typed accessor for config/branding.yaml, injected at build time as
// `__BRANDING__` (see vite.config.ts `define` and src/env.d.ts). Centralised
// here so pages never touch the raw global directly.
export const branding = __BRANDING__

/**
 * 06-UI-UX.md §4 features: outbound / cod / refrigeration / confidential.
 * Unknown flags default to enabled (matches config/branding.yaml's shipped
 * defaults) so a stale/partial branding.yaml never silently hides a field
 * the operator didn't intend to disable.
 */
export function isFeatureEnabled(flag: string): boolean {
  const value = branding.features?.[flag]
  return value ?? true
}
