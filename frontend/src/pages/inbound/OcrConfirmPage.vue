<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppToggle from '@/components/AppToggle.vue'
import AppButton from '@/components/AppButton.vue'
import EmployeeMatchChips from '@/components/EmployeeMatchChips.vue'
import HelpHint from '@/components/HelpHint.vue'
import { useDebouncedFn } from '@/composables/useDebouncedFn'
import { isFeatureEnabled } from '@/branding'
import { listCarriers } from '@/api/carriers'
import { matchEmployees } from '@/api/employees'
import { createItem } from '@/api/items'
import { getOcrDraft, getOcrJob } from '@/api/ocr'
import { getUploadUrl } from '@/api/uploads'
import { formatDateTime } from '@/utils/format'
import { pollOcrJob } from '@/ocr/pollJob'
import { ApiError } from '@/api/client'
import { useOcrConfirmQueueStore } from '@/stores/ocrConfirmQueue'
import {
  createEmptyInboundForm,
  inboundFormToPayload,
  validateInboundForm,
  type InboundFormErrors,
} from './inboundForm'
import { createFormFromOcrDraft, lowConfidenceFields, type OcrConfirmFieldKey } from './ocrConfirmForm'
import { rankedCandidates, unambiguousBestMatch } from '../matchAutoFill'
import type { Carrier, DepartmentMatchCandidate, EmployeeMatchCandidate, MailType, OcrDraftFields, RefrigerationType } from '@/types/api'

// 06-UI-UX.md §1 OCR 確認頁: 左圖右表(手機上下堆疊)、欄位可改、員工比對候選
// chips、信心低欄位標黃。輪詢見 03 §2 GET /ocr/jobs/{id}(task brief: 2s 間隔
// / 60s 上限 — src/ocr/pollJob.ts).
const { t } = useI18n({ useScope: 'global' })
const router = useRouter()
const queue = useOcrConfirmQueueStore()

type PollStatus = 'polling' | 'succeeded' | 'failed' | 'timeout'
const pollStatus = ref<PollStatus>('polling')
// The real backend job.error (rate limit / quota / provider message), shown
// on failure so the counter/admin sees *why* AI failed, not just "failed".
const failureReason = ref<string | null>(null)
const lowConfidence = ref<OcrConfirmFieldKey[]>([])
// FE-STABILITY: per-attachment-id "this photo failed to load" flag, shown
// as fallback text instead of a broken <img> (06 §3 colour/text pairing
// convention extended to failure states too).
const photoLoadErrors = reactive<Record<string, boolean>>({})

/**
 * EXIF capture time for a photo, formatted in Taipei time. Empty string when
 * the photo carried no EXIF (screenshots, re-saved images) or when the job
 * came from a client that didn't record one -- the caption is then omitted
 * rather than showing a placeholder, since "no capture time" is a normal,
 * uninteresting case and a dash next to every photo is just noise.
 */
function capturedAtLabel(attachmentId: string): string {
  const iso = currentJob.value?.capturedAt?.[attachmentId]
  return iso ? formatDateTime(iso) : ''
}

const form = reactive(createEmptyInboundForm())
const errors = ref<InboundFormErrors>({})
const submitting = ref(false)
const submitError = ref<string | null>(null)
const submitSuccess = ref<string | null>(null)

const carriers = ref<Carrier[]>([])
const matchCandidates = ref<EmployeeMatchCandidate[]>([])
// 部門件 (A): departments whose contact person this item can be routed to.
const departmentCandidates = ref<DepartmentMatchCandidate[]>([])
const selectedDepartmentName = ref<string | null>(null)
const matchLoading = ref(false)

const currentJob = computed(() => queue.current)
const remainingCount = computed(() => queue.remaining)

const mailTypeOptions = computed(() =>
  (['letter', 'document', 'parcel', 'box', 'pallet'] satisfies MailType[]).map((value) => ({
    value,
    label: t(`inbound.mailType.${value}`),
  })),
)
const refrigerationOptions = computed(() =>
  (['none', 'chilled', 'frozen'] satisfies RefrigerationType[]).map((value) => ({
    value,
    label: t(`inbound.refrigeration.${value}`),
  })),
)
const carrierOptions = computed(() => carriers.value.map((c) => ({ value: c.id, label: c.name })))

