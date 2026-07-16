<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppButton from '@/components/AppButton.vue'
import AppBadge from '@/components/AppBadge.vue'
import AppDialog from '@/components/AppDialog.vue'
import EmployeeMatchChips from '@/components/EmployeeMatchChips.vue'
import HelpHint from '@/components/HelpHint.vue'
import OtherFieldInput from '@/components/OtherFieldInput.vue'
import { useDebouncedFn } from '@/composables/useDebouncedFn'
import { isOtherSelected } from '@/composables/useOtherOption'
import { useAuthStore } from '@/stores/auth'
import { listCarriers } from '@/api/carriers'
import { listDepartments } from '@/api/departments'
import { matchEmployees } from '@/api/employees'
import { rankedCandidates, unambiguousBestMatch } from '../matchAutoFill'
import { createOutbound, listOutbound, markOutboundShipped } from '@/api/outbound'
import { uploadPhotos } from '@/api/uploads'
import { createOcrJob, getOcrDraft, getOcrJob } from '@/api/ocr'
import { pollOcrJob } from '@/ocr/pollJob'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import { outboundStatusBadgeVariant, outboundStatusLabelKey } from '@/utils/outboundStatus'
import {
  createEmptyOutboundForm,
  outboundFormToPayload,
  validateOutboundForm,
  type OutboundFormErrors,
} from './outboundForm'
import type { Carrier, Department, EmployeeMatchCandidate, OutboundItem, OutboundPayment, OutboundStatus } from '@/types/api'

// 01 §2.2 交寄(outbound) / §3 「交寄欄位」, 06 §1 「交寄」頁
// (對象 counter/employee: 表單 + 拍託運單). 03 §2 `POST /outbound`,
// `GET /outbound`, `POST /outbound/{id}/shipped`.
const { t } = useI18n({ useScope: 'global' })
const auth = useAuthStore()

// --- Create form ---------------------------------------------------------
const form = reactive(createEmptyOutboundForm())
const errors = ref<OutboundFormErrors>({})
const submitting = ref(false)
const submitError = ref<string | null>(null)
const submitSuccess = ref<string | null>(null)

const carriers = ref<Carrier[]>([])
const departments = ref<Department[]>([])
const matchCandidates = ref<EmployeeMatchCandidate[]>([])
const matchLoading = ref(false)

const carrierOptions = computed(() =>
  carriers.value.map((c) => ({ value: c.id, label: c.name, slug: c.slug })),
)
const departmentOptions = computed(() => departments.value.map((d) => ({ value: d.id, label: d.name })))
const paymentOptions = computed(() =>
  (['company', 'dept_code', 'personal'] satisfies OutboundPayment[]).map((value) => ({
    value,
    label: t(`outbound.payment.${value}`),
  })),
)

// task B: 承運商下拉選到「其他」-> 即時展開下方必填輸入框;換回別的選項時
// 清空,避免殘留的舊值悄悄夾帶進 note -- see InboundRegisterPage.vue's twin
// wiring / src/composables/useOtherOption.ts.
const isOtherCarrier = computed(() => isOtherSelected(form.carrierId, carrierOptions.value))
watch(
  () => form.carrierId,
  () => {
    if (!isOtherCarrier.value) form.otherCarrierName = ''
  },
)

const runMatch = useDebouncedFn(async (query: string) => {
  if (!query.trim()) {
    matchCandidates.value = []
    return
  }
  matchLoading.value = true
  try {
    const candidates = await matchEmployees(query)
    // 01 §5: score >= 90 帶入(單一最佳), 70-90 列候選, <70 留空.
    // 同名同姓兩位都高分時不猜:交寄單掛錯人是查不出來的.
    const strong = rankedCandidates(candidates)
    matchCandidates.value = strong
    const best = unambiguousBestMatch(strong)
    if (best) {
      form.applicantEmployeeId = best.employee_id
    } else if (
      form.applicantEmployeeId &&
      !strong.some((c) => c.employee_id === form.applicantEmployeeId)
    ) {
      form.applicantEmployeeId = null
    }
  } catch {
    matchCandidates.value = []
  } finally {
    matchLoading.value = false
  }
}, 300)

function onApplicantInput(value: string) {
  form.applicantNameRaw = value
  form.applicantEmployeeId = null
  runMatch(value)
}

function onSelectCandidate(employeeId: string | null) {
  form.applicantEmployeeId = employeeId
}

