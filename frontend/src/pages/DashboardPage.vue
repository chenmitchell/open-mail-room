<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppButton from '@/components/AppButton.vue'
import AppBadge from '@/components/AppBadge.vue'
import StatCard from '@/components/StatCard.vue'
import HelpHint from '@/components/HelpHint.vue'
import { useAuthStore } from '@/stores/auth'
import { branding } from '@/branding'
import { listItems } from '@/api/items'
import { formatDate, todayForDateInput } from '@/utils/format'
import { mailStatusBadgeVariant, mailStatusLabelKey } from '@/utils/mailStatus'
import type { MailItem } from '@/types/api'

// 06 §1 收件台(首頁): 大按鈕(拍照登記/批次上傳/領取核銷)、今日統計卡、待領取清單.
// 拍照登記/批次上傳 now route to the M2 photo/OCR pages (src/router/index.ts:
// inbound-photo / inbound-batch) — the M1 "coming soon" placeholder was
// stale once those pages shipped. 領取核銷 和 手動登記 are both live in M1
// and reachable from AppShell's nav as well as here.
//
// M6-HELP 角色化強化: `employee` doesn't do intake/pickup at all (01 §1
// RBAC), so the full receiving dashboard (big action buttons + today's
// stats + pickup-ready list) is counter/admin-only. An employee instead
// gets a short "what can I do here" panel pointing at 我的郵件/通知設定/
// 使用說明 -- the three things the task brief calls out for this role.
// `viewer` similarly never touches intake/pickup (only 查詢/報表 per the
// router's `requiresRole` guards), so it gets its own minimal panel rather
// than showing action buttons that would just bounce back here.
const { t } = useI18n({ useScope: 'global' })
const auth = useAuthStore()
const router = useRouter()

const isReceivingRole = computed(() => auth.role === 'admin' || auth.role === 'counter')
const isEmployee = computed(() => auth.role === 'employee')
const isViewer = computed(() => auth.role === 'viewer')

const statsLoading = ref(true)
const todayReceived = ref(0)
const awaitingPickup = ref(0)
const unclaimed = ref(0)
const monthVolume = ref(0)

const pickupList = ref<MailItem[]>([])
const pickupListLoading = ref(true)
const pickupListError = ref(false)

// M8-3 designer layout: dashboard header reads "今日收發 · date · location",
// location coming from config/branding.yaml `pickup_location` (the same
// typed accessor other pages use -- see src/branding.ts). No location
// configured -> just show the date, rather than a stray " · " with nothing
// after it.
const headerMeta = computed(() => {
  const date = formatDate(new Date().toISOString())
  return branding.pickup_location ? `${date} · ${branding.pickup_location}` : date
})

// ASSUMPTION (flag for backend/reviewer): 03-API-SPEC.md's `GET
// /reports/summary` return shape isn't specified, so the stats cards are
// composed from `GET /items` (documented `q/status/date_from/date_to` +
// `meta.total`) instead of guessing that shape. Revisit once M4 wires up
// the real reports page (08-EXECUTION-PLAN.md).
// M8-3 designer layout: stat row is 今日收件/待領取/滯留/本月件量 (dropped the
// old 今日已領取 card, not part of the designer spec). 本月件量 reuses the
// same `GET /items` endpoint as the other three cards (see the ASSUMPTION
// above `loadStats`) with a month-to-date date range instead of a new
// backend call.
async function loadStats() {
  statsLoading.value = true
  const today = todayForDateInput()
  const monthStart = `${today.slice(0, 7)}-01`
  try {
    const [received, notified, stranded, monthly] = await Promise.all([
      listItems({ status: 'received', date_from: today, date_to: today, size: 1 }),
      listItems({ status: 'notified', size: 1 }),
      listItems({ status: 'unclaimed', size: 1 }),
      listItems({ date_from: monthStart, date_to: today, size: 1 }),
    ])
    todayReceived.value = received.meta.total
    awaitingPickup.value = notified.meta.total
    unclaimed.value = stranded.meta.total
    monthVolume.value = monthly.meta.total
  } catch {
    // Leave counts at 0 rather than throwing — the dashboard should still
    // render its navigation even if the backend is briefly unreachable.
  } finally {
    statsLoading.value = false
  }
}

