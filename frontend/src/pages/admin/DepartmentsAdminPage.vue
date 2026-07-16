<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppButton from '@/components/AppButton.vue'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import HelpHint from '@/components/HelpHint.vue'
import { createDepartment, listDepartments, updateDepartment } from '@/api/departments'
import { listEmployees } from '@/api/employees'
import { ApiError } from '@/api/client'
import type { Department, Employee } from '@/types/api'

// A6: department management + contact person. Setting a department's contact
// (manager_employee_id) is what makes the "部門件" routing usable -- mail
// addressed to a company/department with no specific person is delivered to
// this contact (see OcrConfirmPage onSelectDepartment).
const { t } = useI18n({ useScope: 'global' })

const departments = ref<Department[]>([])
const employees = ref<Employee[]>([])
const loading = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

const createForm = ref({ name: '', code: '', managerEmployeeId: '' })
const creating = ref(false)

const employeeOptions = computed(() => employees.value.map((e) => ({ value: e.id, label: e.name })))

function contactName(dept: Department): string {
  if (!dept.manager_employee_id) return t('departments.noContact')
  const emp = employees.value.find((e) => e.id === dept.manager_employee_id)
  return emp ? emp.name : t('departments.unknownContact')
}

async function reload() {
  loading.value = true
  error.value = null
  try {
    const [d, e] = await Promise.all([
      listDepartments({ is_active: true }),
      listEmployees({ status: 'active', size: 100 }),
    ])
    departments.value = d.items
    employees.value = e.items
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    loading.value = false
  }
}

onMounted(reload)

async function onContactChange(dept: Department, employeeId: string) {
  message.value = null
  error.value = null
  try {
    const updated = await updateDepartment(dept.id, { manager_employee_id: employeeId || null })
    dept.manager_employee_id = updated.manager_employee_id ?? null
    message.value = t('departments.contactSaved', { name: dept.name })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('errors.generic')
  }
}

async function onCreate() {
  if (!createForm.value.name.trim() || !createForm.value.code.trim()) return
  creating.value = true
  message.value = null
  error.value = null
  try {
    await createDepartment({
      name: createForm.value.name.trim(),
      code: createForm.value.code.trim(),
      manager_employee_id: createForm.value.managerEmployeeId || null,
    })
    createForm.value = { name: '', code: '', managerEmployeeId: '' }
    message.value = t('departments.created')
    await reload()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('errors.generic')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <section class="departments-admin-page">
    <h1 class="departments-admin-page__title">
      {{ t('departments.title') }}
      <HelpHint :text="t('departments.help')" />
    </h1>
    <p class="departments-admin-page__intro">
      {{ t('departments.intro') }}
    </p>

    <p
      v-if="message"
      class="departments-admin-page__ok"
      role="status"
    >
      {{ message }}
    </p>
    <p
      v-if="error"
      class="departments-admin-page__error"
      role="alert"
    >
      {{ error }}
    </p>

    <form
      class="departments-admin-page__create"
      @submit.prevent="onCreate"
    >
      <AppInput
        v-model="createForm.name"
        :label="t('departments.name')"
      />
      <AppInput
        v-model="createForm.code"
        :label="t('departments.code')"
      />
      <AppSelect
        v-model="createForm.managerEmployeeId"
        :label="t('departments.contact')"
        :options="employeeOptions"
        :placeholder="t('departments.noContact')"
        placeholder-selectable
      />
      <AppButton
        type="submit"
        :loading="creating"
      >
        {{ t('departments.addButton') }}
      </AppButton>
    </form>

    <div class="departments-admin-page__table-card">
      <table class="departments-admin-page__table">
        <thead>
          <tr>
            <th>{{ t('departments.name') }}</th>
            <th>{{ t('departments.code') }}</th>
            <th>{{ t('departments.contact') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="dept in departments"
            :key="dept.id"
          >
            <td :data-label="t('departments.name')">
              {{ dept.name }}
            </td>
            <td :data-label="t('departments.code')">
              {{ dept.code }}
            </td>
            <td :data-label="t('departments.contact')">
              <AppSelect
                :model-value="dept.manager_employee_id ?? ''"
                :options="employeeOptions"
                :placeholder="t('departments.noContact')"
                placeholder-selectable
                @update:model-value="(v) => onContactChange(dept, v)"
              />
              <span class="departments-admin-page__current">{{ contactName(dept) }}</span>
            </td>
          </tr>
          <tr v-if="!loading && departments.length === 0">
            <td colspan="3">
              {{ t('departments.empty') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.departments-admin-page {
  max-width: 900px;
}

.departments-admin-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-3);
}

.departments-admin-page__intro {
  color: var(--color-text-muted);
  margin: 0 0 var(--space-4);
}

.departments-admin-page__ok {
  color: var(--color-success-text);
  font-weight: 600;
  margin: 0 0 var(--space-3);
}

.departments-admin-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
  margin: 0 0 var(--space-3);
}

.departments-admin-page__create {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: flex-end;
  margin: 0 0 var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.departments-admin-page__table-card {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.departments-admin-page__table {
  width: 100%;
  border-collapse: collapse;
}

.departments-admin-page__table th,
.departments-admin-page__table td {
  padding: var(--space-3);
  text-align: left;
  border-bottom: 1px solid var(--color-border-subtle);
  vertical-align: top;
}

.departments-admin-page__current {
  display: block;
  margin-top: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}
</style>