async function onCreateSubmit() {
  submitError.value = null
  submitSuccess.value = null
  const validation = validateOutboundForm(form, { carrierIsOther: isOtherCarrier.value })
  errors.value = validation
  if (Object.keys(validation).length > 0) return

  submitting.value = true
  try {
    const created = await createOutbound(
      outboundFormToPayload(form, {
        carrierIsOther: isOtherCarrier.value,
        otherCarrierNotePrefix: t('otherField.notePrefixCarrier'),
      }),
    )
    submitSuccess.value = t('outbound.submitSuccess', { itemNo: created.item_no })
    const applicantName = auth.user?.display_name ?? ''
    Object.assign(form, createEmptyOutboundForm(), { applicantNameRaw: applicantName })
    matchCandidates.value = []
    errors.value = {}
    await runList()
  } catch (err) {
    submitError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    submitting.value = false
  }
}

// --- List + status filter -------------------------------------------------
const STATUSES: OutboundStatus[] = ['pending', 'shipped', 'delivered', 'exception']
const statusFilter = ref('')
const statusOptions = computed(() =>
  STATUSES.map((s) => ({ value: s, label: t(outboundStatusLabelKey(s)) })),
)

const page = ref(1)
const size = 20
const items = ref<OutboundItem[]>([])
const total = ref(0)
const listLoading = ref(false)
const listError = ref<string | null>(null)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

async function runList() {
  listLoading.value = true
  listError.value = null
  try {
    const result = await listOutbound({
      status: (statusFilter.value || undefined) as OutboundStatus | undefined,
      page: page.value,
      size,
    })
    items.value = result.items
    total.value = result.meta.total
  } catch (err) {
    listError.value = err instanceof ApiError ? err.message : t('errors.generic')
    items.value = []
  } finally {
    listLoading.value = false
  }
}

function onFilterSubmit() {
  page.value = 1
  runList()
}

function resetFilter() {
  statusFilter.value = ''
  page.value = 1
  runList()
}

function goToPage(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
  runList()
}

// --- Mark shipped dialog ---------------------------------------------------
const shippedTarget = ref<OutboundItem | null>(null)
const trackingNoInput = ref('')
const waybillFile = ref<File | null>(null)
const uploadedAttachmentId = ref<string | null>(null)
const ocrRunning = ref(false)
const ocrMessage = ref<string | null>(null)
const shippedSubmitting = ref(false)
const shippedError = ref<string | null>(null)

function openShippedDialog(item: OutboundItem) {
  shippedTarget.value = item
  trackingNoInput.value = item.tracking_no ?? ''
  waybillFile.value = null
  uploadedAttachmentId.value = null
  ocrMessage.value = null
  shippedError.value = null
}

function closeShippedDialog() {
  shippedTarget.value = null
}

function onWaybillFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  waybillFile.value = file
  uploadedAttachmentId.value = null
  ocrMessage.value = null
}

// 01 §2.2 step 2: 拍託運單照片 -> 上傳 -> OCR(可選) 抽單號回填.
async function runWaybillOcr() {
  if (!waybillFile.value) return
  ocrRunning.value = true
  ocrMessage.value = null
  try {
    const uploadResult = await uploadPhotos([
      { localId: 'waybill', blob: waybillFile.value, filename: waybillFile.value.name },
    ])
    const attachmentId = uploadResult.attachmentIds.waybill
    if (!attachmentId) {
      throw uploadResult.failures.waybill ?? new ApiError('UPLOAD_FAILED', t('errors.generic'), 0)
    }
    uploadedAttachmentId.value = attachmentId

    const job = await createOcrJob([attachmentId])
    const result = await pollOcrJob(() => getOcrJob(job.id))
    if (result.status !== 'succeeded') {
      ocrMessage.value = t('outbound.ocrFailed')
      return
    }
    const draft = await getOcrDraft(job.id)
    if (draft.draft.tracking_no) {
      trackingNoInput.value = draft.draft.tracking_no
      ocrMessage.value = t('outbound.ocrSuccess')
    } else {
      ocrMessage.value = t('outbound.ocrFailed')
    }
  } catch (err) {
    ocrMessage.value = err instanceof ApiError ? err.message : t('outbound.ocrFailed')
  } finally {
    ocrRunning.value = false
  }
}

