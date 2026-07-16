<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppButton from '@/components/AppButton.vue'
import AppBadge from '@/components/AppBadge.vue'
import SignaturePad from '@/components/SignaturePad.vue'
import HelpHint from '@/components/HelpHint.vue'
import { useDebouncedFn } from '@/composables/useDebouncedFn'
import { listEmployees } from '@/api/employees'
import { listItems, pickupItem } from '@/api/items'
import { lookupByPickupCode } from '@/api/pickup'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import { mailStatusBadgeVariant, mailStatusLabelKey } from '@/utils/mailStatus'
import type { Employee, MailItem, PickupLookupEmployee, PickupMethod } from '@/types/api'

// 06 §1 領取核銷頁: 搜姓名/掃員工 QR/輸入取件碼 -> 觸控簽名板.
//
// M1-R1 blocking #3: the "輸入取件碼" path now calls the dedicated
// `POST /pickup/lookup` endpoint (app/api/v1/pickup.py) instead of the old
// `GET /employees?q=<code>` + client-side `pickup_code` comparison, which
// never actually worked -- `q` only ever searched `name`, and
// `GET /employees` no longer returns `pickup_code` in its response at all
// (server-side leak fix, see app/api/v1/employees.py `_serialize`). The
// server does the authoritative, constant-time comparison and returns the
// matched employee plus their pending items in one call.
const { t } = useI18n({ useScope: 'global' })

type LookupMode = 'name' | 'code'
type SelectedEmployee = Employee | PickupLookupEmployee

const lookupMode = ref<LookupMode>('name')
const lookupQuery = ref('')
const lookupLoading = ref(false)
const lookupError = ref<string | null>(null)
const lookupResults = ref<Employee[]>([])

const selectedEmployee = ref<SelectedEmployee | null>(null)
const pendingItems = ref<MailItem[]>([])
const itemsLoading = ref(false)
const selectedItemIds = reactive(new Set<string>())

const pickedUpByName = ref('')
const method = ref<PickupMethod>('signature')
const pickupCodeInput = ref('')
const signaturePadRef = ref<InstanceType<typeof SignaturePad> | null>(null)
const signatureValue = ref<string | null>(null)

const submitting = ref(false)
const formError = ref<string | null>(null)
interface PickupResultRow {
  itemNo: string
  success: boolean
  message: string
}
const resultRows = ref<PickupResultRow[]>([])

const hasSelection = computed(() => selectedItemIds.size > 0)

function selectPendingItems(items: MailItem[]) {
  pendingItems.value = items
  selectedItemIds.clear()
  for (const item of items) selectedItemIds.add(item.id)
}

async function runLookup() {
  const query = lookupQuery.value.trim()
  lookupError.value = null
  lookupResults.value = []
  selectedEmployee.value = null
  pendingItems.value = []
  if (!query) return

  lookupLoading.value = true
  try {
    if (lookupMode.value === 'code') {
      const result = await lookupByPickupCode(query)
      selectedEmployee.value = result.employee
      pickedUpByName.value = result.employee.name
      resultRows.value = []
      formError.value = null
      selectPendingItems(result.items)
      // The counter already has the verified code in hand at this point;
      // default the confirmation method to it so the flow doesn't force a
      // redundant signature after a successful code lookup.
      method.value = 'pickup_code'
      pickupCodeInput.value = query
      if (result.items.length === 0) {
        lookupError.value = t('pickup.noPendingItems')
      }
    } else {
      const result = await listEmployees({ q: query, status: 'active', size: 10 })
      lookupResults.value = result.items
      if (result.items.length === 0) {
        lookupError.value = t('pickup.errors.nameNotFound')
      }
    }
  } catch (err) {
    lookupError.value = errorMessage(err)
  } finally {
    lookupLoading.value = false
  }
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'PICKUP_CODE_INVALID') return t('pickup.errors.codeNotFound')
    if (err.code === 'PICKUP_CODE_RATE_LIMITED') return t('errors.rateLimited')
    return err.message
  }
  return t('errors.generic')
}

const debouncedLookup = useDebouncedFn(runLookup, 350)

function onQueryInput(value: string) {
  lookupQuery.value = value
  debouncedLookup()
}

