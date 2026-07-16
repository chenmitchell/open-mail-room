<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppInput from '@/components/AppInput.vue'
import AppSelect from '@/components/AppSelect.vue'
import AppButton from '@/components/AppButton.vue'
import AppDialog from '@/components/AppDialog.vue'
import AppToggle from '@/components/AppToggle.vue'
import AppBadge from '@/components/AppBadge.vue'
import HelpHint from '@/components/HelpHint.vue'
import { createUser, listUsers, resetUserPassword, updateUser } from '@/api/users'
import { ApiError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import { roleBadgeVariant, userActiveBadgeVariant } from '@/utils/userBadges'
import type { AdminUser, AdminUsersQuery, Role } from '@/types/api'

// M7-FE task brief: 後台開帳號給其他人並設角色. `GET /admin/users` is a
// paginated envelope, mirrors SearchPage.vue/AuditLogsPage.vue's
// filters+pagination pattern.
const { t } = useI18n({ useScope: 'global' })

const ROLES: Role[] = ['admin', 'counter', 'employee', 'viewer']
const roleOptions = computed(() => ROLES.map((r) => ({ value: r, label: t(`nav.roleBadge.${r}`) })))
const statusFilterOptions = computed(() => [
  { value: 'true', label: t('usersAdmin.statusActive') },
  { value: 'false', label: t('usersAdmin.statusInactive') },
])

function roleLabel(role: Role): string {
  return t(`nav.roleBadge.${role}`)
}

// Maps ApiError.code -> a friendly, already-translated message; falls back
// to the backend's own message, then a generic i18n string.
function mapError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 'EMAIL_EXISTS':
        return t('usersAdmin.errors.emailExists')
      case 'WEAK_PASSWORD':
        return t('usersAdmin.errors.weakPassword')
      case 'EMPLOYEE_NOT_FOUND':
        return t('usersAdmin.errors.employeeNotFound')
      case 'LAST_ADMIN':
        return t('usersAdmin.errors.lastAdmin')
      default:
        return err.message
    }
  }
  return t('errors.generic')
}

// --- List + filters + pagination ------------------------------------------
const filters = reactive({
  q: '',
  role: '' as Role | '',
  isActive: '' as '' | 'true' | 'false',
})

const page = ref(1)
const size = 20
const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref<string | null>(null)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

function buildQuery(): AdminUsersQuery {
  return {
    q: filters.q || undefined,
    role: (filters.role || undefined) as Role | undefined,
    is_active: filters.isActive === '' ? undefined : filters.isActive === 'true',
    page: page.value,
    size,
  }
}

async function loadUsers() {
  loading.value = true
  loadError.value = null
  try {
    const result = await listUsers(buildQuery())
    users.value = result.items
    total.value = result.meta.total
  } catch (err) {
    loadError.value = mapError(err)
    users.value = []
  } finally {
    loading.value = false
  }
}

function onFilterSubmit() {
  page.value = 1
  loadUsers()
}

function resetFilters() {
  filters.q = ''
  filters.role = ''
  filters.isActive = ''
  page.value = 1
  loadUsers()
}

function goToPage(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
  loadUsers()
}

// --- Create / edit dialog ---------------------------------------------------
const dialogOpen = ref(false)
const editingUser = ref<AdminUser | null>(null)
const emailError = ref<string | null>(null)
const displayNameError = ref<string | null>(null)
const roleError = ref<string | null>(null)
const passwordError = ref<string | null>(null)
const formError = ref<string | null>(null)
const saving = ref(false)

const form = reactive({
  email: '',
  displayName: '',
  role: '' as Role | '',
  password: '',
  employeeId: '',
  isActive: true,
})

function resetForm() {
  form.email = ''
  form.displayName = ''
  form.role = ''
  form.password = ''
  form.employeeId = ''
  form.isActive = true
  emailError.value = null
  displayNameError.value = null
  roleError.value = null
  passwordError.value = null
  formError.value = null
}

