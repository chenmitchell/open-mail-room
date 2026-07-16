<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppButton from '@/components/AppButton.vue'
import StatCard from '@/components/StatCard.vue'
import HelpHint from '@/components/HelpHint.vue'
import { getExportUrl, getReportSummary, triggerExportDownload } from '@/api/reports'
import { ApiError } from '@/api/client'
import { buildBarChart } from './reportChart'
import type { ReportGroupBy, ReportSummary } from '@/types/api'

// 03-API-SPEC.md §2 `GET /reports/summary?from=&to=&group_by=
// department|carrier|day`; 01 §4 「報表:每日/每月件量、各部門件量、平均領
// 取時間、滯留清單、各承運商佔比」. Task brief: "日期區間+group_by 切換
// (部門/承運商/日),卡片+簡單長條圖(不裝圖表庫,用 CSS/SVG 自繪,遵守
// Okabe-Ito token 與 aria);匯出按鈕(items.csv/outbound.csv 下載)".
const { t } = useI18n({ useScope: 'global' })

function isoDateDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const form = reactive({
  from: isoDateDaysAgo(30),
  to: isoDateDaysAgo(0),
  groupBy: 'department' as ReportGroupBy,
})

const groupByOptions = computed(() =>
  (['department', 'carrier', 'day'] satisfies ReportGroupBy[]).map((value) => ({
    value,
    label: t(`reports.groupBy.${value}`),
  })),
)

const summary = ref<ReportSummary | null>(null)
const loading = ref(false)
const loadError = ref<string | null>(null)

// 06-UI-UX.md §3: colour is never the sole carrier of meaning, and every
// chart needs an accessible fallback — the bar chart below is `role="img"`
// with a single summarizing aria-label, and the <table> underneath (always
// rendered, never visually hidden) carries the exact per-row numbers for
// screen readers / keyboard users / anyone who prefers a table.
const barData = computed(() => buildBarChart(summary.value?.rows ?? [], 'received_count'))
const groupByColumnLabel = computed(() =>
  summary.value ? t(`reports.groupBy.${summary.value.group_by}`) : '',
)

async function runReport() {
  loading.value = true
  loadError.value = null
  try {
    summary.value = await getReportSummary({ from: form.from, to: form.to, group_by: form.groupBy })
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
    summary.value = null
  } finally {
    loading.value = false
  }
}

function exportItems() {
  triggerExportDownload(getExportUrl('items', { date_from: form.from, date_to: form.to }))
}

function exportOutbound() {
  triggerExportDownload(getExportUrl('outbound', { date_from: form.from, date_to: form.to }))
}

onMounted(runReport)
</script>