async function loadPickupList() {
  pickupListLoading.value = true
  pickupListError.value = false
  try {
    const result = await listItems({ status: 'notified', size: 10 })
    pickupList.value = result.items
  } catch {
    pickupListError.value = true
  } finally {
    pickupListLoading.value = false
  }
}

function goToPickup() {
  router.push({ name: 'pickup' })
}

// M8-3 designer layout: pickup-ready row is 姓名 + 部門 + 承運商/單號 (or the
// internal item_no when there's no carrier tracking number yet), matching
// how src/pages/search/SearchPage.vue already renders carrier + tracking.
function carrierLine(item: MailItem): string {
  const carrier = item.carrier_name ?? '—'
  const reference = item.tracking_no ?? item.item_no
  return `${carrier} ${reference}`
}

function goToPhotoRegister() {
  router.push({ name: 'inbound-photo' })
}

function goToBatchUpload() {
  router.push({ name: 'inbound-batch' })
}

function goToMyMail() {
  router.push({ name: 'my-mail' })
}

function goToNotificationSettings() {
  router.push({ name: 'notification-settings' })
}

function goToHelp() {
  router.push({ name: 'help' })
}

function goToSearch() {
  router.push({ name: 'search' })
}

function goToReports() {
  router.push({ name: 'reports' })
}

onMounted(() => {
  // Counter/admin only: the stats cards and pickup-ready list are
  // receiving-desk data an employee/viewer has no use for on their
  // simplified panel, so skip the extra requests entirely for them.
  if (isReceivingRole.value) {
    loadStats()
    loadPickupList()
  }
})
</script>

<template>
  <section class="dashboard-page">
    <header class="dashboard-page__header">
      <h1 class="dashboard-page__title">
        {{ t('dashboard.headerTitle') }}
        <HelpHint :text="t('help.hint.dashboard')" />
      </h1>
      <p class="dashboard-page__meta">
        {{ headerMeta }}
      </p>
    </header>

    <div
      v-if="isEmployee"
      class="dashboard-page__employee-panel"
    >
      <p class="dashboard-page__intro">
        {{ t('dashboard.employeeIntro') }}
      </p>
      <div class="dashboard-page__actions">
        <AppButton
          variant="primary"
          @click="goToMyMail"
        >
          {{ t('nav.myMail') }}
        </AppButton>
        <AppButton
          variant="secondary"
          @click="goToNotificationSettings"
        >
          {{ t('nav.notificationSettings') }}
        </AppButton>
        <AppButton
          variant="secondary"
          @click="goToHelp"
        >
          {{ t('nav.help') }}
        </AppButton>
      </div>
    </div>

    <div
      v-else-if="isViewer"
      class="dashboard-page__viewer-panel"
    >
      <p class="dashboard-page__intro">
        {{ t('dashboard.viewerIntro') }}
      </p>
      <div class="dashboard-page__actions">
        <AppButton
          variant="primary"
          @click="goToSearch"
        >
          {{ t('nav.search') }}
        </AppButton>
        <AppButton
          variant="secondary"
          @click="goToReports"
        >
          {{ t('nav.reports') }}
        </AppButton>
      </div>
    </div>

    <template v-else>
      <div class="dashboard-page__actions dashboard-page__actions--primary">
        <AppButton
          variant="primary"
          class="dashboard-page__cta"
          @click="goToPhotoRegister"
        >
          {{ t('dashboard.actionPhotoRegister') }}
        </AppButton>
        <AppButton
          variant="secondary"
          class="dashboard-page__cta"
          @click="goToBatchUpload"
        >
          {{ t('dashboard.actionBatchUpload') }}
        </AppButton>
        <AppButton
          variant="secondary"
          class="dashboard-page__cta"
          @click="goToPickup"
        >
          {{ t('dashboard.actionPickup') }}
        </AppButton>
      </div>

      <div class="dashboard-page__stats">
        <StatCard
          :label="t('dashboard.statReceivedToday')"
          :value="todayReceived"
          :loading="statsLoading"
        />
        <StatCard
          :label="t('dashboard.statAwaitingPickup')"
          :value="awaitingPickup"
          :loading="statsLoading"
        />
        <StatCard
          :label="t('dashboard.statUnclaimed')"
          :value="unclaimed"
          :loading="statsLoading"
          tone="warning"
        />
        <StatCard
          :label="t('dashboard.statMonthVolume')"
          :value="monthVolume"
          :loading="statsLoading"
        />
      </div>

      <section class="dashboard-page__panel">
        <h2 class="dashboard-page__panel-title">
          <span>{{ t('dashboard.readyForPickup') }}</span>
          <span
            v-if="!pickupListLoading && !pickupListError"
            class="dashboard-page__panel-count"
          >
            {{ t('dashboard.resultsCaption', { total: pickupList.length }) }}
          </span>
        </h2>

        <p v-if="pickupListLoading">
          {{ t('common.loading') }}
        </p>
        <p
          v-else-if="pickupListError"
          class="dashboard-page__error"
          role="alert"
        >
          {{ t('errors.generic') }}
        </p>
        <p
          v-else-if="pickupList.length === 0"
          class="dashboard-page__empty"
        >
          {{ t('dashboard.emptyPickup') }}
        </p>
        <ul
          v-else
          class="dashboard-page__list"
        >
          <li
            v-for="item in pickupList"
            :key="item.id"
            class="dashboard-page__list-item"
          >
            <span class="dashboard-page__list-main">
              <span class="dashboard-page__list-name">{{ item.recipient_name_raw }}</span>
              <span class="dashboard-page__list-dept">{{ item.department_name ?? '—' }}</span>
              <span class="dashboard-page__list-carrier">{{ carrierLine(item) }}</span>
            </span>
            <AppBadge
              :status="mailStatusBadgeVariant(item.status)"
              :label="t(mailStatusLabelKey(item.status))"
              class="dashboard-page__list-badge"
            />
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.dashboard-page__header {
  margin: 0 0 var(--space-5);
}