function openCreateDialog() {
  editingUser.value = null
  resetForm()
  dialogOpen.value = true
}

function openEditDialog(user: AdminUser) {
  editingUser.value = user
  form.email = user.email
  form.displayName = user.display_name
  form.role = user.role
  form.password = ''
  form.employeeId = user.employee_id ?? ''
  form.isActive = user.is_active
  emailError.value = null
  displayNameError.value = null
  roleError.value = null
  passwordError.value = null
  formError.value = null
  dialogOpen.value = true
}

function closeDialog() {
  dialogOpen.value = false
}

async function onSave() {
  formError.value = null
  displayNameError.value = form.displayName.trim() ? null : t('usersAdmin.errors.displayNameRequired')
  roleError.value = form.role ? null : t('usersAdmin.errors.roleRequired')

  if (!editingUser.value) {
    emailError.value = form.email.trim() ? null : t('usersAdmin.errors.emailRequired')
    passwordError.value = !form.password
      ? t('usersAdmin.errors.passwordRequired')
      : form.password.length < 10
        ? t('usersAdmin.errors.passwordTooShort')
        : null
  } else {
    emailError.value = null
    passwordError.value = null
  }

  if (displayNameError.value || roleError.value || emailError.value || passwordError.value) return

  saving.value = true
  try {
    if (editingUser.value) {
      await updateUser(editingUser.value.id, {
        display_name: form.displayName.trim(),
        role: form.role as Role,
        is_active: form.isActive,
        employee_id: form.employeeId.trim() || null,
      })
    } else {
      await createUser({
        email: form.email.trim(),
        display_name: form.displayName.trim(),
        role: form.role as Role,
        password: form.password,
        employee_id: form.employeeId.trim() || undefined,
      })
    }
    dialogOpen.value = false
    await loadUsers()
  } catch (err) {
    formError.value = mapError(err)
  } finally {
    saving.value = false
  }
}

// --- Activate / deactivate (LAST_ADMIN guard) -------------------------------
const toggling = reactive(new Set<string>())
const toggleError = ref<string | null>(null)
const deactivateTarget = ref<AdminUser | null>(null)

function requestToggle(user: AdminUser) {
  toggleError.value = null
  resetSuccessMessage.value = null
  if (user.is_active) {
    // Deactivating is the dangerous direction (can lock someone out, or hit
    // the backend's LAST_ADMIN guard) — always confirm first.
    deactivateTarget.value = user
  } else {
    activateUser(user)
  }
}

async function activateUser(user: AdminUser) {
  toggling.add(user.id)
  try {
    await updateUser(user.id, { is_active: true })
    await loadUsers()
  } catch (err) {
    toggleError.value = mapError(err)
  } finally {
    toggling.delete(user.id)
  }
}

function closeDeactivateConfirm() {
  deactivateTarget.value = null
}

async function confirmDeactivate() {
  const user = deactivateTarget.value
  if (!user) return
  toggling.add(user.id)
  try {
    await updateUser(user.id, { is_active: false })
    deactivateTarget.value = null
    await loadUsers()
  } catch (err) {
    toggleError.value = mapError(err)
    deactivateTarget.value = null
  } finally {
    toggling.delete(user.id)
  }
}

// --- Reset password dialog ---------------------------------------------------
const resetTarget = ref<AdminUser | null>(null)
const resetPasswordValue = ref('')
const resetPasswordError = ref<string | null>(null)
const resetting = ref(false)
const resetSuccessMessage = ref<string | null>(null)

function openResetDialog(user: AdminUser) {
  toggleError.value = null
  resetSuccessMessage.value = null
  resetTarget.value = user
  resetPasswordValue.value = ''
  resetPasswordError.value = null
}

function closeResetDialog() {
  resetTarget.value = null
}