const showConfidential = isFeatureEnabled('confidential')
const showCod = isFeatureEnabled('cod')
const showRefrigeration = isFeatureEnabled('refrigeration')

function isLow(key: OcrConfirmFieldKey): boolean {
  return lowConfidence.value.includes(key)
}

function onPhotoError(attachmentId: string) {
  photoLoadErrors[attachmentId] = true
}

async function loadJob() {
  const job = currentJob.value
  submitError.value = null
  submitSuccess.value = null
  if (!job) return

  pollStatus.value = 'polling'
  failureReason.value = null
  Object.assign(form, createEmptyInboundForm())
  errors.value = {}
  matchCandidates.value = []
  departmentCandidates.value = []
  selectedDepartmentName.value = null
  lowConfidence.value = []
  for (const key of Object.keys(photoLoadErrors)) delete photoLoadErrors[key]

  const result = await pollOcrJob(() => getOcrJob(job.jobId))
  if (result.status === 'timeout') {
    pollStatus.value = 'timeout'
    return
  }
  if (result.status === 'failed') {
    failureReason.value = result.job.error ?? null
    pollStatus.value = 'failed'
    return
  }

  try {
    const draft = await getOcrDraft(job.jobId)
    matchCandidates.value = draft.employee_candidates ?? []
    departmentCandidates.value = draft.department_candidates ?? []
    const filled = createFormFromOcrDraft(draft.draft, job.barcodeHint, carriers.value)
    Object.assign(form, filled)
    lowConfidence.value = lowConfidenceFields(draft.draft as OcrDraftFields, form, job.barcodeHint)

    // 01 §5: score >= 90 帶入(單一最佳). 有兩位同分/同樣高分時不猜——
    // 猜錯就是把別人的信通知給錯的人.
    const best = unambiguousBestMatch(matchCandidates.value)
    if (best) {
      form.recipientEmployeeId = best.employee_id
    }
    pollStatus.value = 'succeeded'
  } catch {
    pollStatus.value = 'failed'
  }
}

onMounted(async () => {
  try {
    const result = await listCarriers()
    carriers.value = result.items
  } catch {
    carriers.value = []
  }
  await loadJob()
})

watch(
  () => queue.current?.jobId,
  (jobId, previousId) => {
    if (jobId && jobId !== previousId) void loadJob()
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
    const strong = rankedCandidates(candidates)
    matchCandidates.value = strong
    const best = unambiguousBestMatch(strong)
    if (best) {
      form.recipientEmployeeId = best.employee_id
    } else if (form.recipientEmployeeId && !strong.some((c) => c.employee_id === form.recipientEmployeeId)) {
      form.recipientEmployeeId = null
    }
  } catch {
    matchCandidates.value = []
  } finally {
    matchLoading.value = false
  }
}, 300)

function onRecipientInput(value: string) {
  form.recipientNameRaw = value
  form.recipientEmployeeId = null
  // Hand-editing the recipient means it is no longer a routed 部門件.
  form.departmentId = null
  selectedDepartmentName.value = null
  lowConfidence.value = lowConfidence.value.filter((k) => k !== 'recipientNameRaw')
  runMatch(value)
}

function onSelectCandidate(employeeId: string | null) {
  form.recipientEmployeeId = employeeId
  // Picking a specific employee makes it a personal item, not a 部門件.
  form.departmentId = null
  selectedDepartmentName.value = null
}

// 部門件: route to the department's contact person. Setting recipientEmployeeId
// to the manager makes the existing notify / my-mail / pickup flow deliver it
// to that contact, and the backend derives department_id from the employee.
function onSelectDepartment(dept: DepartmentMatchCandidate) {
  if (!dept.manager_employee_id) return
  form.recipientEmployeeId = dept.manager_employee_id
  form.departmentId = dept.department_id
  form.recipientNameRaw = dept.name
  selectedDepartmentName.value = dept.name
  matchCandidates.value = []
}

async function advanceQueue() {
  queue.advance()
  if (queue.remaining > 0) {
    await loadJob()
  } else {
    router.push({ name: 'dashboard' })
  }
}

