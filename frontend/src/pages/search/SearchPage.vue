<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppButton from '@/components/AppButton.vue'
import AppBadge from '@/components/AppBadge.vue'
import AppDialog from '@/components/AppDialog.vue'
import HelpHint from '@/components/HelpHint.vue'
import { listItems } from '@/api/items'
import { listCarriers } from '@/api/carriers'
import { listDepartments } from '@/api/departments'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import { mailStatusBadgeVariant, mailStatusLabelKey } from '@/utils/mailStatus'
import type { Carrier, Department, ItemsQuery, MailItem, MailItemStatus } from '@/types/api'

const { t } = useI18n({ useScope: 'global' })

const STATUSES: MailItemStatus[] = [
  'received',
  'notified',
  'picked_up',
  'returned',
  'forwarded',
  'unclaimed',
  'destroyed',
]

const filters = reactive({
  q: '',
  status: '',
  carrierId: '',
  departmentId: '',
  dateFrom: '',
  dateTo: '',
})

const page = ref(1)
const size = 20
const items = ref<MailItem[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref<string | null>(null)

const carriers = ref<Carrier[]>([])
const departments = ref<Department[]>([])

const statusOptions = computed(() => STATUSES.map((s) => ({ value: s, label: t(mailStatusLabelKey(s)) })))
const carrierOptions = computed(() => carriers.value.map((c) => ({ value: c.id, label: c.name })))
const departmentOptions = computed(() => departments.value.map((d) => ({ value: d.id, label: d.name })))

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

const selectedItem = ref<MailItem | null>(null)

function buildQuery(): ItemsQuery {
  return {
    q: filters.q || undefined,
    status: (filters.status || undefined) as MailItemStatus | undefined,
    carrier_id: filters.carrierId || undefined,
    department_id: filters.departmentId || undefined,
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
    const result = await listItems(buildQuery())
    items.value = result.items
    total.value = result.meta.total
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
    items.value = []
  } finally {
    loading.value = false
  }
}

function onFilterSubmit() {
  page.value = 1
  runSearch()
}

function resetFilters() {
  filters.q = ''
  filters.status = ''
  filters.carrierId = ''
  filters.departmentId = ''
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

function openDetail(item: MailItem) {
  selectedItem.value = item
}

function closeDetail() {
  selectedItem.value = null
}

onMounted(async () => {
  runSearch()
  try {
    const [carrierResult, departmentResult] = await Promise.all([listCarriers(), listDepartments()])
    carriers.value = carrierResult.items
    departments.value = departmentResult.items
  } catch {
    // Filter dropdowns degrade to "no options"; the keyword/status/date
    // filters still work without them.
  }
})
</script>

<template>
  <section class="search-page">
    <h1 class="search-page__title">
      {{ t('search.title') }}
      <HelpHint :text="t('help.hint.search')" />
    </h1>

    <form
      class="search-page__filters"
      novalidate
      @submit.prevent="onFilterSubmit"
    >
      <AppInput
        v-model="filters.q"
        :label="t('search.keywordLabel')"
      />
      <AppSelect
        v-model="filters.status"
        :label="t('search.statusLabel')"
        :options="statusOptions"
        :placeholder="t('search.anyStatus')"
        placeholder-selectable
      />
      <AppSelect
        v-model="filters.carrierId"
        :label="t('search.carrierLabel')"
        :options="carrierOptions"
        :placeholder="t('search.anyCarrier')"
        placeholder-selectable
      />
      <AppSelect
        v-model="filters.departmentId"
        :label="t('search.departmentLabel')"
        :options="departmentOptions"
        :placeholder="t('search.anyDepartment')"
        placeholder-selectable
      />
      <AppInput
        v-model="filters.dateFrom"
        type="date"
        :label="t('search.dateFromLabel')"
      />
      <AppInput
        v-model="filters.dateTo"
        type="date"
        :label="t('search.dateToLabel')"
      />

      <div class="search-page__filter-actions">
        <AppButton
          type="submit"
          :loading="loading"
        >
          {{ t('search.apply') }}
        </AppButton>
        <AppButton
          type="button"
          variant="ghost"
          @click="resetFilters"
        >
          {{ t('search.reset') }}
        </AppButton>
      </div>
    </form>

    <p
      v-if="loadError"
      class="search-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p
      v-else-if="!loading && items.length === 0"
      class="search-page__empty"
    >
      {{ t('search.empty') }}
    </p>

    <div
      v-if="items.length"
      class="search-page__table-card"
    >
      <table
        class="search-page__table"
      >
        <caption class="search-page__caption">
          {{ t('search.resultsCaption', { total }) }}
        </caption>
        <thead>
          <tr>
            <th scope="col">
              {{ t('search.colItemNo') }}
            </th>
            <th scope="col">
              {{ t('search.colStatus') }}
            </th>
            <th scope="col">
              {{ t('search.colRecipient') }}
            </th>
            <th scope="col">
              {{ t('search.colDepartment') }}
            </th>
            <th scope="col">
              {{ t('search.colCarrier') }}
            </th>
            <th scope="col">
              {{ t('search.colReceivedAt') }}
            </th>
            <th scope="col">
              {{ t('search.colActions') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.id"
          >
            <td :data-label="t('search.colItemNo')">
              {{ item.item_no }}
            </td>
            <td :data-label="t('search.colStatus')">
              <AppBadge
                :status="mailStatusBadgeVariant(item.status)"
                :label="t(mailStatusLabelKey(item.status))"
              />
            </td>
            <td :data-label="t('search.colRecipient')">
              {{ item.recipient_name_raw }}
            </td>
            <td :data-label="t('search.colDepartment')">
              {{ item.department_name ?? '—' }}
            </td>
            <td :data-label="t('search.colCarrier')">
              {{ item.carrier_name ?? '—' }}
            </td>
            <td :data-label="t('search.colReceivedAt')">
              {{ formatDateTime(item.received_at) }}
            </td>
            <td :data-label="t('search.colActions')">
              <button
                type="button"
                class="search-page__detail-btn"
                @click="openDetail(item)"
              >
                {{ t('search.viewDetail') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav
      v-if="items.length"
      class="search-page__pagination"
      :aria-label="t('search.paginationLabel')"
    >
      <AppButton
        variant="ghost"
        :disabled="page <= 1"
        @click="goToPage(page - 1)"
      >
        {{ t('search.prevPage') }}
      </AppButton>
      <span class="search-page__page-indicator">{{ t('search.pageIndicator', { page, totalPages }) }}</span>
      <AppButton
        variant="ghost"
        :disabled="page >= totalPages"
        @click="goToPage(page + 1)"
      >
        {{ t('search.nextPage') }}
      </AppButton>
    </nav>

    <AppDialog
      :open="selectedItem !== null"
      variant="drawer"
      :title="t('search.detailTitle')"
      @close="closeDetail"
    >
      <dl
        v-if="selectedItem"
        class="search-page__detail"
      >
        <dt>{{ t('search.colItemNo') }}</dt>
        <dd>{{ selectedItem.item_no }}</dd>
        <dt>{{ t('search.colStatus') }}</dt>
        <dd>
          <AppBadge
            :status="mailStatusBadgeVariant(selectedItem.status)"
            :label="t(mailStatusLabelKey(selectedItem.status))"
          />
        </dd>
        <dt>{{ t('search.colRecipient') }}</dt>
        <dd>{{ selectedItem.recipient_name_raw }}</dd>
        <dt>{{ t('search.colDepartment') }}</dt>
        <dd>{{ selectedItem.department_name ?? '—' }}</dd>
        <dt>{{ t('search.colCarrier') }}</dt>
        <dd>{{ selectedItem.carrier_name ?? '—' }}</dd>
        <dt>{{ t('inbound.trackingNoLabel') }}</dt>
        <dd>{{ selectedItem.tracking_no ?? '—' }}</dd>
        <dt>{{ t('search.colReceivedAt') }}</dt>
        <dd>{{ formatDateTime(selectedItem.received_at) }}</dd>
        <dt>{{ t('dashboard.readyForPickup') }}</dt>
        <dd>{{ selectedItem.notified_at ? formatDateTime(selectedItem.notified_at) : '—' }}</dd>
        <dt>{{ t('status.pickedUp') }}</dt>
        <dd>{{ selectedItem.picked_up_at ? formatDateTime(selectedItem.picked_up_at) : '—' }}</dd>
        <dt v-if="selectedItem.picked_up_by_name">
          {{ t('pickup.pickedUpByLabel') }}
        </dt>
        <dd v-if="selectedItem.picked_up_by_name">
          {{ selectedItem.picked_up_by_name }}
        </dd>
        <dt v-if="selectedItem.note">
          {{ t('inbound.noteLabel') }}
        </dt>
        <dd v-if="selectedItem.note">
          {{ selectedItem.note }}
        </dd>
      </dl>
    </AppDialog>
  </section>
</template>

<style scoped>
.search-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.search-page__filters {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 var(--space-4);
  margin-bottom: var(--space-3);
}

@media (min-width: 640px) {
  .search-page__filters {
    grid-template-columns: repeat(3, 1fr);
  }
}

.search-page__filter-actions {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

.search-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.search-page__empty {
  color: var(--color-text-muted);
}

.search-page__caption {
  text-align: left;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-2);
}

.search-page__table-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  overflow-x: auto;
}

.search-page__table {
  width: 100%;
  border-collapse: collapse;
  /* M8-2 badges spec "等寬對齊": force every AppBadge in this table's colStatus
     column to the same width regardless of label length. */
  --app-badge-min-width: 112px;
}

.search-page__table th,
.search-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.search-page__detail-btn {
  min-height: var(--touch-target-min);
  min-width: var(--touch-target-min);
  padding: var(--space-1) var(--space-3);
  border: 2px solid var(--brand-primary);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--brand-primary);
  font-weight: 600;
  cursor: pointer;
}

.search-page__pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.search-page__page-indicator {
  color: var(--color-text);
  font-weight: 600;
}

.search-page__detail {
  margin: 0;
}

.search-page__detail dt {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-weight: 600;
  margin-top: var(--space-3);
}

.search-page__detail dd {
  margin: 0;
  color: var(--color-text);
}

/* Mobile card collapse (06 §2 Mobile-first, breakpoint 640): keep the
   <table>/<thead>/<td> semantics for assistive tech, but visually restyle
   each row as a card with the column name shown via data-label. */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .search-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .search-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .search-page__table,
  .search-page__table tbody,
  .search-page__table tr,
  .search-page__table td {
    display: block;
    width: 100%;
  }

  .search-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .search-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .search-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
  }
}
</style>