async function confirmReset() {
  const user = resetTarget.value
  if (!user) return
  resetPasswordError.value =
    resetPasswordValue.value.length >= 10 ? null : t('usersAdmin.errors.passwordTooShort')
  if (resetPasswordError.value) return

  resetting.value = true
  try {
    await resetUserPassword(user.id, { new_password: resetPasswordValue.value })
    resetSuccessMessage.value = t('usersAdmin.resetPassword.success', { email: user.email })
    resetTarget.value = null
  } catch (err) {
    resetPasswordError.value = mapError(err)
  } finally {
    resetting.value = false
  }
}

onMounted(loadUsers)
</script>

<template>
  <section class="users-admin-page">
    <h1 class="users-admin-page__title">
      {{ t('usersAdmin.title') }}
      <HelpHint :text="t('help.hint.usersAdmin')" />
    </h1>

    <AppButton @click="openCreateDialog">
      {{ t('usersAdmin.addNew') }}
    </AppButton>

    <form
      class="users-admin-page__filters"
      novalidate
      @submit.prevent="onFilterSubmit"
    >
      <AppInput
        v-model="filters.q"
        :label="t('usersAdmin.searchLabel')"
      />
      <AppSelect
        v-model="filters.role"
        :label="t('usersAdmin.roleLabel')"
        :options="roleOptions"
        :placeholder="t('usersAdmin.anyRole')"
        placeholder-selectable
      />
      <AppSelect
        v-model="filters.isActive"
        :label="t('usersAdmin.statusLabel')"
        :options="statusFilterOptions"
        :placeholder="t('usersAdmin.anyStatus')"
        placeholder-selectable
      />
      <div class="users-admin-page__filter-actions">
        <AppButton
          type="submit"
          :loading="loading"
        >
          {{ t('usersAdmin.apply') }}
        </AppButton>
        <AppButton
          type="button"
          variant="ghost"
          @click="resetFilters"
        >
          {{ t('usersAdmin.reset') }}
        </AppButton>
      </div>
    </form>

    <p
      v-if="resetSuccessMessage"
      class="users-admin-page__success"
      role="status"
    >
      {{ resetSuccessMessage }}
    </p>
    <p
      v-if="toggleError"
      class="users-admin-page__error"
      role="alert"
    >
      {{ toggleError }}
    </p>
    <p
      v-if="loadError"
      class="users-admin-page__error"
      role="alert"
    >
      {{ loadError }}
    </p>
    <p v-else-if="loading">
      {{ t('common.loading') }}
    </p>
    <p
      v-else-if="users.length === 0"
      class="users-admin-page__empty"
    >
      {{ t('usersAdmin.empty') }}
    </p>

    <div
      v-if="users.length"
      class="users-admin-page__table-card"
    >
      <table class="users-admin-page__table">
        <caption class="users-admin-page__caption">
          {{ t('usersAdmin.resultsCaption', { total }) }}
        </caption>
        <thead>
          <tr>
            <th scope="col">
              {{ t('usersAdmin.colEmail') }}
            </th>
            <th scope="col">
              {{ t('usersAdmin.colDisplayName') }}
            </th>
            <th scope="col">
              {{ t('usersAdmin.colRole') }}
            </th>
            <th scope="col">
              {{ t('usersAdmin.colStatus') }}
            </th>
            <th scope="col">
              {{ t('usersAdmin.colLastLogin') }}
            </th>
            <th scope="col">
              {{ t('usersAdmin.colEmployee') }}
            </th>
            <th scope="col">
              {{ t('usersAdmin.colActions') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="user in users"
            :key="user.id"
          >
            <td :data-label="t('usersAdmin.colEmail')">
              {{ user.email }}
            </td>
            <td :data-label="t('usersAdmin.colDisplayName')">
              {{ user.display_name }}
            </td>
            <td :data-label="t('usersAdmin.colRole')">
              <AppBadge
                :status="roleBadgeVariant(user.role)"
                :label="roleLabel(user.role)"
              />
            </td>
            <td :data-label="t('usersAdmin.colStatus')">
              <AppBadge
                :status="userActiveBadgeVariant(user.is_active)"
                :label="user.is_active ? t('usersAdmin.statusActive') : t('usersAdmin.statusInactive')"
              />
            </td>
            <td :data-label="t('usersAdmin.colLastLogin')">
              {{ user.last_login_at ? formatDateTime(user.last_login_at) : '—' }}
            </td>
            <td :data-label="t('usersAdmin.colEmployee')">
              {{ user.employee_name ?? user.employee_id ?? '—' }}
            </td>
            <td :data-label="t('usersAdmin.colActions')">
              <div class="users-admin-page__actions">
                <AppButton
                  variant="ghost"
                  @click="openEditDialog(user)"
                >
                  {{ t('usersAdmin.edit') }}
                </AppButton>
                <AppButton
                  variant="secondary"
                  :loading="toggling.has(user.id)"
                  @click="requestToggle(user)"
                >
                  {{ user.is_active ? t('usersAdmin.deactivate') : t('usersAdmin.activate') }}
                </AppButton>
                <AppButton
                  variant="ghost"
                  @click="openResetDialog(user)"
                >
                  {{ t('usersAdmin.resetPasswordAction') }}
                </AppButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav
      v-if="users.length"
      class="users-admin-page__pagination"
      :aria-label="t('usersAdmin.paginationLabel')"
    >
      <AppButton
        variant="ghost"
        :disabled="page <= 1"
        @click="goToPage(page - 1)"
      >
        {{ t('usersAdmin.prevPage') }}
      </AppButton>
      <span class="users-admin-page__page-indicator">{{ t('usersAdmin.pageIndicator', { page, totalPages }) }}</span>
      <AppButton
        variant="ghost"
        :disabled="page >= totalPages"
        @click="goToPage(page + 1)"
      >
        {{ t('usersAdmin.nextPage') }}
      </AppButton>
    </nav>

    <!-- Create / edit dialog -->
    <AppDialog
      :open="dialogOpen"
      :title="editingUser ? t('usersAdmin.editTitle') : t('usersAdmin.addTitle')"
      @close="closeDialog"
    >
      <form
        novalidate
        @submit.prevent="onSave"
      >
        <AppInput
          v-if="!editingUser"
          v-model="form.email"
          type="email"
          :label="t('usersAdmin.emailLabel')"
          :error="emailError"
          autocomplete="off"
          required
        />
        <div
          v-else
          class="users-admin-page__readonly-field"
        >
          <span class="users-admin-page__readonly-label">{{ t('usersAdmin.emailLabel') }}</span>
          <span class="users-admin-page__readonly-value">{{ form.email }}</span>
        </div>

        <AppInput
          v-model="form.displayName"
          :label="t('usersAdmin.displayNameLabel')"
          :error="displayNameError"
          required
        />

        <AppSelect
          v-model="form.role"
          :label="t('usersAdmin.roleLabel')"
          :options="roleOptions"
          :placeholder="t('usersAdmin.rolePlaceholder')"
          :error="roleError"
          required
        />

        <AppInput
          v-if="!editingUser"
          v-model="form.password"
          type="password"
          :label="t('usersAdmin.passwordLabel')"
          :hint="t('usersAdmin.passwordHint')"
          :error="passwordError"
          autocomplete="new-password"
          required
        />

        <AppToggle
          v-if="editingUser"
          v-model="form.isActive"
          :label="t('usersAdmin.activeToggleLabel')"
        />

        <AppInput
          v-model="form.employeeId"
          :label="t('usersAdmin.employeeIdLabel')"
          :hint="t('usersAdmin.employeeIdHint')"
        />

        <p
          v-if="formError"
          class="users-admin-page__error"
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

    <!-- Deactivate confirmation -->
    <AppDialog
      :open="deactivateTarget !== null"
      :title="t('usersAdmin.deactivateConfirmTitle')"
      @close="closeDeactivateConfirm"
    >
      <p v-if="deactivateTarget">
        {{ t('usersAdmin.deactivateConfirmMessage', { email: deactivateTarget.email }) }}
      </p>

      <template #footer>
        <AppButton
          variant="ghost"
          type="button"
          @click="closeDeactivateConfirm"
        >
          {{ t('common.cancel') }}
        </AppButton>
        <AppButton
          variant="danger"
          :loading="deactivateTarget !== null && toggling.has(deactivateTarget.id)"
          @click="confirmDeactivate"
        >
          {{ t('usersAdmin.deactivate') }}
        </AppButton>
      </template>
    </AppDialog>

    <!-- Reset password -->
    <AppDialog
      :open="resetTarget !== null"
      :title="t('usersAdmin.resetPassword.title')"
      @close="closeResetDialog"
    >
      <p v-if="resetTarget">
        {{ t('usersAdmin.resetPassword.message', { email: resetTarget.email }) }}
      </p>
      <AppInput
        v-model="resetPasswordValue"
        type="password"
        :label="t('usersAdmin.resetPassword.newPasswordLabel')"
        :hint="t('usersAdmin.passwordHint')"
        :error="resetPasswordError"
        autocomplete="new-password"
        required
      />

      <template #footer>
        <AppButton
          variant="ghost"
          type="button"
          @click="closeResetDialog"
        >
          {{ t('common.cancel') }}
        </AppButton>
        <AppButton
          :loading="resetting"
          @click="confirmReset"
        >
          {{ t('usersAdmin.resetPassword.submit') }}
        </AppButton>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.users-admin-page__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}

.users-admin-page__filters {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 var(--space-4);
  margin: var(--space-4) 0 var(--space-3);
}

@media (min-width: 640px) {
  .users-admin-page__filters {
    grid-template-columns: repeat(3, 1fr);
  }
}

.users-admin-page__filter-actions {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

.users-admin-page__error {
  color: var(--color-danger-text);
  font-weight: 600;
}

.users-admin-page__success {
  color: var(--color-text);
  font-weight: 600;
  background-color: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}

.users-admin-page__empty {
  color: var(--color-text-muted);
}

.users-admin-page__caption {
  text-align: left;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-2);
}

.users-admin-page__table-card {
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  overflow-x: auto;
}

.users-admin-page__table {
  width: 100%;
  border-collapse: collapse;
  /* M8-2 badges spec "等寬對齊": same-width AppBadge across colRole/colStatus. */
  --app-badge-min-width: 104px;
}

.users-admin-page__table th,
.users-admin-page__table td {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.users-admin-page__actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.users-admin-page__pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.users-admin-page__page-indicator {
  color: var(--color-text);
  font-weight: 600;
}

.users-admin-page__readonly-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}

.users-admin-page__readonly-label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text);
}

.users-admin-page__readonly-value {
  min-height: var(--touch-target-min);
  display: flex;
  align-items: center;
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-muted);
  background-color: var(--color-bg-subtle);
  border-radius: var(--radius-md);
}

/* Mobile card collapse (06 §2 Mobile-first, breakpoint 640) -- same pattern
   as SearchPage.vue / AuditLogsPage.vue / EmployeesAdminPage.vue. */
@media (max-width: 639px) {
  /* On the mobile card-collapse layout each row already renders as its own
     bordered card (below), so the outer table-card wrapper would otherwise
     double up as a nested card frame -- flatten it back to plain layout. */
  .users-admin-page__table-card {
    border: none;
    padding: 0;
    background: transparent;
    overflow-x: visible;
  }

  .users-admin-page__table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .users-admin-page__table,
  .users-admin-page__table tbody,
  .users-admin-page__table tr,
  .users-admin-page__table td {
    display: block;
    width: 100%;
  }

  .users-admin-page__table tr {
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-3);
  }

  .users-admin-page__table td {
    border-bottom: none;
    padding: var(--space-1) 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .users-admin-page__table td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--color-text-muted);
    flex-shrink: 0;
  }
}
</style>
