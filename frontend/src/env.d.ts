/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

// Injected by vite.config.ts `define` from config/branding.yaml (see
// src/branding.ts for the typed accessor). See the ASSUMPTION note next to
// the `Branding` interface in vite.config.ts for why this is build-time.
declare const __BRANDING__: {
  app_name: string
  company_name?: string
  primary_color: string
  locale: string
  pickup_location?: string
  retention_years?: number
  features?: Record<string, boolean>
}
