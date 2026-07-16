<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppButton from '@/components/AppButton.vue'
import AppDialog from '@/components/AppDialog.vue'
import HelpHint from '@/components/HelpHint.vue'
import { createEmployee, importEmployeesCsv, listEmployees, updateEmployee } from '@/api/employees'
import { listDepartments } from '@/api/departments'
import { ApiError } from '@/api/client'
import type { Department, Employee, EmployeeImportResult } from '@/types/api'

const { t } = useI18n({ useScope: 'global' })

const employees = ref<Employee[]>([])
const departments = ref<Department[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)

const departmentOptions = computed(() => departments.value.map((d) => ({ value: d.id, label: d.name })))
const statusOptions = computed(() => [
  { value: 'active', label: t('employees.statusActive') },
  { value: 'inactive', label: t('employees.statusInactive') },
])

async function loadEmployees() {
  loading.value = true
  loadError.value = null
  try {
    const result = await listEmployees({ size: 100 })
    employees.value = result.items
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadEmployees()
  try {
    const result = await listDepartments()
    departments.value = result.items
  } catch {
    departments.value = []
  }
})

// --- Create / edit dialog -------------------------------------------------
const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)
const nameError = ref<string | null>(null)
const saving = ref(false)

const form = reactive({
  name: '',
  aliases: '',
  departmentId: '',
  ext: '',
  email: '',
  phone: '',
  status: 'active' as 'active' | 'inactive',
})

function resetForm() {
  form.name = ''
  form.aliases = ''
  form.departmentId = ''
  form.ext = ''
  form.email = ''
  form.phone = ''
  form.status = 'active'
  nameError.value = null
  formError.value = null
}

function openCreateDialog() {
  editingId.value = null
  resetForm()
  dialogOpen.value = true
}

function openEditDialog(employee: Employee) {
  editingId.value = employee.id
  form.name = employee.name
  form.aliases = employee.aliases.join(', ')
  form.departmentId = employee.department_id ?? ''
  form.ext = employee.ext ?? ''
  form.email = employee.email ?? ''
  form.phone = employee.phone ?? ''
  form.status = employee.status
  nameError.value = null
  formError.value = null
  dialogOpen.value = true
}

function closeDialog() {
  dialogOpen.value = false
}

async function onSave() {
  formError.value = null
  nameError.value = form.name.trim() ? null : t('employees.errors.nameRequired')
  if (nameError.value) return

  const payload = {
    name: form.name.trim(),
    aliases: form.aliases
      .split(',')
      .map((a) => a.trim())
      .filter(Boolean),
    department_id: form.departmentId || null,
    ext: form.ext.trim() || undefined,
    email: form.email.trim() || undefined,
    phone: form.phone.trim() || undefined,
    status: form.status,
  }

  saving.value = true
  try {
    if (editingId.value) {
      await updateEmployee(editingId.value, payload)
    } else {
      await createEmployee(payload)
    }
    dialogOpen.value = false
    await loadEmployees()
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    saving.value = false
  }
}

// --- CSV import ------------------------------------------------------------
const csvInputRef = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<EmployeeImportResult | null>(null)
const importError = ref<string | null>(null)

async function onCsvSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  importing.value = true
  importError.value = null
  importResult.value = null
  try {
    importResult.value = await importEmployeesCsv(file)
    await loadEmployees()
  } catch (err) {
    importError.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    importing.value = false
    input.value = ''
  }
}

function triggerCsvPicker() {
  csvInputRef.value?.click()
}

// M6-HELP 範本: client-generated CSV matching the columns `importEmployeesCsv`
// expects (see src/api/employees.ts / help.hint.employeesCsvTemplate) --
// name/aliases/department_code/ext/email/phone, with two example rows so an
// operator can see the expected shape (semicolon-separated aliases, no
// header renaming) without guessing. Built as a Blob + object URL rather
// than a static /public file so the column list can never drift from the
// hint text next to the button.
const CSV_TEMPLATE_HEADER = 'name,aliases,department_code,ext,email,phone'
const CSV_TEMPLATE_ROWS = [
  '王小明,小明;Ming,SALES,1234,ming@example.com,0912345678',
  '陳小華,Hua,MKT,5678,hua@example.com,0922334455',
]

