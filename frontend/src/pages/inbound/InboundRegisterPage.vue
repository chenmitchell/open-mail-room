<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppToggle from '@/components/AppToggle.vue'
import AppButton from '@/components/AppButton.vue'
import EmployeeMatchChips from '@/components/EmployeeMatchChips.vue'
import HelpHint from '@/components/HelpHint.vue'
import OtherFieldInput from '@/components/OtherFieldInput.vue'
import { useDebouncedFn } from '@/composables/useDebouncedFn'
import { isOtherSelected } from '@/composables/useOtherOption'
import { isFeatureEnabled } from '@/branding'
import { listCarriers } from '@/api/carriers'
import { matchEmployees } from '@/api/employees'
import { rankedCandidates, unambiguousBestMatch } from '../matchAutoFill'
import { createItem } from '@/api/items'
import { ApiError } from '@/api/client'
import {
  createEmptyInboundForm,
  inboundFormToPayload,
  validateInboundForm,
  type InboundFormErrors,
} from './inboundForm'
import type { Carrier, EmployeeMatchCandidate, MailType, RefrigerationType } from '@/types/api'

const { t } = useI18n({ useScope: 'global' })

const form = reactive(createEmptyInboundForm())
const errors = ref<InboundFormErrors>({})
const submitting = ref(false)
const submitError = ref<string | null>(null)
const submitSuccess = ref<string | null>(null)

const carriers = ref<Carrier[]>([])
const matchCandidates = ref<EmployeeMatchCandidate[]>([])
const matchLoading = ref(false)

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

const carrierOptions = computed(() =>
  carriers.value.map((c) => ({ value: c.id, label: c.name, slug: c.slug })),
)

// task B: 承運商下拉選到「其他」(seed slug='other'/name='其他') -> 即時展開
// 下方必填輸入框;承運商換回別的選項時清空,避免殘留的舊值悄悄夾帶進 note。
const isOtherCarrier = computed(() => isOtherSelected(form.carrierId, carrierOptions.value))
watch(
  () => form.carrierId,
  () => {
    if (!isOtherCarrier.value) form.otherCarrierName = ''
  },
)

const showConfidential = isFeatureEnabled('confidential')
const showCod = isFeatureEnabled('cod')
const showRefrigeration = isFeatureEnabled('refrigeration')

onMounted(async () => {
  try {
    const result = await listCarriers()
    carriers.value = result.items
  } catch {
    // Carrier dropdown degrades to "no options"; carrier is an optional
    // field (01 §3 選填) so registration can still proceed without it.
    carriers.value = []
  }
})