.dashboard-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0;
}

.dashboard-page__meta {
  margin: var(--space-1) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.dashboard-page__intro {
  color: var(--color-text-muted);
  margin: 0 0 var(--space-4);
  max-width: 480px;
}

.dashboard-page__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

/* M8-3 designer layout: 拍照登記/批次上傳/領取核銷 are the dashboard's primary
 * "大動作按鈕" -- taller than AppButton's default 44px touch target (still
 * >= the 44px a11y floor) so they read as the main call-to-action row, both
 * on desktop and stacked full-width on mobile (see the <640px rule below). */
.dashboard-page__cta {
  min-height: 52px;
  padding: var(--space-3) var(--space-5);
  font-size: var(--font-size-base);
}

@media (max-width: 639px) {
  .dashboard-page__actions--primary {
    flex-direction: column;
  }
  .dashboard-page__actions--primary .dashboard-page__cta {
    width: 100%;
  }
}

.dashboard-page__stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

@media (min-width: 640px) {
  .dashboard-page__stats {
    grid-template-columns: repeat(4, 1fr);
  }
}

.dashboard-page__panel {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.dashboard-page__panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--color-border-subtle);
}

.dashboard-page__panel-count {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  font-weight: 400;
  color: var(--color-text-muted);
}

.dashboard-page__empty {
  color: var(--color-text-muted);
  margin: 0;
}

.dashboard-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.dashboard-page__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.dashboard-page__list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  flex-wrap: wrap;
}

.dashboard-page__list-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.dashboard-page__list-name {
  font-weight: 700;
  color: var(--color-text);
}

.dashboard-page__list-dept,
.dashboard-page__list-carrier {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.dashboard-page__list-carrier {
  font-family: var(--font-family-mono);
}

.dashboard-page__list-badge {
  flex-shrink: 0;
}
</style>