function downloadCsvTemplate() {
  const csvContent = [CSV_TEMPLATE_HEADER, ...CSV_TEMPLATE_ROWS].join('\r\n')
  // Prepend a UTF-8 BOM so Excel (common consumer of this template on
  // Windows) doesn't mangle the zh-TW example names as mojibake.
  const blob = new Blob(['\ufeff', csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'employees-template.csv'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <section class="employees-admin-page">
    <h1 class="employees-admin-page__title">
      {{ t('employees.title') }}
      <HelpHint :text="t('help.hint.employees')" />
    </h1>

    <div class="employees-admin-page__toolbar">
      <AppButton @click="openCreateDialog">
        {{ t('employees.addNew') }}
      </AppButton>
      <AppButton
        variant="secondary"
        @click="downloadCsvTemplate"
      >
        {{ t('employees.downloadTemplate') }}
      </AppButton>
      <AppButton
        variant="secondary"
        :loading="importing"
        @click="triggerCsvPicker"
      >
        {{ t('employees.importCsv') }}
      </AppButton>
      <HelpHint :text="t('help.hint.employeesCsvTemplate')" />
      <input
        ref="csvInputRef"
        type="file"
        accept=".csv,text/csv"
        class="employees-admin-page__csv-input"
        :aria-label="t('employees.importCsv')"
        @change="onCsvSelected"
      >
    </div>

    <p
      v-if="importError"
      class="employees-admin-page__error"
      role="alert"
    >
      {{ importError }}
    </p>
    <div
      v-if="importResult"
      class="employees-admin-page__import-report"
      role="status"
    >
      <p>
        {{
          t('employees.importSummary', {
            total: importResult.total,
            succeeded: importResult.succeeded,
            failed: importResult.failed,
          })
        }}
      </p>
      <ul
        v-if="importResult.errors.length"
        class="employees-admin-page__import-errors"
      >
        <li
          v-for="err in importResult.errors"
          :key="err.row"
        >
          {{ t('employees.importRowError', { row: err.row, message: err.message }) }}
        </li>
      </ul>
    </div>

    <p
      v-if="loadError"
      class="employees-admin-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p v-else-if="loading">
      {{ t('common.loading') }}
    </p>
    <p
      v-else-if="employees.length === 0"
      class="employees-admin-page__empty"
    >
      {{ t('employees.empty') }}
    </p>

    <div
      v-else
      class="employees-admin-page__table-card"
    >
      <table class="employees-admin-page__table">
        <thead>
          <tr>
            <th scope="col">
              {{ t('employees.colName') }}
            </th>
            <th scope="col">
              {{ t('employees.colDepartment') }}
            </th>
            <th scope="col">
              {{ t('employees.colExt') }}
            </th>
            <th scope="col">
              {{ t('employees.colStatus') }}
            </th>
            <th scope="col">
              {{ t('employees.colActions') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="employee in employees"
            :key="employee.id"
          >
            <td :data-label="t('employees.colName')">
              {{ employee.name }}
            </td>
            <td :data-label="t('employees.colDepartment')">
              {{ employee.department_name ?? '—' }}
            </td>
            <td :data-label="t('employees.colExt')">
              {{ employee.ext ?? '—' }}
            </td>
            <td :data-label="t('employees.colStatus')">
              {{ employee.status === 'active' ? t('employees.statusActive') : t('employees.statusInactive') }}
            </td>
            <td :data-label="t('employees.colActions')">
              <button
                type="button"
                class="employees-admin-page__edit-btn"
                @click="openEditDialog(employee)"
              >
                {{ t('employees.edit') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppDialog
      :open="dialogOpen"
      :title="editingId ? t('employees.editTitle') : t('employees.addTitle')"
      @close="closeDialog"
    >
      <form
        novalidate
        @submit.prevent="onSave"
      >
        <AppInput
          v-model="form.name"
          :label="t('employees.colName')"
          :error="nameError"
          required
        />
        <AppInput
          v-model="form.aliases"
          :label="t('employees.aliasesLabel')"
          :hint="t('employees.aliasesHint')"
        />
        <AppSelect
          v-model="form.departmentId"
          :label="t('employees.colDepartment')"
          :options="departmentOptions"
          :placeholder="t('search.anyDepartment')"
          placeholder-selectable
        />
        <AppInput
          v-model="form.ext"
          :label="t('employees.extLabel')"
        />
        <AppInput
          v-model="form.email"
          type="email"
          :label="t('employees.emailLabel')"
        />
        <AppInput
          v-model="form.phone"
          type="tel"
          :label="t('employees.phoneLabel')"
        />
        <AppSelect
          v-model="form.status"
          :label="t('employees.colStatus')"
          :options="statusOptions"
        />

        <p
          v-if="formError"
          class="employees-admin-page__error"
          role="alert"
        >
          {{ formError }}
        </p>
      </form>

      <template #footer>
        <AppButton
          variant="ghost"
          type="button"
          @click="closeDialog"
        >
          {{ t('common.cancel') }}
        </AppButton>
        <AppButton
          :loading="saving"
          @click="onSave"
        >
          {{ t('common.save') }}
        </AppButton>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.employees-admin-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.employees-admin-page__toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}

.employees-admin-page__csv-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.employees-admin-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-4);
}

.employees-admin-page__import-report {
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-subtle);
}

.employees-admin-page__import-errors {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-5);
}

.employees-admin-page__empty {
  color: var(--color-text-muted);
}

.employees-admin-page__table-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  overflow-x: auto;
}

.employees-admin-page__table {
  width: 100%;
  border-collapse: collapse;
}

.employees-admin-page__table th,
.employees-admin-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.employees-admin-page__edit-btn {
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

/* Mobile card collapse (06 §2 Mobile-first, breakpoint 640) -- same pattern
   as SearchPage.vue (POLISH-AUDIT.md Should-fix #5). */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .employees-admin-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .employees-admin-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .employees-admin-page__table,
  .employees-admin-page__table tbody,
  .employees-admin-page__table tr,
  .employees-admin-page__table td {
    display: block;
    width: 100%;
  }

  .employees-admin-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .employees-admin-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .employees-admin-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
    flex-shrink: 0;
  }
}
</style>