async function selectEmployee(employee: Employee) {
  selectedEmployee.value = employee
  lookupResults.value = []
  pickedUpByName.value = employee.name
  resultRows.value = []
  formError.value = null
  itemsLoading.value = true
  try {
    const result = await listItems({ q: employee.name, status: 'notified', size: 50 })
    selectPendingItems(result.items)
  } catch (err) {
    lookupError.value = errorMessage(err)
  } finally {
    itemsLoading.value = false
  }
}

function toggleItem(id: string) {
  if (selectedItemIds.has(id)) {
    selectedItemIds.delete(id)
  } else {
    selectedItemIds.add(id)
  }
}

function onSignatureChange(value: string | null) {
  signatureValue.value = value
}

async function onSubmit() {
  formError.value = null
  resultRows.value = []

  if (!pickedUpByName.value.trim()) {
    formError.value = t('pickup.errors.pickedUpByRequired')
    return
  }
  if (!hasSelection.value) {
    formError.value = t('pickup.errors.noItemsSelected')
    return
  }
  if (method.value === 'signature' && !signatureValue.value) {
    formError.value = t('pickup.errors.signatureRequired')
    return
  }
  if (method.value === 'pickup_code' && !pickupCodeInput.value.trim()) {
    formError.value = t('pickup.errors.codeRequired')
    return
  }

  submitting.value = true
  const targetIds = [...selectedItemIds]
  const rows: PickupResultRow[] = []

  for (const id of targetIds) {
    const item = pendingItems.value.find((i) => i.id === id)
    if (!item) continue
    try {
      await pickupItem(id, {
        method: method.value,
        picked_up_by_name: pickedUpByName.value.trim(),
        signature_png_base64: method.value === 'signature' ? (signatureValue.value ?? undefined) : undefined,
        pickup_code: method.value === 'pickup_code' ? pickupCodeInput.value.trim() : undefined,
      })
      rows.push({ itemNo: item.item_no, success: true, message: t('pickup.resultSuccess') })
      pendingItems.value = pendingItems.value.filter((i) => i.id !== id)
      selectedItemIds.delete(id)
    } catch (err) {
      rows.push({ itemNo: item.item_no, success: false, message: errorMessage(err) })
    }
  }

  resultRows.value = rows
  signaturePadRef.value?.clear()
  pickupCodeInput.value = ''
  submitting.value = false
}
</script>