async function onConfirm() {
  const job = currentJob.value
  if (!job) return
  submitError.value = null
  const validation = validateInboundForm(form)
  errors.value = validation
  if (Object.keys(validation).length > 0) return

  submitting.value = true
  try {
    const item = await createItem({
      ...inboundFormToPayload(form),
      ocr_job_id: job.jobId,
      attachment_ids: job.attachmentIds,
    })
    submitSuccess.value = t('inbound.confirm.submitSuccess', { itemNo: item.item_no })
    await advanceQueue()
  } catch (err) {
    submitError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    submitting.value = false
  }
}

async function onSkip() {
  if (!currentJob.value) return
  await advanceQueue()
}
</script>

<template>
  <section class="ocr-confirm-page">
    <p class="ocr-confirm-page__step">
      {{ t('inbound.confirm.step') }}
    </p>
    <h1 class="ocr-confirm-page__title">
      {{ t('inbound.confirm.title') }}
      <HelpHint :text="t('help.hint.ocrConfirm')" />
    </h1>

    <p
      v-if="submitSuccess"
      class="ocr-confirm-page__success"
      role="status"
    >
      {{ submitSuccess }}
    </p>

    <div v-if="!currentJob">
      <p>{{ t('inbound.confirm.empty') }}</p>
      <router-link
        class="ocr-confirm-page__link"
        :to="{ name: 'inbound-photo' }"
      >
        {{ t('inbound.camera.title') }}
      </router-link>
    </div>

    <template v-else>
      <p
        class="ocr-confirm-page__queue-status"
        role="status"
        aria-live="polite"
      >
        {{ t('inbound.confirm.queueStatus', { remaining: remainingCount }) }}
      </p>

      <p
        v-if="pollStatus === 'polling'"
        role="status"
        aria-live="polite"
        class="ocr-confirm-page__polling"
      >
        {{ t('inbound.confirm.polling') }}
      </p>

      <div
        v-if="pollStatus === 'timeout'"
        class="ocr-confirm-page__timeout"
        role="alert"
      >
        <p>{{ t('inbound.confirm.timeout') }}</p>
        <AppButton
          variant="secondary"
          @click="loadJob"
        >
          {{ t('common.retry') }}
        </AppButton>
      </div>

      <p
        v-if="pollStatus === 'failed'"
        class="ocr-confirm-page__failed"
        role="alert"
      >
        {{ t('inbound.confirm.failed') }}
        <span
          v-if="failureReason"
          class="ocr-confirm-page__failed-reason"
        >{{ failureReason }}</span>
      </p>

      <div
        v-if="pollStatus === 'succeeded' || pollStatus === 'failed'"
        class="ocr-confirm-page__layout"
      >
        <div class="ocr-confirm-page__photos-panel">
          <div class="ocr-confirm-page__photos">
            <div
              v-for="attachmentId in currentJob.attachmentIds"
              :key="attachmentId"
              class="ocr-confirm-page__photo-slot"
            >
              <img
                v-if="!photoLoadErrors[attachmentId]"
                :src="getUploadUrl(attachmentId)"
                :alt="t('inbound.camera.photoAlt')"
                class="ocr-confirm-page__photo"
                @error="onPhotoError(attachmentId)"
              >
              <p
                v-else
                class="ocr-confirm-page__photo-error"
                role="alert"
              >
                {{ t('inbound.confirm.photoLoadError') }}
              </p>
              <p
                v-if="capturedAtLabel(attachmentId)"
                class="ocr-confirm-page__photo-captured"
              >
                {{ t('inbound.confirm.capturedAt', { time: capturedAtLabel(attachmentId) }) }}
              </p>
            </div>
          </div>
        </div>

        <form
          novalidate
          class="ocr-confirm-page__form"
          @submit.prevent="onConfirm"
        >
          <p
            v-if="submitError"
            class="ocr-confirm-page__error"
            role="alert"
          >
            {{ submitError }}
          </p>

          <AppSelect
            v-model="form.mailType"
            :label="t('inbound.mailTypeLabel')"
            :options="mailTypeOptions"
            :placeholder="t('inbound.mailTypePlaceholder')"
            :error="errors.mailType ? t(errors.mailType) : null"
            required
          />

          <div :class="{ 'ocr-confirm-page__field--low-confidence': isLow('carrierId') }">
            <AppSelect
              v-model="form.carrierId"
              :label="t('inbound.carrierLabel')"
              :options="carrierOptions"
              :placeholder="t('inbound.carrierPlaceholder')"
              :hint="isLow('carrierId') ? t('inbound.confirm.lowConfidenceHint') : null"
            />
          </div>

          <div :class="{ 'ocr-confirm-page__field--low-confidence': isLow('trackingNo') }">
            <AppInput
              v-model="form.trackingNo"
              :label="t('inbound.trackingNoLabel')"
              :error="errors.trackingNo ? t(errors.trackingNo) : null"
              :hint="isLow('trackingNo') ? t('inbound.confirm.lowConfidenceHint') : null"
            />
          </div>

          <div :class="{ 'ocr-confirm-page__field--low-confidence': isLow('senderName') }">
            <AppInput
              v-model="form.senderName"
              :label="t('inbound.senderNameLabel')"
              :error="errors.senderName ? t(errors.senderName) : null"
              :hint="isLow('senderName') ? t('inbound.confirm.lowConfidenceHint') : null"
            />
          </div>
          <div :class="{ 'ocr-confirm-page__field--low-confidence': isLow('senderOrg') }">
            <AppInput
              v-model="form.senderOrg"
              :label="t('inbound.senderOrgLabel')"
              :error="errors.senderOrg ? t(errors.senderOrg) : null"
              :hint="isLow('senderOrg') ? t('inbound.confirm.lowConfidenceHint') : null"
            />
          </div>

          <div
            class="ocr-confirm-page__recipient"
            :class="{ 'ocr-confirm-page__field--low-confidence': isLow('recipientNameRaw') }"
          >
            <AppInput
              :model-value="form.recipientNameRaw"
              :label="t('inbound.recipientLabel')"
              :error="errors.recipientNameRaw ? t(errors.recipientNameRaw) : null"
              :hint="matchLoading ? t('inbound.matchLoading') : (isLow('recipientNameRaw') ? t('inbound.confirm.lowConfidenceHint') : null)"
              required
              @update:model-value="onRecipientInput"
            />
            <EmployeeMatchChips
              :candidates="matchCandidates"
              :model-value="form.recipientEmployeeId"
              @update:model-value="onSelectCandidate"
            />
            <p
              v-if="form.recipientEmployeeId"
              class="ocr-confirm-page__matched"
              role="status"
            >
              {{ t('inbound.matchSelected') }}
            </p>
          </div>

          <div
            v-if="departmentCandidates.length"
            class="ocr-confirm-page__dept"
          >
            <p class="ocr-confirm-page__dept-label">
              {{ t('inbound.confirm.deptSectionLabel') }}
            </p>
            <div class="ocr-confirm-page__dept-list">
              <button
                v-for="d in departmentCandidates"
                :key="d.department_id"
                type="button"
                class="ocr-confirm-page__dept-btn"
                :disabled="!d.manager_employee_id"
                @click="onSelectDepartment(d)"
              >
                <strong>{{ d.name }}</strong>
                <span v-if="d.manager_employee_id">{{ t('inbound.confirm.deptContact', { name: d.manager_name || d.name }) }}</span>
                <span v-else>{{ t('inbound.confirm.deptNoContact') }}</span>
              </button>
            </div>
            <p
              v-if="selectedDepartmentName"
              class="ocr-confirm-page__dept-set"
              role="status"
            >
              {{ t('inbound.confirm.deptSet', { name: selectedDepartmentName }) }}
            </p>
          </div>

          <AppToggle
            v-if="showConfidential"
            v-model="form.isConfidential"
            :label="t('inbound.confidentialLabel')"
            :hint="t('inbound.confidentialHint')"
          />
          <AppToggle
            v-if="showCod"
            v-model="form.isCod"
            :label="t('inbound.codLabel')"
          />
          <AppInput
            v-if="showCod && form.isCod"
            v-model="form.codAmount"
            type="number"
            :label="t('inbound.codAmountLabel')"
            :error="errors.codAmount ? t(errors.codAmount) : null"
            required
          />

          <AppSelect
            v-if="showRefrigeration"
            v-model="form.refrigeration"
            :label="t('inbound.refrigerationLabel')"
            :options="refrigerationOptions"
          />

          <AppInput
            v-model="form.sizeNote"
            :label="t('inbound.sizeNoteLabel')"
          />
          <AppInput
            v-model="form.note"
            :label="t('inbound.noteLabel')"
            :error="errors.note ? t(errors.note) : null"
          />

          <div class="ocr-confirm-page__buttons">
            <AppButton
              type="submit"
              :loading="submitting"
            >
              {{ t('inbound.confirm.confirmButton') }}
            </AppButton>
            <AppButton
              type="button"
              variant="ghost"
              :disabled="submitting"
              @click="onSkip"
            >
              {{ t('inbound.confirm.skip') }}
            </AppButton>
          </div>
        </form>
      </div>
    </template>
  </section>
