<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { isFeatureEnabled } from '@/branding'
import AppBadge from '@/components/AppBadge.vue'
import OfflineQueueBadge from '@/components/OfflineQueueBadge.vue'
import ChangePasswordDialog from '@/components/ChangePasswordDialog.vue'
import AuthorCredit from '@/components/AuthorCredit.vue'

const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const auth = useAuthStore()

// task brief M7-FE: self-service password change, available to every
// authenticated role -- not gated by `auth.role` at all (see template).
const changePasswordOpen = ref(false)

// M6-HELP: lets the signed-in user see which of the four RBAC roles (01 §1:
// admin/counter/employee/viewer) their account has -- rendered as a small
// badge in the nav (see template) rather than only being implicit in which
// nav items/routes happen to be reachable.
const roleBadgeLabel = computed(() => (auth.role ? t(`nav.roleBadge.${auth.role}`) : null))

// Outbound/reports-charts/other admin sections land in M2-M5 per
// 08-EXECUTION-PLAN.md and should be appended here as their routes are
// built. Employees admin is gated to the admin role (mirrors the router's
// `requiresRole` guard — see router/index.ts).
interface NavItem {
  to: string
  labelKey: string
  icon: string
}

const navItems = computed<NavItem[]>(() => {
  const items: NavItem[] = [
    {
      to: '/',
      labelKey: 'nav.dashboard',
      icon: 'M4 10.5L12 4l8 6.5M6 9.5V19a1 1 0 001 1h3v-5a1 1 0 011-1h2a1 1 0 011 1v5h3a1 1 0 001-1V9.5',
    },
    {
      to: '/register',
      labelKey: 'nav.manualRegister',
      icon: 'M12 5v14M5 12h14',
    },
    {
      to: '/pickup',
      labelKey: 'nav.pickup',
      icon: 'M20 6L9 17l-5-5',
    },
    {
      // 06 §1 查詢頁 (record-level search + detail drawer).
      to: '/search',
      labelKey: 'nav.search',
      icon: 'M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35',
    },
    {
      // 06 §1 查詢/報表頁 (M4-02): 卡片+長條圖 summary, gated the same as
      // the /reports route itself (viewer/counter/admin — router/index.ts
      // `requiresRole`); showing it to an `employee` here would just dead-
      // end at the router's redirect-to-dashboard guard.
      to: '/reports',
      labelKey: 'nav.reports',
      icon: 'M4 19h16M7 19V9m5 10V5m5 14v-7',
    },
    {
      // 06 §1 「我的郵件」— shown to every authenticated role (ASSUMPTION,
      // see router/index.ts my-mail route comment).
      to: '/my-mail',
      labelKey: 'nav.myMail',
      icon: 'M4 4h16v16H4zM4 4l8 8 8-8',
    },
    {
      // 03 §2 通知綁定(員工自助) UI.
      to: '/notifications/settings',
      labelKey: 'nav.notificationSettings',
      icon: 'M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0',
    },
  ]
  // 06 §1 「交寄」頁 (M4-02): 對象 counter/employee(+admin per 01 §1「全
  // 部」). Also gated behind config/branding.yaml `features.outbound` (06
  // §4) so an operator who disabled the outbound feature doesn't see a nav
  // entry for a workflow they turned off.
  if (
    (auth.role === 'admin' || auth.role === 'counter' || auth.role === 'employee') &&
    isFeatureEnabled('outbound')
  ) {
    items.push({
      to: '/outbound',
      labelKey: 'nav.outbound',
      icon: 'M5 12h14M13 6l6 6-6 6',
    })
  }
  if (auth.role === 'admin' || auth.role === 'counter') {
    items.push({
      // task brief 「通知失敗清單」(counter/admin).
      to: '/notifications/failures',
      labelKey: 'nav.notificationFailures',
      icon: 'M12 9v4M12 17h.01M10.29 3.86L1.82 18a1 1 0 00.87 1.5h18.62a1 1 0 00.87-1.5L13.71 3.86a1 1 0 00-1.72 0z',
    })
  }
  if (auth.role === 'admin') {
    items.push({
      to: '/admin/employees',
      labelKey: 'nav.employees',
      icon: 'M17 20v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M12 11a4 4 0 100-8 4 4 0 000 8zM23 20v-1a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75',
    })
    items.push({
      // A6: 部門管理(設部門聯絡人).
      to: '/admin/departments',
      labelKey: 'nav.departments',
      icon: 'M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M9 13h.01M9 17h.01M15 9h.01M15 13h.01M15 17h.01',
    })
    items.push({
      // task brief M7-FE 「使用者管理」: 開帳號給其他人並設角色.
      to: '/admin/users',
      labelKey: 'nav.users',
      icon: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0',
    })
    items.push({
      // task brief 「admin webhooks 頁」.
      to: '/admin/webhooks',
      labelKey: 'nav.webhooks',
      icon: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
    })
    items.push({
      // 06 §1 管理後台「稽核」(M4-02).
      to: '/admin/audit-logs',
      labelKey: 'nav.auditLogs',
      icon: 'M9 12h6M9 16h6M9 8h6M5 4h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1z',
    })
    items.push({
      // task brief M9-FE 「AI 設定」頁.
      to: '/admin/ai',
      labelKey: 'nav.aiSettings',
      icon: 'M12 2a4 4 0 014 4c0 1.5-.8 2.4-1.6 3.2A3 3 0 0013 12v1H9v-1a3 3 0 00-1.4-2.8C6.8 8.4 6 7.5 6 6a4 4 0 016-3.46M9 17h6M10 21h4',
    })
  }
  // M6-HELP: role-aware user manual (src/pages/HelpPage.vue) -- every
  // authenticated role gets this, so it's pushed unconditionally, last,
  // so it lands near the bottom of the nav just above the logout button.
  items.push({
    to: '/help',
    labelKey: 'nav.help',
    icon: 'M9.2 9a2.8 2.8 0 115.2 1.5c-.7.9-1.9 1.3-1.9 2.7M12 17.2h.01M12 21a9 9 0 100-18 9 9 0 000 18z',
  })
  return items
})