const runMatch = useDebouncedFn(async (query: string) => {
  if (!query.trim()) {
    matchCandidates.value = []
    return
  }
  matchLoading.value = true
  try {
    const candidates = await matchEmployees(query)
    // 01 §5: score >= 90 帶入(單一最佳), 70-90 列候選, <70 留空。
    // 「單一」是重點:同名同姓兩位都高分時交給人選,不由程式決定。
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
  runMatch(value)
}

function onSelectCandidate(employeeId: string | null) {
  form.recipientEmployeeId = employeeId
}

async function onSubmit() {
  submitError.value = null
  submitSuccess.value = null
  const validation = validateInboundForm(form, { carrierIsOther: isOtherCarrier.value })
  errors.value = validation
  if (Object.keys(validation).length > 0) return

  submitting.value = true
  try {
    const item = await createItem(
      inboundFormToPayload(form, {
        carrierIsOther: isOtherCarrier.value,
        otherCarrierNotePrefix: t('otherField.notePrefixCarrier'),
      }),
    )
    submitSuccess.value = t('inbound.submitSuccess', { itemNo: item.item_no })
    Object.assign(form, createEmptyInboundForm())
    matchCandidates.value = []
    errors.value = {}
  } catch (err) {
    submitError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="inbound-register-page">
    <h1 class="inbound-register-page__title">
      {{ t('inbound.title') }}
      <HelpHint :text="t('help.hint.inboundRegister')" />
    </h1>

    <p
      v-if="submitSuccess"
      class="inbound-register-page__success"
      role="status"
    >
      {{ submitSuccess }}
    </p>
    <p
      v-if="submitError"
      class="inbound-register-page__error"
      role="alert"
    >
      {{ submitError }}
    </p>

    <form
      class="inbound-register-page__form"
      novalidate
      @submit.prevent="onSubmit"
    >
      <AppSelect
        v-model="form.mailType"
        :label="t('inbound.mailTypeLabel')"
        :options="mailTypeOptions"
        :placeholder="t('inbound.mailTypePlaceholder')"
        :error="errors.mailType ? t(errors.mailType) : null"
        required
      />

      <div class="inbound-register-page__field-with-hint">
        <AppSelect
          v-model="form.carrierId"
          :label="t('inbound.carrierLabel')"
          :options="carrierOptions"
          :placeholder="t('inbound.carrierPlaceholder')"
        />
        <HelpHint :text="t('help.hint.inboundCarrier')" />
      </div>
      <OtherFieldInput
        v-model="form.otherCarrierName"
        :show="isOtherCarrier"
        :label="t('otherField.carrierLabel')"
        :error="errors.otherCarrierName ? t(errors.otherCarrierName) : null"
      />

      <div class="inbound-register-page__field-with-hint">
        <AppInput
          v-model="form.trackingNo"
          :label="t('inbound.trackingNoLabel')"
          :placeholder="t('inbound.trackingNoPlaceholder')"
          :error="errors.trackingNo ? t(errors.trackingNo) : null"
        />
        <HelpHint :text="t('help.hint.inboundTrackingNo')" />
      </div>

      <AppInput
        v-model="form.senderName"
        :label="t('inbound.senderNameLabel')"
        :error="errors.senderName ? t(errors.senderName) : null"
      />
      <AppInput
        v-model="form.senderOrg"
        :label="t('inbound.senderOrgLabel')"
        :error="errors.senderOrg ? t(errors.senderOrg) : null"
      />

      <div class="inbound-register-page__recipient">
        <div class="inbound-register-page__field-with-hint">
          <AppInput
            :model-value="form.recipientNameRaw"
            :label="t('inbound.recipientLabel')"
            :error="errors.recipientNameRaw ? t(errors.recipientNameRaw) : null"
            :hint="matchLoading ? t('inbound.matchLoading') : null"
            required
            @update:model-value="onRecipientInput"
          />
          <HelpHint :text="t('help.hint.inboundRecipientMatch')" />
        </div>
        <EmployeeMatchChips
          :candidates="matchCandidates"
          :model-value="form.recipientEmployeeId"
          @update:model-value="onSelectCandidate"
        />
        <p
          v-if="form.recipientEmployeeId"
          class="inbound-register-page__matched"
          role="status"
        >
          {{ t('inbound.matchSelected') }}
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

      <AppButton
        type="submit"
        :loading="submitting"
        full-width
      >
        {{ t('inbound.submit') }}
      </AppButton>
    </form>
  </section>
</template>

<style scoped>
.inbound-register-page {
  max-width: 640px;
}

.inbound-register-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.inbound-register-page__form {
  padding: var(--space-5);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.inbound-register-page__field-with-hint {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
}

.inbound-register-page__field-with-hint > :first-child {
  flex: 1;
  min-width: 0;
}

.inbound-register-page__recipient {
  margin-bottom: var(--space-2);
}

.inbound-register-page__matched {
  margin: 0 0 var(--space-4);
  color: var(--color-success-text);
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.inbound-register-page__success {
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-subtle);
  color: var(--color-text);
  font-weight: 600;
}

.inbound-register-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

@media (min-width: 1024px) {
  .inbound-register-page {
    max-width: 960px;
  }
  .inbound-register-page__form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    column-gap: var(--space-4);
    align-items: start;
  }
  .inbound-register-page__form > .inbound-register-page__recipient,
  .inbound-register-page__form > .inbound-register-page__matched,
  .inbound-register-page__form > .app-button {
    grid-column: 1 / -1;
  }
}
</style>