</template>

<style scoped>
.ocr-confirm-page {
  max-width: 960px;
}

.ocr-confirm-page__step {
  margin: 0 0 var(--space-2);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.ocr-confirm-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.ocr-confirm-page__queue-status {
  color: var(--color-text-muted);
  margin: 0 0 var(--space-3);
}

.ocr-confirm-page__polling {
  font-weight: 600;
  color: var(--color-text);
}

.ocr-confirm-page__timeout,
.ocr-confirm-page__failed {
  color: var(--color-danger-text);
  font-weight: 600;
}

.ocr-confirm-page__failed-reason {
  display: block;
  margin-top: var(--space-1);
  font-weight: 400;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  word-break: break-word;
}

.ocr-confirm-page__success {
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-subtle);
  color: var(--color-text);
  font-weight: 600;
}

.ocr-confirm-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

.ocr-confirm-page__layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-5);
}

@media (min-width: 640px) {
  .ocr-confirm-page__layout {
    grid-template-columns: 320px 1fr;
  }
}

.ocr-confirm-page__photos-panel {
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-subtle);
  height: fit-content;
}

.ocr-confirm-page__photos {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: var(--space-2);
}

@media (min-width: 640px) {
  .ocr-confirm-page__photos {
    flex-direction: column;
  }
}