<template>
  <section class="reports-page">
    <h1 class="reports-page__title">
      {{ t('reports.title') }}
      <HelpHint :text="t('help.hint.reports')" />
    </h1>

    <form
      class="reports-page__filters"
      novalidate
      @submit.prevent="runReport"
    >
      <AppInput
        v-model="form.from"
        type="date"
        :label="t('reports.fromLabel')"
      />
      <AppInput
        v-model="form.to"
        type="date"
        :label="t('reports.toLabel')"
      />
      <AppSelect
        v-model="form.groupBy"
        :label="t('reports.groupByLabel')"
        :options="groupByOptions"
      />
      <AppButton
        type="submit"
        :loading="loading"
      >
        {{ t('reports.apply') }}
      </AppButton>
    </form>

    <p
      v-if="loadError"
      class="reports-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>

    <template v-if="summary">
      <div class="reports-page__stats">
        <StatCard
          :label="t('reports.statReceived')"
          :value="summary.totals.received_count"
        />
        <StatCard
          :label="t('reports.statPickedUp')"
          :value="summary.totals.picked_up_count"
        />
        <StatCard
          :label="t('reports.statUnclaimed')"
          :value="summary.totals.unclaimed_count"
        />
        <StatCard
          :label="t('reports.statAvgPickupHours')"
          :value="summary.totals.avg_pickup_hours != null ? summary.totals.avg_pickup_hours.toFixed(1) : '—'"
        />
        <StatCard
          :label="t('reports.statOutboundShipped')"
          :value="summary.totals.outbound_shipped_count"
        />
      </div>

      <p
        v-if="summary.rows.length === 0"
        class="reports-page__empty"
      >
        {{ t('reports.empty') }}
      </p>

      <template v-else>
        <h2 class="reports-page__section-title">
          {{ t('reports.chartTitle') }}
        </h2>
        <div
          class="reports-page__chart"
          role="img"
          :aria-label="t('reports.chartAriaLabel')"
        >
          <div
            v-for="bar in barData"
            :key="bar.key"
            class="reports-page__bar-row"
          >
            <span class="reports-page__bar-label">{{ bar.label }}</span>
            <span class="reports-page__bar-track">
              <span
                class="reports-page__bar-fill"
                :style="{ width: bar.percent + '%' }"
              />
            </span>
            <span class="reports-page__bar-value">{{ bar.value }}</span>
          </div>
        </div>

        <h2 class="reports-page__section-title">
          {{ t('reports.tableTitle') }}
        </h2>
        <div class="reports-page__table-card">
          <table class="reports-page__table">
            <thead>
              <tr>
                <th scope="col">
                  {{ groupByColumnLabel }}
                </th>
                <th scope="col">
                  {{ t('reports.colReceived') }}
                </th>
                <th scope="col">
                  {{ t('reports.colPickedUp') }}
                </th>
                <th scope="col">
                  {{ t('reports.colUnclaimed') }}
                </th>
                <th scope="col">
                  {{ t('reports.colAvgPickupHours') }}
                </th>
                <th scope="col">
                  {{ t('reports.colOutboundShipped') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in summary.rows"
                :key="row.key"
              >
                <td :data-label="groupByColumnLabel">
                  {{ row.label }}
                </td>
                <td :data-label="t('reports.colReceived')">
                  {{ row.received_count }}
                </td>
                <td :data-label="t('reports.colPickedUp')">
                  {{ row.picked_up_count }}
                </td>
                <td :data-label="t('reports.colUnclaimed')">
                  {{ row.unclaimed_count }}
                </td>
                <td :data-label="t('reports.colAvgPickupHours')">
                  {{ row.avg_pickup_hours != null ? row.avg_pickup_hours.toFixed(1) : '—' }}
                </td>
                <td :data-label="t('reports.colOutboundShipped')">
                  {{ row.outbound_shipped_count }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>

    <section class="reports-page__export">
      <h2 class="reports-page__section-title">
        {{ t('reports.exportTitle') }}
      </h2>
      <div class="reports-page__export-actions">
        <AppButton
          variant="secondary"
          @click="exportItems"
        >
          {{ t('reports.exportItems') }}
        </AppButton>
        <AppButton
          variant="secondary"
          @click="exportOutbound"
        >
          {{ t('reports.exportOutbound') }}
        </AppButton>
      </div>
    </section>
  </section>
</template>

<style scoped>
.reports-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.reports-page__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.reports-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.reports-page__empty {
  color: var(--color-text-muted);
}

.reports-page__stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

@media (min-width: 640px) {
  .reports-page__stats {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (min-width: 960px) {
  .reports-page__stats {
    grid-template-columns: repeat(5, 1fr);
  }
}

.reports-page__section-title {
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.reports-page__chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.reports-page__table-card {
  padding: var(--space-4);
  margin-bottom: var(--space-6);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.reports-page__bar-row {
  display: grid;
  grid-template-columns: minmax(96px, 25%) 1fr auto;
  align-items: center;
  gap: var(--space-3);
}

.reports-page__bar-label {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.reports-page__bar-track {
  display: block;
  height: 20px;
  border-radius: var(--radius-sm);
  background-color: var(--color-bg-subtle);
  overflow: hidden;
}

.reports-page__bar-fill {
  display: block;
  height: 100%;
  min-width: 2px;
  background-color: var(--oi-blue);
}

.reports-page__bar-value {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-weight: 600;
  min-width: 2ch;
  text-align: right;
}

.reports-page__table {
  width: 100%;
  border-collapse: collapse;
}

.reports-page__table th,
.reports-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.reports-page__export-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

/* Mobile card collapse (06 §2 Mobile-first, breakpoint 640) -- same pattern
   as SearchPage.vue (POLISH-AUDIT.md Should-fix #5); the bar-chart summary
   above already has its own responsive layout, this only affects the
   detail <table>. */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .reports-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .reports-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .reports-page__table,
  .reports-page__table tbody,
  .reports-page__table tr,
  .reports-page__table td {
    display: block;
    width: 100%;
  }

  .reports-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .reports-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .reports-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
    flex-shrink: 0;
  }
}
</style>