// M8-3 designer layout: purely a rendering concern -- navItems above (and
// its role/feature gating) is untouched; this just partitions the same
// array into the designer's visual groups (收發作業/查詢報表/我的服務/管理
// 後台/說明) with a thin divider between groups (06-UI-UX.md left-nav spec).
type NavGroupKey = 'core' | 'query' | 'self' | 'admin' | 'help'

function navGroupFor(to: string): NavGroupKey {
  if (to === '/search' || to === '/reports') return 'query'
  if (to === '/my-mail' || to === '/notifications/settings') return 'self'
  if (to === '/help') return 'help'
  if (to.startsWith('/admin/') || to === '/notifications/failures') return 'admin'
  return 'core'
}

const NAV_GROUP_ORDER: Array<{ key: NavGroupKey; labelKey: string }> = [
  { key: 'core', labelKey: 'nav.group.core' },
  { key: 'query', labelKey: 'nav.group.query' },
  { key: 'self', labelKey: 'nav.group.self' },
  { key: 'admin', labelKey: 'nav.group.admin' },
  { key: 'help', labelKey: 'nav.group.help' },
]

interface NavEntry {
  kind: 'label' | 'divider' | 'item'
  key: string
  labelKey?: string
  item?: NavItem
}

const navEntries = computed<NavEntry[]>(() => {
  const buckets: Record<NavGroupKey, NavItem[]> = {
    core: [],
    query: [],
    self: [],
    admin: [],
    help: [],
  }
  for (const item of navItems.value) {
    buckets[navGroupFor(item.to)].push(item)
  }

  const entries: NavEntry[] = []
  let isFirstGroup = true
  for (const group of NAV_GROUP_ORDER) {
    const items = buckets[group.key]
    if (items.length === 0) continue
    if (!isFirstGroup) {
      entries.push({ kind: 'divider', key: `divider-${group.key}` })
    }
    entries.push({ kind: 'label', key: `label-${group.key}`, labelKey: group.labelKey })
    for (const item of items) {
      entries.push({ kind: 'item', key: item.to, item })
    }
    isFirstGroup = false
  }
  return entries
})

