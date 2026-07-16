<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

// M6-HELP: role-aware user manual. Common sections (系統簡介/登入登出/我的
// 郵件) always show; the role-specific block(s) below are additive, not
// exclusive, because RBAC (01 §1) makes `admin` a superset of `counter`
// (counter's registration/pickup/outbound/search pages are all reachable by
// an admin too — see router/index.ts `requiresRole` arrays), so an admin
// landing here should see the counter walkthrough as well as the
// admin-only material, not just the latter.
const { t, tm, rt } = useI18n({ useScope: 'global' })
const auth = useAuthStore()

interface HelpSection {
  id: string
  titleKey: string
  itemsKey: string
}

const commonSections: HelpSection[] = [
  { id: 'help-intro', titleKey: 'help.intro.title', itemsKey: 'help.intro.items' },
  { id: 'help-login-logout', titleKey: 'help.loginLogout.title', itemsKey: 'help.loginLogout.items' },
  { id: 'help-my-mail-common', titleKey: 'help.myMailCommon.title', itemsKey: 'help.myMailCommon.items' },
]

const employeeSections: HelpSection[] = [
  { id: 'help-employee-my-mail', titleKey: 'help.employee.myMail.title', itemsKey: 'help.employee.myMail.items' },
  {
    id: 'help-employee-notifications',
    titleKey: 'help.employee.notifications.title',
    itemsKey: 'help.employee.notifications.items',
  },
  {
    id: 'help-employee-pickup-code',
    titleKey: 'help.employee.pickupCode.title',
    itemsKey: 'help.employee.pickupCode.items',
  },
]

const counterSections: HelpSection[] = [
  {
    id: 'help-counter-inbound-register',
    titleKey: 'help.counter.inboundRegister.title',
    itemsKey: 'help.counter.inboundRegister.items',
  },
  { id: 'help-counter-ocr-confirm', titleKey: 'help.counter.ocrConfirm.title', itemsKey: 'help.counter.ocrConfirm.items' },
  { id: 'help-counter-pickup', titleKey: 'help.counter.pickup.title', itemsKey: 'help.counter.pickup.items' },
  { id: 'help-counter-outbound', titleKey: 'help.counter.outbound.title', itemsKey: 'help.counter.outbound.items' },
  { id: 'help-counter-search', titleKey: 'help.counter.search.title', itemsKey: 'help.counter.search.items' },
]

const adminSections: HelpSection[] = [
  { id: 'help-admin-employees', titleKey: 'help.admin.employees.title', itemsKey: 'help.admin.employees.items' },
  { id: 'help-admin-ai-settings', titleKey: 'help.admin.aiSettings.title', itemsKey: 'help.admin.aiSettings.items' },
  { id: 'help-admin-webhooks', titleKey: 'help.admin.webhooks.title', itemsKey: 'help.admin.webhooks.items' },
  { id: 'help-admin-audit-logs', titleKey: 'help.admin.auditLogs.title', itemsKey: 'help.admin.auditLogs.items' },
  { id: 'help-admin-retention', titleKey: 'help.admin.retention.title', itemsKey: 'help.admin.retention.items' },
]

const viewerSections: HelpSection[] = [{ id: 'help-viewer', titleKey: 'help.viewer.title', itemsKey: 'help.viewer.items' }]

interface HelpGroup {
  key: string
  titleKey: string | null
  sections: HelpSection[]
}

// role gates: employee-only block for employee; counter block for
// counter+admin (admin can reach every counter page); admin-only block for
// admin; a short read-only note for viewer. Falls back to common-only
// content for an unexpected/missing role rather than showing nothing.
const groups = computed<HelpGroup[]>(() => {
  const role = auth.role
  const list: HelpGroup[] = [{ key: 'common', titleKey: null, sections: commonSections }]
  if (role === 'employee') {
    list.push({ key: 'employee', titleKey: 'help.employee.title', sections: employeeSections })
  }
  if (role === 'counter' || role === 'admin') {
    list.push({ key: 'counter', titleKey: 'help.counter.title', sections: counterSections })
  }
  if (role === 'admin') {
    list.push({ key: 'admin', titleKey: 'help.admin.title', sections: adminSections })
  }
  if (role === 'viewer') {
    list.push({ key: 'viewer', titleKey: 'help.viewer.title', sections: viewerSections })
  }
  return list
})

const tocEntries = computed(() => groups.value.flatMap((g) => g.sections))

function items(itemsKey: string): string[] {
  const raw = tm(itemsKey)
  // tm() returns precompiled message AST nodes (runtimeOnly i18n); rt() resolves each to a string.
  return Array.isArray(raw) ? (raw as unknown[]).map((line) => rt(line as string)) : []
}
</script>

<template>
  <section class="help-page">
    <h1 class="help-page__title">
      {{ t('help.title') }}
    </h1>

    <nav
      class="help-page__toc"
      :aria-label="t('help.tocLabel')"
    >
      <ul>
        <li
          v-for="entry in tocEntries"
          :key="entry.id"
        >
          <a :href="`#${entry.id}`">{{ t(entry.titleKey) }}</a>
        </li>
      </ul>
    </nav>

    <template
      v-for="group in groups"
      :key="group.key"
    >
      <h2
        v-if="group.titleKey"
        class="help-page__group-title"
      >
        {{ t(group.titleKey) }}
      </h2>
      <section
        v-for="entry in group.sections"
        :id="entry.id"
        :key="entry.id"
        class="help-page__section"
      >
        <component
          :is="group.titleKey ? 'h3' : 'h2'"
          class="help-page__section-title"
        >
          {{ t(entry.titleKey) }}
        </component>
        <ul class="help-page__list">
          <li
            v-for="line in items(entry.itemsKey)"
            :key="line"
          >
            {{ line }}
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.help-page {
  max-width: 720px;
}

.help-page__title {
  font-size: var(--font-size-2xl);
  color: var(--color-text);
  margin: 0 0 var(--space-4);
}

.help-page__toc {
  padding: var(--space-4);
  margin-bottom: var(--space-6);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
}

.help-page__toc ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
}

.help-page__toc a {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target-min);
  font-weight: 600;
}

.help-page__group-title {
  font-size: var(--font-size-xl);
  color: var(--color-text);
  margin: var(--space-6) 0 var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 2px solid var(--brand-primary);
}

.help-page__section {
  margin-bottom: var(--space-5);
  scroll-margin-top: var(--space-4);
}

.help-page__section-title {
  font-size: var(--font-size-lg);
  color: var(--color-text);
  margin: 0 0 var(--space-2);
}

.help-page__list {
  margin: 0;
  padding-left: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  color: var(--color-text);
  line-height: var(--line-height-base);
}

@media (max-width: 639px) {
  .help-page__toc ul {
    flex-direction: column;
    gap: var(--space-1);
  }
}
</style>