<template>
  <section class="pickup-page">
    <h1 class="pickup-page__title">
      {{ t('pickup.title') }}
      <HelpHint :text="t('help.hint.pickup')" />
    </h1>

    <div
      class="pickup-page__lookup-mode"
      role="radiogroup"
      :aria-label="t('pickup.lookupModeLabel')"
    >
      <label class="pickup-page__radio">
        <input
          v-model="lookupMode"
          type="radio"
          name="lookup-mode"
          value="name"
        >
        {{ t('pickup.lookupByName') }}
      </label>
      <label class="pickup-page__radio">
        <input
          v-model="lookupMode"
          type="radio"
          name="lookup-mode"
          value="code"
        >
        {{ t('pickup.lookupByCode') }}
      </label>
    </div>

    <AppInput
      :model-value="lookupQuery"
      :label="lookupMode === 'name' ? t('pickup.lookupByName') : t('pickup.lookupByCode')"
      :hint="lookupLoading ? t('common.loading') : null"
      @update:model-value="onQueryInput"
    />
    <p
      v-if="lookupError"
      class="pickup-page__error"
      role="alert"
    >
      {{ lookupError }}
    </p>

    <ul
      v-if="lookupResults.length"
      class="pickup-page__results"
    >
      <li
        v-for="employee in lookupResults"
        :key="employee.id"
      >
        <button
          type="button"
          class="pickup-page__result-btn"
          @click="selectEmployee(employee)"
        >
          <span>{{ employee.name }}</span>
          <span
            v-if="employee.department_name"
            class="pickup-page__result-dept"
          >{{
            employee.department_name
          }}</span>
        </button>
      </li>
    </ul>

    <div
      v-if="selectedEmployee"
      class="pickup-page__employee"
    >
      <h2 class="pickup-page__employee-name">
        {{ t('pickup.selectedEmployee', { name: selectedEmployee.name }) }}
      </h2>

      <p v-if="itemsLoading">
        {{ t('common.loading') }}
      </p>
      <p
        v-else-if="pendingItems.length === 0"
        class="pickup-page__empty"
      >
        {{ t('pickup.noPendingItems') }}
      </p>

      <ul
        v-else
        class="pickup-page__items"
      >
        <li
          v-for="item in pendingItems"
          :key="item.id"
          class="pickup-page__item"
        >
          <label class="pickup-page__item-label">
            <input
              type="checkbox"
              :checked="selectedItemIds.has(item.id)"
              @change="toggleItem(item.id)"
            >
            <span class="pickup-page__item-info">
              <span class="pickup-page__item-no">{{ item.item_no }}</span>
              <AppBadge
                :status="mailStatusBadgeVariant(item.status)"
                :label="t(mailStatusLabelKey(item.status))"
              />
              <span class="pickup-page__item-meta">{{ formatDateTime(item.received_at) }}</span>
            </span>
          </label>
        </li>
      </ul>

      <form
        v-if="pendingItems.length"
        novalidate
        @submit.prevent="onSubmit"
      >
        <AppInput
          v-model="pickedUpByName"
          :label="t('pickup.pickedUpByLabel')"
          required
        />

        <fieldset class="pickup-page__method">
          <legend>{{ t('pickup.methodLabel') }}</legend>
          <label class="pickup-page__radio">
            <input
              v-model="method"
              type="radio"
              name="pickup-method"
              value="signature"
            >
            {{ t('pickup.methodSignature') }}
          </label>
          <label class="pickup-page__radio">
            <input
              v-model="method"
              type="radio"
              name="pickup-method"
              value="pickup_code"
            >
            {{ t('pickup.methodCode') }}
          </label>
        </fieldset>

        <SignaturePad
          v-if="method === 'signature'"
          ref="signaturePadRef"
          @change="onSignatureChange"
        />
        <AppInput
          v-if="method === 'pickup_code'"
          v-model="pickupCodeInput"
          :label="t('pickup.verifyCodeLabel')"
          required
        />

        <p
          v-if="formError"
          class="pickup-page__error"
          role="alert"
        >
          {{ formError }}
        </p>

        <AppButton
          type="submit"
          :loading="submitting"
          full-width
        >
          {{ t('pickup.submit') }}
        </AppButton>
      </form>
    </div>

    <ul
      v-if="resultRows.length"
      class="pickup-page__result-log"
      aria-live="polite"
    >
      <li
        v-for="row in resultRows"
        :key="row.itemNo"
        :class="row.success ? 'pickup-page__result-ok' : 'pickup-page__result-fail'"
      >
        {{ row.itemNo }} — {{ row.message }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.pickup-page {
  max-width: 640px;
}

.pickup-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.pickup-page__lookup-mode {
  display: flex;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.pickup-page__radio {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target-min);
  font-weight: 600;
  color: var(--color-text);
}

.pickup-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

.pickup-page__results {
  list-style: none;
  margin: 0 0 var(--space-4);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.pickup-page__result-btn {
  display: flex;
  justify-content: space-between;
  width: 100%;
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg);
  color: var(--color-text);
  cursor: pointer;
}

.pickup-page__result-dept {
  color: var(--color-text-muted);
}

.pickup-page__employee-name {
  font-size: var(--font-size-lg);
  margin: var(--space-5) 0 var(--space-4);
}

.pickup-page__empty {
  color: var(--color-text-muted);
}

.pickup-page__items {
  list-style: none;
  margin: 0 0 var(--space-4);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  /* M8-2 badges spec "等寬對齊": same-width AppBadge across this list. */
  --app-badge-min-width: 112px;
}

.pickup-page__item-label {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target-min);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.pickup-page__item-label input[type='checkbox'] {
  width: 20px;
  height: 20px;
}

.pickup-page__item-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.pickup-page__item-no {
  font-weight: 700;
}

.pickup-page__item-meta {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.pickup-page__method {
  border: none;
  padding: 0;
  margin: 0 0 var(--space-4);
}

.pickup-page__method legend {
  font-weight: 600;
  margin-bottom: var(--space-2);
  padding: 0;
}

.pickup-page__result-log {
  margin-top: var(--space-5);
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.pickup-page__result-ok {
  color: var(--color-success-text);
  font-weight: 600;
}

.pickup-page__result-fail {
  color: var(--color-danger-text);
  font-weight: 600;
}
</style>