.ocr-confirm-page__photo-slot {
  width: 100%;
  max-width: 320px;
}

.ocr-confirm-page__photo {
  width: 100%;
  max-width: 320px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  object-fit: contain;
}

.ocr-confirm-page__photo-captured {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.ocr-confirm-page__photo-error {
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 1px dashed var(--color-border);
  color: var(--color-danger-text);
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.ocr-confirm-page__link {
  color: var(--brand-primary);
  font-weight: 600;
}

.ocr-confirm-page__form {
  padding: var(--space-5);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.ocr-confirm-page__recipient {
  margin-bottom: var(--space-2);
}

.ocr-confirm-page__matched {
  margin: 0 0 var(--space-4);
  color: var(--color-success-text);
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.ocr-confirm-page__dept {
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.ocr-confirm-page__dept-label {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.ocr-confirm-page__dept-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ocr-confirm-page__dept-btn {
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-elevated);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.ocr-confirm-page__dept-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ocr-confirm-page__dept-set {
  margin: var(--space-2) 0 0;
  color: var(--color-success-text);
  font-weight: 600;
  font-size: var(--font-size-sm);
}

/* 06 §3: colour is never the only signal — the hint text next to each
   low-confidence field ("信心偏低,請確認") always accompanies this highlight.
   POLISH-AUDIT.md Should-fix #9: --oi-yellow is a light fill meant to always
   pair with black text (see tokens.css); this container previously relied
   on inherited `color`, which in dark mode resolves to --color-text
   (#f2f2f2, near-white) -- unreadable on the yellow background. Force black
   explicitly rather than depending on inheritance not changing later. */
.ocr-confirm-page__field--low-confidence {
  background-color: var(--oi-yellow);
  color: #000;
  padding: var(--space-2);
  border-radius: var(--radius-md);
}

.ocr-confirm-page__buttons {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