async function onLogout() {
  await auth.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="app-shell">
    <nav
      class="app-shell__nav"
      :aria-label="t('nav.dashboard')"
    >
      <div class="app-shell__brand">
        <svg
          class="app-shell__brand-mark"
          viewBox="0 0 32 32"
          aria-hidden="true"
          focusable="false"
        >
          <rect
            width="32"
            height="32"
            rx="7"
            class="app-shell__brand-mark-bg"
          />
          <rect
            x="6.5"
            y="9.5"
            width="19"
            height="14"
            rx="2"
            fill="none"
            stroke="#fff"
            stroke-width="1.6"
          />
          <path
            d="M6.5 11.5l9.5 6.5 9.5-6.5"
            fill="none"
            stroke="#fff"
            stroke-width="1.6"
            stroke-linejoin="round"
          />
        </svg>
        <span class="app-shell__brand-name">{{ t('app.name') }}</span>
      </div>
      <AppBadge
        v-if="roleBadgeLabel"
        status="neutral"
        :label="roleBadgeLabel"
        class="app-shell__role-badge"
      />
      <ul class="app-shell__nav-list">
        <template
          v-for="entry in navEntries"
          :key="entry.key"
        >
          <li
            v-if="entry.kind === 'divider'"
            class="app-shell__nav-divider"
            role="separator"
          />
          <li
            v-else-if="entry.kind === 'label'"
            class="app-shell__nav-group-label"
          >
            {{ t(entry.labelKey!) }}
          </li>
          <li v-else>
            <router-link
              :to="entry.item!.to"
              class="app-shell__nav-link"
            >
              <svg
                class="app-shell__nav-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path :d="entry.item!.icon" />
              </svg>
              <span>{{ t(entry.item!.labelKey) }}</span>
            </router-link>
          </li>
        </template>
      </ul>
      <button
        type="button"
        class="app-shell__change-password"
        @click="changePasswordOpen = true"
      >
        <svg
          class="app-shell__nav-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 10-8 0v2" />
        </svg>
        <span>{{ t('nav.changePassword') }}</span>
      </button>
      <button
        type="button"
        class="app-shell__logout"
        @click="onLogout"
      >
        {{ t('nav.logout') }}
      </button>
    </nav>
    <main class="app-shell__main">
      <OfflineQueueBadge class="app-shell__offline-badge" />
      <router-view />
      <footer class="app-shell__footer">
        <AuthorCredit />
      </footer>
    </main>
    <ChangePasswordDialog
      :open="changePasswordOpen"
      @close="changePasswordOpen = false"
    />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-shell__nav {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background-color: var(--color-bg-elevated);
  border-right: 1px solid var(--color-border-subtle);
  width: 240px;
  padding: var(--space-4);
  height: 100vh;
  overflow-y: auto;
  flex-shrink: 0;
}

.app-shell__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-1) var(--space-4);
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-border-subtle);
}