async function confirmShipped() {
  if (!shippedTarget.value) return
  shippedSubmitting.value = true
  shippedError.value = null
  try {
    await markOutboundShipped(shippedTarget.value.id, {
      tracking_no: trackingNoInput.value.trim() || undefined,
      attachment_id: uploadedAttachmentId.value || undefined,
    })
    closeShippedDialog()
    await runList()
  } catch (err) {
    shippedError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    shippedSubmitting.value = false
  }
}

onMounted(async () => {
  const applicantName = auth.user?.display_name ?? ''
  form.applicantNameRaw = applicantName
  // M4-R1: 自己幫自己開交寄單時,申請人身分是已知的——用 /auth/me 回的
  // employee_id 直接帶入,不要拿自己的名字去模糊比對猜自己是誰.
  form.applicantEmployeeId = auth.user?.employee_id ?? null

  runList()
  try {
    const [carrierResult, departmentResult] = await Promise.all([listCarriers(), listDepartments()])
    carriers.value = carrierResult.items
    departments.value = departmentResult.items
    // ASSUMPTION (flag for reviewer): AuthUser only carries the linked
    // employee's department *name* (app/api/v1/auth.py `_user_public`), not
    // its id — best-effort resolve it against the loaded department list so
    // "部門自動帶入" works without requiring a backend contract change; the
    // field stays editable if this can't find an exact name match.
    if (auth.user?.department) {
      const match = departments.value.find((d) => d.name === auth.user?.department)
      if (match) form.departmentId = match.id
    }
  } catch {
    // Carrier/department dropdowns degrade to "no options"; both fields are
    // optional so the form can still be submitted.
  }
  if (applicantName) runMatch(applicantName)
})
</script>

