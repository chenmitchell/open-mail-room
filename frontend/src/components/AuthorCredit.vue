<script setup lang="ts">
/**
 * Attribution to the original author, shown in the app's UI.
 *
 * This is the "Appropriate Legal Notices" credit required by the project's
 * licence: AGPL-3.0 plus the Section 7(b) attribution term in the repo's
 * NOTICE file. A self-hoster may restyle it to match their own branding, but
 * the credit to the original author and the link back to the upstream
 * repository must stay — that is the one thing the licence asks in return for
 * letting you use, modify, and self-host this freely.
 *
 * Please keep it.
 */
</script>

<template>
  <p class="author-credit">
    <a
      href="https://github.com/chenmitchell/open-mail-room"
      target="_blank"
      rel="noopener noreferrer"
    >Open Mail Room</a>
    ·
    <span class="author-credit__by">原作者</span>
    <a
      href="https://github.com/chenmitchell"
      target="_blank"
      rel="noopener noreferrer"
    >Mitchell Chen</a>
  </p>
</template>

<style scoped>
.author-credit {
  margin: 0;
  padding: var(--space-3) 0;
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.author-credit__by {
  margin: 0 0.35em;
}

.author-credit a {
  color: var(--color-text-muted);
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

.author-credit a:hover {
  color: var(--brand-primary);
  border-bottom-color: currentColor;
}
</style>
