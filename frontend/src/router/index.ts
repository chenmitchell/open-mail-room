import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { needsSetup, resolveSetupRedirect } from './setupStatus'

const routes = [
  {
    // SETUP-WIZARD: first-run "create the initial administrator" page
    // (backend/app/api/v1/setup.py). Public (no session exists yet) --
    // access is gated by the beforeEach guard below instead: reachable
    // only while `needs_setup` is true, otherwise bounced to /login.
    path: '/setup',
    name: 'setup',
    component: () => import('@/pages/SetupPage.vue'),
    meta: { public: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/offline',
    name: 'offline',
    component: () => import('@/pages/OfflinePage.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/pages/AppShell.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        // 06 §1 收件台(首頁).
        path: '',
        name: 'dashboard',
        component: () => import('@/pages/DashboardPage.vue'),
      },
      {
        // 06 §1 手動登記頁 — kept as the always-available fallback ("系統可用
        // 純手動模式" per 04-AI-OCR.md §4) alongside the M2 photo/OCR flow
        // below.
        path: 'register',
        name: 'inbound-register',
        component: () => import('@/pages/inbound/InboundRegisterPage.vue'),
      },
      {
        // 06 §1 拍照登記頁 (M2-02).
        path: 'register/photo',
        name: 'inbound-photo',
        component: () => import('@/pages/inbound/PhotoRegisterPage.vue'),
      },
      {
        // 06 §1 批次上傳 (M2-02).
        path: 'register/batch',
        name: 'inbound-batch',
        component: () => import('@/pages/inbound/BatchUploadPage.vue'),
      },
      {
        // 06 §1 OCR 確認頁 (M2-02). No :jobId param — the confirm queue
        // (src/stores/ocrConfirmQueue.ts) drives which job is being shown so
        // the page can step through a whole batch without re-navigating.
        path: 'register/confirm',
        name: 'inbound-confirm',
        component: () => import('@/pages/inbound/OcrConfirmPage.vue'),
      },
      {
        // 06 §1 領取核銷頁.
        path: 'pickup',
        name: 'pickup',
        component: () => import('@/pages/pickup/PickupPage.vue'),
      },
      {
        // 06 §1 查詢頁 (M1 scope: filter + list + detail drawer). M4-02 added
        // a dedicated /reports route (below) for the chart/card summary
        // view backed by `GET /reports/summary` — this page stays the
        // record-level search/detail-drawer view.
        path: 'search',
        name: 'search',
        component: () => import('@/pages/search/SearchPage.vue'),
      },
      {
        // 06 §1 管理後台 → 員工名錄. admin only (01 §1 RBAC).
        path: 'admin/employees',
        name: 'admin-employees',
        component: () => import('@/pages/admin/EmployeesAdminPage.vue'),
        meta: { requiresRole: 'admin' },
      },
      {
        // task brief M7-FE: 管理後台 → 使用者管理(開帳號/設角色). admin only
        // (01 §1 RBAC), same guard convention as admin-employees above.
        path: 'admin/users',
        name: 'admin-users',
        component: () => import('@/pages/admin/UsersAdminPage.vue'),
        meta: { requiresRole: 'admin' },
      },
      {
        // A6: 管理後台 → 部門管理(設定部門聯絡人,部門件路由用). admin only.
        path: 'admin/departments',
        name: 'admin-departments',
        component: () => import('@/pages/admin/DepartmentsAdminPage.vue'),
        meta: { requiresRole: 'admin' },
      },
      {
        // 06 §1 「我的郵件」(employee): 待領/歷史 + 取件碼. Not role-gated —
        // any authenticated user (counter/admin included) may also be a
        // directory employee who receives mail themselves (ASSUMPTION, see
        // src/types/api.ts `AuthUser.pickup_code`).
        path: 'my-mail',
        name: 'my-mail',
        component: () => import('@/pages/employee/MyMailPage.vue'),
      },
      {
        // 06 §1 「交寄」頁 (M4-02): 對象 counter/employee per the page-list
        // table — viewer is read-only (查詢/報表 only) so it's excluded here.
        // admin has "全部" per 01 §1 RBAC, kept in the allow-list too.
        path: 'outbound',
        name: 'outbound',
        component: () => import('@/pages/outbound/OutboundPage.vue'),
        meta: { requiresRole: ['admin', 'counter', 'employee'] },
      },
      {
        // 06 §1 「查詢/報表」頁 (M4-02 report cards + chart, integrates
        // `GET /reports/summary` per the router comment on the `search`
        // route below). Object per page-list table: counter/viewer (+admin).
        path: 'reports',
        name: 'reports',
        component: () => import('@/pages/reports/ReportsPage.vue'),
        meta: { requiresRole: ['admin', 'counter', 'viewer'] },
      },
      {
        // 03 §2 通知綁定(員工自助) UI: LINE/Telegram 綁定精靈 + 直接綁定表單.
        // Same "not role-gated" reasoning as my-mail above.
        path: 'notifications/settings',
        name: 'notification-settings',
        component: () => import('@/pages/employee/NotificationSettingsPage.vue'),
      },
      {
        // task brief 「通知失敗清單」(counter/admin): dead 通知 + 重發.
        path: 'notifications/failures',
        name: 'notification-failures',
        component: () => import('@/pages/notifications/NotificationFailuresPage.vue'),
        meta: { requiresRole: ['admin', 'counter'] },
      },
      {
        // task brief 「admin webhooks 頁」. admin only (01 §1 RBAC).
        path: 'admin/webhooks',
        name: 'admin-webhooks',
        component: () => import('@/pages/admin/WebhooksAdminPage.vue'),
        meta: { requiresRole: 'admin' },
      },
      {
        // 06 §1 管理後台「稽核」(M4-02): `GET /admin/audit-logs`. admin only
        // (01 §1 RBAC).
        path: 'admin/audit-logs',
        name: 'admin-audit-logs',
        component: () => import('@/pages/admin/AuditLogsPage.vue'),
        meta: { requiresRole: 'admin' },
      },
      {
        // task brief M9-FE 「AI 設定」頁: GET/PUT /admin/ai/status|models|
        // settings. admin only, same RBAC convention as the other admin/*
        // routes above.
        path: 'admin/ai',
        name: 'admin-ai',
        component: () => import('@/pages/admin/AiSettingsPage.vue'),
        meta: { requiresRole: 'admin' },
      },
      {
        // M6-HELP: role-aware user manual (src/pages/HelpPage.vue). Every
        // authenticated role can read it -- deliberately NOT gated by
        // `requiresRole` (unlike the admin/counter-only routes above) since
        // the whole point is that every role, including viewer, has a page
        // explaining what they can do.
        path: 'help',
        name: 'help',
        component: () => import('@/pages/HelpPage.vue'),
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to: RouteLocationNormalized) => {
  // SETUP-WIZARD: checked before anything else (including the `public`
  // carve-out below) so a fresh install with zero admins always lands on
  // /setup no matter what URL was requested, and — the flip side — /setup
  // itself becomes unreachable again the instant an admin exists (bounced
  // to /login instead). `resolveSetupRedirect` is the pure decision
  // function (src/router/setupStatus.ts) that keeps this from looping:
  // it returns `null` (no redirect) once `to` already matches where this
  // check would otherwise send it.
  const setupNeeded = await needsSetup()
  const setupRedirect = resolveSetupRedirect(setupNeeded, to.name)
  if (setupRedirect) {
    return { name: setupRedirect }
  }

  if (to.meta.public) return true

  const auth = useAuthStore()
  if (auth.status === 'idle') {
    await auth.fetchMe()
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // 01 §1 RBAC: enforced server-side too (07 §2 "RBAC 在後端每個端點強制檢查
  // 不能只靠前端隱藏按鈕") — this is only a navigation convenience so a
  // non-admin never even sees the admin page shell render. `requiresRole` may
  // be a single role (existing admin-only routes) or an array (M3-02
  // notification-failures: counter OR admin).
  const requiresRole = to.meta.requiresRole as string | string[] | undefined
  if (requiresRole) {
    const allowedRoles = Array.isArray(requiresRole) ? requiresRole : [requiresRole]
    if (!auth.role || !allowedRoles.includes(auth.role)) {
      return { name: 'dashboard' }
    }
  }

  return true
})
