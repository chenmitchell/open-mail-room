/// <reference types="vitest" />
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import yaml from 'js-yaml'

interface Branding {
  app_name: string
  company_name?: string
  primary_color: string
  locale: string
  pickup_location?: string
  retention_years?: number
  // 06-UI-UX.md §4 "套版設定檔": feature toggles for optional item fields.
  // M1-03 (frontend) reads these at BUILD time (see `define: __BRANDING__`
  // below) rather than via a runtime API call, because 03-API-SPEC.md does
  // not enumerate an endpoint that serves branding.yaml to the browser —
  // only `GET|PUT /admin/settings` exists and that is admin-scoped, not
  // reachable by the `counter` role that fills in the inbound form. This
  // mirrors the existing pattern already used for app_name/primary_color
  // above. ASSUMPTION (flag for reviewer/backend): if an admin ever needs to
  // toggle features without a container restart, a public `GET /config`
  // (or similar) endpoint should be added and this should switch to reading
  // it at runtime instead.
  features?: Record<string, boolean>
}

const DEFAULT_BRANDING: Branding = {
  app_name: 'Open Mail Room',
  company_name: 'Open Mail Room',
  primary_color: '#0072B2',
  locale: 'zh-TW',
  pickup_location: '一樓櫃台',
  retention_years: 5,
  features: {
    outbound: true,
    cod: true,
    refrigeration: true,
    confidential: true,
  },
}

const rootDir = fileURLToPath(new URL('.', import.meta.url))

/**
 * config/branding.yaml lives one level above frontend/ (see docs/plan/06-UI-UX.md §4).
 * It is the only file open-source operators are expected to touch, and it may not
 * exist yet (e.g. a fresh checkout before ops has configured it) — fall back to
 * sane defaults so `npm run build` never fails because of a missing/invalid file.
 */
function loadBranding(): Branding {
  const brandingPath = resolve(rootDir, '../config/branding.yaml')
  if (!existsSync(brandingPath)) {
    return DEFAULT_BRANDING
  }
  try {
    const raw = readFileSync(brandingPath, 'utf-8')
    const parsed = yaml.load(raw) as Partial<Branding> | undefined
    return { ...DEFAULT_BRANDING, ...parsed }
  } catch (err) {
    console.warn('[vite.config] failed to parse config/branding.yaml, using defaults:', err)
    return DEFAULT_BRANDING
  }
}

const branding = loadBranding()

export default defineConfig({
  define: {
    // Frozen at build/dev-server-start time; see `Branding.features` comment
    // above for why this is build-time rather than a runtime fetch. Declared
    // in src/env.d.ts. Restarting `vite`/`vite build` re-reads branding.yaml,
    // matching 06 §4 "改完 restart 即生效".
    __BRANDING__: JSON.stringify(branding),
    // CSP-I18N fix: vue-i18n's runtime-only build only registers its
    // (eval-free) AST message compiler -- `compile()` in
    // @intlify/core-base, which evaluates precompiled/JIT-compiled
    // messages via a plain tree-walking interpreter, never `new Function`
    // -- when this flag is true. Left at its default (false), the
    // runtime-only build registers *no* message compiler at all, so
    // `t()` returns the raw precompiled message-AST object instead of a
    // string ("Unexpected return type in composer"). This is unrelated to
    // (and does not reintroduce) the eval-based `compileToFunction`
    // compiler that the *full* vue-i18n build falls back to when this
    // flag is false -- that eval path is excluded entirely by the
    // `vue-i18n` resolve.alias below pinning the runtime-only bundle.
    __INTLIFY_JIT_COMPILATION__: true,
  },
  plugins: [
    vue(),
    // CSP-I18N fix: default-src 'self' (see backend/app/main.py
    // SECURITY_HEADERS) forbids 'unsafe-eval', but vue-i18n's runtime
    // message compiler uses `new Function` to compile ICU-style message
    // strings at runtime, which throws EvalError under that CSP and blanks
    // the whole SPA. This plugin precompiles src/locales/*.json into plain
    // JS functions at build time, so the runtime-only vue-i18n build (no
    // `new Function` compiler) is all that ships -- see also the
    // `vue-i18n` resolve.alias below, which points at that runtime-only
    // bundle.
    VueI18nPlugin({
      include: [resolve(rootDir, 'src/locales/**')],
      runtimeOnly: true,
      compositionOnly: true,
    }),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icons/*.svg'],
      manifest: {
        name: branding.app_name,
        short_name: branding.app_name,
        description: `${branding.company_name ?? branding.app_name} 收發室管理系統`,
        theme_color: branding.primary_color,
        background_color: '#FFFFFF',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        lang: branding.locale,
        icons: [
          { src: '/icons/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/icons/maskable-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        // FE-STABILITY: explicit (rather than relying solely on
        // registerType:'autoUpdate' implicitly wiring these up) so a new
        // service worker takes over immediately on activation and every open
        // tab is claimed right away -- a reload always gets the latest
        // front-end bundle instead of a stale cached one.
        clientsClaim: true,
        skipWaiting: true,
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,svg,ico,woff2}'],
        additionalManifestEntries: [{ url: '/offline.html', revision: null }],
        runtimeCaching: [
          {
            // Navigations (full page loads / SPA route entries): try network first
            // so users always get the freshest shell, fall back to the offline
            // page when there is no network and nothing cached yet.
            urlPattern: ({ request }) => request.mode === 'navigate',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'oi-pages',
              networkTimeoutSeconds: 3,
              plugins: [
                {
                  handlerDidError: async () => caches.match('/offline.html'),
                },
              ],
            },
          },
          {
            // API calls must never be served from cache — offline write queueing
            // for inbound/outbound forms is handled at the IndexedDB layer in M2,
            // not by the service worker.
            urlPattern: /^\/api\//,
            handler: 'NetworkOnly',
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // CSP-I18N fix (see VueI18nPlugin above): force the runtime-only
      // vue-i18n build so the full build (which bundles the `new
      // Function`-based message compiler, disallowed under our
      // `default-src 'self'` CSP with no 'unsafe-eval') never ends up in
      // the client bundle even transitively.
      'vue-i18n': 'vue-i18n/dist/vue-i18n.runtime.esm-bundler.js',
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
    setupFiles: ['./tests/setup.ts'],
  },
})