<template>
  <section class="outbound-page">
    <h1 class="outbound-page__title">
      {{ t('outbound.title') }}
      <HelpHint :text="t('help.hint.outbound')" />
    </h1>

    <section class="outbound-page__create">
      <h2 class="outbound-page__section-title">
        {{ t('outbound.createTitle') }}
      </h2>

      <p
        v-if="submitSuccess"
        class="outbound-page__success"
        role="status"
      >
        {{ submitSuccess }}
      </p>
      <p
        v-if="submitError"
        class="outbound-page__error"
        role="alert"
      >
        {{ submitError }}
      </p>

      <form
        class="outbound-page__create-form"
        novalidate
        @submit.prevent="onCreateSubmit"
      >
        <div class="outbound-page__applicant">
          <div class="outbound-page__field-with-hint">
            <AppInput
              :model-value="form.applicantNameRaw"
              :label="t('outbound.applicantLabel')"
              :hint="matchLoading ? t('outbound.applicantMatchLoading') : t('outbound.applicantHint')"
              required
              @update:model-value="onApplicantInput"
            />
            <HelpHint :text="t('help.hint.outboundApplicantMatch')" />
          </div>
          <EmployeeMatchChips
            :candidates="matchCandidates"
            :model-value="form.applicantEmployeeId"
            @update:model-value="onSelectCandidate"
          />
          <p
            v-if="form.applicantEmployeeId"
            class="outbound-page__matched"
            role="status"
          >
            {{ t('outbound.applicantMatched') }}
          </p>
        </div>

        <AppSelect
          v-model="form.departmentId"
          :label="t('outbound.departmentLabel')"
          :options="departmentOptions"
          :placeholder="t('outbound.departmentPlaceholder')"
        />

        <AppInput
          v-model="form.toName"
          :label="t('outbound.toNameLabel')"
          :placeholder="t('outbound.toNamePlaceholder')"
          :error="errors.toName ? t(errors.toName) : null"
          required
        />
        <AppInput
          v-model="form.toOrg"
          :label="t('outbound.toOrgLabel')"
          :error="errors.toOrg ? t(errors.toOrg) : null"
        />
        <AppInput
          v-model="form.toAddress"
          :label="t('outbound.toAddressLabel')"
          :error="errors.toAddress ? t(errors.toAddress) : null"
        />
        <AppInput
          v-model="form.toPhone"
          :label="t('outbound.toPhoneLabel')"
          :error="errors.toPhone ? t(errors.toPhone) : null"
        />

        <div class="outbound-page__field-with-hint">
          <AppSelect
            v-model="form.carrierId"
            :label="t('outbound.carrierLabel')"
            :options="carrierOptions"
            :placeholder="t('outbound.carrierPlaceholder')"
          />
          <HelpHint :text="t('help.hint.outboundCarrier')" />
        </div>
        <OtherFieldInput
          v-model="form.otherCarrierName"
          :show="isOtherCarrier"
          :label="t('otherField.carrierLabel')"
          :error="errors.otherCarrierName ? t(errors.otherCarrierName) : null"
        />

        <div class="outbound-page__field-with-hint">
          <AppSelect
            v-model="form.payment"
            :label="t('outbound.paymentLabel')"
            :options="paymentOptions"
            :placeholder="t('outbound.paymentPlaceholder')"
          />
          <HelpHint :text="t('help.hint.outboundPayment')" />
        </div>

        <AppInput
          v-model="form.cost"
          type="number"
          :label="t('outbound.costLabel')"
          :error="errors.cost ? t(errors.cost) : null"
        />

        <AppInput
          v-model="form.note"
          :label="t('outbound.noteLabel')"
          :error="errors.note ? t(errors.note) : null"
        />

        <AppButton
          type="submit"
          :loading="submitting"
          full-width
        >
          {{ t('outbound.submit') }}
        </AppButton>
      </form>
    </section>

    <section class="outbound-page__list">
      <h2 class="outbound-page__section-title">
        {{ t('outbound.listTitle') }}
      </h2>

      <form
        class="outbound-page__filters"
        novalidate
        @submit.prevent="onFilterSubmit"
      >
        <AppSelect
          v-model="statusFilter"
          :label="t('outbound.filterStatusLabel')"
          :options="statusOptions"
          :placeholder="t('outbound.anyStatus')"
          placeholder-selectable
        />
        <div class="outbound-page__filter-actions">
          <AppButton
            type="submit"
            :loading="listLoading"
          >
            {{ t('outbound.filterApply') }}
          </AppButton>
          <AppButton
            type="button"
            variant="ghost"
            @click="resetFilter"
          >
            {{ t('outbound.filterReset') }}
          </AppButton>
        </div>
      </form>

      <p
        v-if="listError"
        class="outbound-page__error"
        role="alert"
      >
        {{ listError }}
      </p>
      <p
        v-else-if="!listLoading && items.length === 0"
        class="outbound-page__empty"
      >
        {{ t('outbound.empty') }}
      </p>

      <div
        v-if="items.length"
        class="outbound-page__table-card"
      >
        <table class="outbound-page__table">
          <caption class="outbound-page__caption">
            {{ t('outbound.resultsCaption', { total }) }}
          </caption>
          <thead>
            <tr>
              <th scope="col">
                {{ t('outbound.colItemNo') }}
              </th>
              <th scope="col">
                {{ t('outbound.colApplicant') }}
              </th>
              <th scope="col">
                {{ t('outbound.colRecipient') }}
              </th>
              <th scope="col">
                {{ t('outbound.colDepartment') }}
              </th>
              <th scope="col">
                {{ t('outbound.colCarrier') }}
              </th>
              <th scope="col">
                {{ t('outbound.colStatus') }}
              </th>
              <th scope="col">
                {{ t('outbound.colShippedAt') }}
              </th>
              <th scope="col">
                {{ t('outbound.colActions') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in items"
              :key="item.id"
            >
              <td :data-label="t('outbound.colItemNo')">
                {{ item.item_no }}
              </td>
              <td :data-label="t('outbound.colApplicant')">
                {{ item.applicant_name ?? '—' }}
              </td>
              <td :data-label="t('outbound.colRecipient')">
                {{ item.to_name ?? '—' }}
              </td>
              <td :data-label="t('outbound.colDepartment')">
                {{ item.department_name ?? '—' }}
              </td>
              <td :data-label="t('outbound.colCarrier')">
                {{ item.carrier_name ?? '—' }}
              </td>
              <td :data-label="t('outbound.colStatus')">
                <AppBadge
                  :status="outboundStatusBadgeVariant(item.status)"
                  :label="t(outboundStatusLabelKey(item.status))"
                />
              </td>
              <td :data-label="t('outbound.colShippedAt')">
                {{ item.shipped_at ? formatDateTime(item.shipped_at) : '—' }}
              </td>
              <td :data-label="t('outbound.colActions')">
                <AppButton
                  v-if="item.status === 'pending'"
                  variant="secondary"
                  @click="openShippedDialog(item)"
                >
                  {{ t('outbound.markShipped') }}
                </AppButton>
                <span v-else>—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <nav
        v-if="items.length"
        class="outbound-page__pagination"
        :aria-label="t('outbound.paginationLabel')"
      >
        <AppButton
          variant="ghost"
          :disabled="page <= 1"
          @click="goToPage(page - 1)"
        >
          {{ t('outbound.prevPage') }}
        </AppButton>
        <span class="outbound-page__page-indicator">{{ t('outbound.pageIndicator', { page, totalPages }) }}</span>
        <AppButton
          variant="ghost"
          :disabled="page >= totalPages"
          @click="goToPage(page + 1)"
        >
          {{ t('outbound.nextPage') }}
        </AppButton>
      </nav>
    </section>

    <AppDialog
      :open="shippedTarget !== null"
      :title="t('outbound.shippedDialogTitle')"
      @close="closeShippedDialog"
    >
      <template v-if="shippedTarget">
        <div class="outbound-page__field-with-hint">
          <AppInput
            v-model="trackingNoInput"
            :label="t('outbound.trackingNoLabel')"
            :placeholder="t('outbound.trackingNoPlaceholder')"
            :hint="t('outbound.trackingNoHint')"
          />
          <HelpHint :text="t('help.hint.outboundTrackingNo')" />
        </div>

        <div class="outbound-page__waybill">
          <label
            class="outbound-page__waybill-label"
            for="outbound-waybill-photo"
          >{{ t('outbound.photoLabel') }}</label>
          <input
            id="outbound-waybill-photo"
            type="file"
            accept="image/*"
            capture="environment"
            @change="onWaybillFileChange"
          >
          <AppButton
            type="button"
            variant="secondary"
            :disabled="!waybillFile"
            :loading="ocrRunning"
            @click="runWaybillOcr"
          >
            {{ t('outbound.runOcr') }}
          </AppButton>
          <p
            v-if="ocrMessage"
            role="status"
            class="outbound-page__ocr-message"
          >
            {{ ocrMessage }}
          </p>
        </div>

        <p
          v-if="shippedError"
          class="outbound-page__error"
          role="alert"
        >
          {{ shippedError }}
        </p>
      </template>

      <template #footer>
        <AppButton
          variant="ghost"
          @click="closeShippedDialog"
        >
          {{ t('common.cancel') }}
        </AppButton>
        <AppButton
          :loading="shippedSubmitting"
          @click="confirmShipped"
        >
          {{ t('outbound.confirmShipped') }}
        </AppButton>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.outbound-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.outbound-page__field-with-hint {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
}

.outbound-page__field-with-hint > :first-child {
  flex: 1;
  min-width: 0;
}

.outbound-page__section-title {
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: 0 0 var(--space-4);
}

.outbound-page__create {
  max-width: 640px;
  margin-bottom: var(--space-7);
}

.outbound-page__applicant {
  margin-bottom: var(--space-2);
}

.outbound-page__matched {
  margin: 0 0 var(--space-4);
  color: var(--color-success-text);
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.outbound-page__success {
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-subtle);
  color: var(--color-text);
  font-weight: 600;
}

.outbound-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

.outbound-page__filters {
  display: flex;
  align-items: flex-end;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
  max-width: 480px;
}

.outbound-page__filter-actions {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.outbound-page__empty {
  color: var(--color-text-muted);
}

.outbound-page__caption {
  text-align: left;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-2);
}

.outbound-page__table-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  overflow-x: auto;
}

.outbound-page__table {
  width: 100%;
  border-collapse: collapse;
  /* M8-2 badges spec "等寬對齊": same-width AppBadge in the colStatus column. */
  --app-badge-min-width: 112px;
}

.outbound-page__table th,
.outbound-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.outbound-page__pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.outbound-page__page-indicator {
  color: var(--color-text);
  font-weight: 600;
}

.outbound-page__waybill {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  margin: var(--space-2) 0 var(--space-4);
}

.outbound-page__waybill-label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.outbound-page__ocr-message {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

/* Mobile card collapse — same pattern as SearchPage.vue. */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .outbound-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .outbound-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .outbound-page__table,
  .outbound-page__table tbody,
  .outbound-page__table tr,
  .outbound-page__table td {
    display: block;
    width: 100%;
  }

  .outbound-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .outbound-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .outbound-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
  }
}

@media (min-width: 1024px) {
  .outbound-page__create {
    max-width: 960px;
  }
  .outbound-page__create-form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    column-gap: var(--space-4);
    align-items: start;
  }
  .outbound-page__create-form > .outbound-page__applicant,
  .outbound-page__create-form > .outbound-page__matched,
  .outbound-page__create-form > .app-button {
    grid-column: 1 / -1;
  }
}
</style>
