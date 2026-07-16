<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import AppDialog from '@/components/AppDialog.vue'
import HelpHint from '@/components/HelpHint.vue'
import { listAuditLogs } from '@/api/audit'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import type { AuditLogEntry, AuditLogsQuery } from '@/types/api'

// 01-REQUIREMENTS.md §4 「稽核紀錄:誰在何時建立/修改/刪除/查看了哪筆(機密
// 件查看也記錄)」; 03-API-SPEC.md §2 `GET /admin/audit-logs`. admin only
// (01 §1 RBAC).
const { t } = useI18n({ useScope: 'global' })

const filters = reactive({
  actorId: '',
  action: '',
  targetType: '',
  targetId: '',
  dateFrom: '',
  dateTo: '',
})

const page = ref(1)
const size = 20
const entries = ref<AuditLogEntry[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref<string | null>(null)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

const selectedEntry = ref<AuditLogEntry | null>(null)

function buildQuery(): AuditLogsQuery {
  return {
    actor_id: filters.actorId || undefined,
    action: filters.action || undefined,
    target_type: filters.targetType || undefined,
    target_id: filters.targetId || undefined,
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
    page: page.value,
    size,
  }
}

async function runSearch() {
  loading.value = true
  loadError.value = null
  try {
    const result = await listAuditLogs(buildQuery())
    entries.value = result.items
    total.value = result.meta.total
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
    entries.value = []
  } finally {
    loading.value = false
  }
}

function onFilterSubmit() {
  page.value = 1
  runSearch()
}

function resetFilters() {
  filters.actorId = ''
  filters.action = ''
  filters.targetType = ''
  filters.targetId = ''
  filters.dateFrom = ''
  filters.dateTo = ''
  page.value = 1
  runSearch()
}

function goToPage(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
  runSearch()
}

function openDiff(entry: AuditLogEntry) {
  selectedEntry.value = entry
}

function closeDiff() {
  selectedEntry.value = null
}

const diffText = computed(() => {
  if (!selectedEntry.value?.diff_json) return null
  return JSON.stringify(selectedEntry.value.diff_json, null, 2)
})

onMounted(runSearch)
</script>

<template>
  <section class="audit-logs-page">
    <h1 class="audit-logs-page__title">
      {{ t('auditLogs.title') }}
      <HelpHint :text="t('help.hint.auditLogs')" />
    </h1>

    <form
      class="audit-logs-page__filters"
      novalidate
      @submit.prevent="onFilterSubmit"
    >
      <AppInput
        v-model="filters.actorId"
        :label="t('auditLogs.filterActorLabel')"
      />
      <AppInput
        v-model="filters.action"
        :label="t('auditLogs.filterActionLabel')"
      />
      <AppInput
        v-model="filters.targetType"
        :label="t('auditLogs.filterTargetTypeLabel')"
      />
      <AppInput
        v-model="filters.targetId"
        :label="t('auditLogs.filterTargetIdLabel')"
      />
      <AppInput
        v-model="filters.dateFrom"
        type="date"
        :label="t('auditLogs.dateFromLabel')"
      />
      <AppInput
        v-model="filters.dateTo"
        type="date"
        :label="t('auditLogs.dateToLabel')"
      />

      <div class="audit-logs-page__filter-actions">
        <AppButton
          type="submit"
          :loading="loading"
        >
          {{ t('auditLogs.apply') }}
        </AppButton>
        <AppButton
          type="button"
          variant="ghost"
          @click="resetFilters"
        >
          {{ t('auditLogs.reset') }}
        </AppButton>
      </div>
    </form>

    <p
      v-if="loadError"
      class="audit-logs-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p
      v-else-if="!loading && entries.length === 0"
      class="audit-logs-page__empty"
    >
      {{ t('auditLogs.empty') }}
    </p>

    <div
      v-if="entries.length"
      class="audit-logs-page__table-card"
    >
      <table class="audit-logs-page__table">
        <caption class="audit-logs-page__caption">
          {{ t('auditLogs.resultsCaption', { total }) }}
        </caption>
        <thead>
          <tr>
            <th scope="col">
              {{ t('auditLogs.colAt') }}
            </th>
            <th scope="col">
              {{ t('auditLogs.colActor') }}
            </th>
            <th scope="col">
              {{ t('auditLogs.colAction') }}
            </th>
            <th scope="col">
              {{ t('auditLogs.colTarget') }}
            </th>
            <th scope="col">
              {{ t('auditLogs.colIp') }}
            </th>
            <th scope="col">
              {{ t('auditLogs.colActions') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in entries"
            :key="entry.id"
          >
            <td :data-label="t('auditLogs.colAt')">
              {{ formatDateTime(entry.at) }}
            </td>
            <td :data-label="t('auditLogs.colActor')">
              {{ entry.actor_name ?? entry.actor_id ?? entry.actor_type }}
            </td>
            <td :data-label="t('auditLogs.colAction')">
              {{ entry.action }}
            </td>
            <td :data-label="t('auditLogs.colTarget')">
              {{ entry.target_type }}<span v-if="entry.target_id"> · {{ entry.target_id }}</span>
            </td>
            <td :data-label="t('auditLogs.colIp')">
              {{ entry.ip ?? '—' }}
            </td>
            <td :data-label="t('auditLogs.colActions')">
              <AppButton
                variant="ghost"
                @click="openDiff(entry)"
              >
                {{ t('auditLogs.viewDiff') }}
              </AppButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav
      v-if="entries.length"
      class="audit-logs-page__pagination"
      :aria-label="t('auditLogs.paginationLabel')"
    >
      <AppButton
        variant="ghost"
        :disabled="page <= 1"
        @click="goToPage(page - 1)"
      >
        {{ t('auditLogs.prevPage') }}
      </AppButton>
      <span class="audit-logs-page__page-indicator">{{ t('auditLogs.pageIndicator', { page, totalPages }) }}</span>
      <AppButton
        variant="ghost"
        :disabled="page >= totalPages"
        @click="goToPage(page + 1)"
      >
        {{ t('auditLogs.nextPage') }}
      </AppButton>
    </nav>

    <AppDialog
      :open="selectedEntry !== null"
      :title="t('auditLogs.diffTitle')"
      @close="closeDiff"
    >
      <pre
        v-if="diffText"
        class="audit-logs-page__diff"
      >{{ diffText }}</pre>
      <p v-else>
        {{ t('auditLogs.diffEmpty') }}
      </p>
    </AppDialog>
  </section>
</template>

<style scoped>
.audit-logs-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.audit-logs-page__filters {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 var(--space-4);
  margin-bottom: var(--space-3);
}

@media (min-width: 640px) {
  .audit-logs-page__filters {
    grid-template-columns: repeat(3, 1fr);
  }
}

.audit-logs-page__filter-actions {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

.audit-logs-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.audit-logs-page__empty {
  color: var(--color-text-muted);
}

.audit-logs-page__caption {
  text-align: left;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-2);
}

.audit-logs-page__table-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  overflow-x: auto;
}

.audit-logs-page__table {
  width: 100%;
  border-collapse: collapse;
}

.audit-logs-page__table th,
.audit-logs-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.audit-logs-page__pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.audit-logs-page__page-indicator {
  color: var(--color-text);
  font-weight: 600;
}

.audit-logs-page__diff {
  white-space: pre-wrap;
  word-break: break-word;
  background-color: var(--color-bg-subtle);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

/* Mobile card collapse — same pattern as SearchPage.vue. */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .audit-logs-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .audit-logs-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .audit-logs-page__table,
  .audit-logs-page__table tbody,
  .audit-logs-page__table tr,
  .audit-logs-page__table td {
    display: block;
    width: 100%;
  }

  .audit-logs-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .audit-logs-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .audit-logs-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
  }
}
</style>