.app-shell__brand-mark {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.app-shell__brand-mark-bg {
  fill: var(--brand-primary);
}

.app-shell__brand-name {
  font-size: var(--font-size-base);
  font-weight: 800;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-shell__role-badge {
  align-self: flex-start;
  margin-bottom: var(--space-4);
}

.app-shell__nav-list {
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

/* M8-3 designer layout: 清楚分組 -- a small uppercase label above each nav
 * group (收發作業/查詢報表/我的服務/管理後台/說明), and a hairline divider
 * between groups (not before the first one). Both collapse away on the
 * mobile bottom bar below, where icons + the existing horizontal scroll
 * already carry the grouping visually. */
.app-shell__nav-group-label {
  padding: var(--space-3) var(--space-3) var(--space-1);
  font-size: var(--font-size-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.app-shell__nav-divider {
  height: 1px;
  margin: var(--space-2) var(--space-1);
  background-color: var(--color-border-subtle);
}

.app-shell__nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-text);
  text-decoration: none;
  font-weight: 600;
}

.app-shell__nav-link:hover {
  background-color: var(--color-bg-subtle);
}

/* Active pill: a pale tint of the (configurable) brand colour rather than a
 * flat grey, so the current page reads as "branded" the same way the
 * designer's static mock does with a solid fill -- just softened to a tint
 * so the bold brand-coloured label text on top stays readable. Falls back
 * to the plain neutral subtle background in browsers without color-mix()
 * support (the second `background-color` wins only when the engine
 * understands it; otherwise the declaration is dropped entirely and the
 * first one stands). */
.app-shell__nav-link.router-link-active {
  background-color: var(--color-bg-subtle);
  background-color: color-mix(in srgb, var(--brand-primary) 14%, var(--color-bg-elevated));
  color: var(--brand-primary);
  font-weight: 700;
}

.app-shell__nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.app-shell__change-password {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text);
  font-weight: 600;
  cursor: pointer;
  width: 100%;
  text-align: left;
}

.app-shell__change-password:hover {
  background-color: var(--color-bg-subtle);
}

.app-shell__logout {
  min-height: var(--touch-target-min);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text);
  font-weight: 600;
  cursor: pointer;
}

.app-shell__logout:hover {
  background-color: var(--color-bg-subtle);
}

.app-shell__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-5);
  background-color: var(--color-bg);
}

.app-shell__footer {
  /* Sits after the routed view inside the scrolling main column, so it
     follows the content rather than pinning to the viewport. */
  margin-top: var(--space-6);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.app-shell__offline-badge {
  margin-bottom: var(--space-4);
}

@media (max-width: 639px) {
  .app-shell {
    flex-direction: column;
  }
  .app-shell__main {
    padding-bottom: calc(var(--touch-target-min) + var(--space-4));
  }
  .app-shell__nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    width: auto;
    height: auto;
    overflow-y: visible;
    flex-direction: row;
    justify-content: flex-start;
    align-items: center;
    border-right: none;
    border-top: 1px solid var(--color-border);
    padding: var(--space-2);
    z-index: 10;
    /* POLISH-AUDIT.md Blocking #4: with several roles' nav items appended
     * (admin especially -- employees/webhooks/audit-logs on top of the base
     * set), the bottom bar can outgrow the viewport width. Let it scroll
     * horizontally instead of squeezing/wrapping/clipping items. */
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .app-shell__brand {
    display: none;
  }
  .app-shell__role-badge {
    display: none;
  }
  .app-shell__nav-group-label {
    display: none;
  }
  .app-shell__nav-list {
    flex-direction: row;
    flex-wrap: nowrap;
    flex-shrink: 0;
    gap: var(--space-1);
  }
  .app-shell__nav-list > li {
    flex-shrink: 0;
  }
  /* Groups collapse to icon-only chips on the horizontally-scrolling bottom
   * bar (see the `.app-shell__nav` overflow-x rule above); the divider still
   * marks the seam between groups, just rotated into a vertical rule. */
  .app-shell__nav-divider {
    width: 1px;
    height: 28px;
    margin: 0 var(--space-1);
  }
  .app-shell__nav-link {
    flex-direction: column;
    gap: var(--space-1);
    font-size: var(--font-size-xs);
    padding: var(--space-1) var(--space-2);
    white-space: nowrap;
  }
  .app-shell__logout {
    display: none;
  }
  .app-shell__change-password {
    /* Unlike logout (desktop-only above), self-service password change per
     * the task brief must stay reachable for every role -- including on the
     * mobile bottom bar -- so it gets nav-link-like sizing instead of being
     * hidden. */
    width: auto;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: 0;
    padding: var(--space-1) var(--space-2);
    border: none;
    font-size: var(--font-size-xs);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .app-shell__main {
    padding-bottom: calc(var(--touch-target-min) + var(--space-6));
  }
}

@media (min-width: 1024px) {
  .app-shell__nav {
    width: 260px;
  }
}
</style>
