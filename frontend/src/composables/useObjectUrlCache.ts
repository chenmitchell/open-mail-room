import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

export interface HasBlobId {
  id: string
  blob: Blob
}

/**
 * POLISH-AUDIT.md Nice #15: PhotoRegisterPage.vue / BatchUploadPage.vue used
 * to call `URL.createObjectURL(photo.blob)` directly inside a template
 * expression (`objectUrl(photo.blob)`). Every reactive re-render re-ran that
 * expression and minted a brand-new blob: URL for the same photo, and none
 * of them were ever revoked -- a straightforward memory leak that grows with
 * every keystroke/re-render for as long as the photo stays in the list, not
 * just per-photo.
 *
 * This caches one object URL per item id, created lazily on first access and
 * revoked automatically both when the item is removed from `items` (retake/
 * remove buttons) and when the owning component unmounts (route away
 * mid-batch).
 */
export function useObjectUrlCache<T extends HasBlobId>(items: Ref<T[]>) {
  const urls = ref(new Map<string, string>())

  function sync(list: T[]) {
    const currentIds = new Set(list.map((item) => item.id))
    for (const [id, url] of urls.value) {
      if (!currentIds.has(id)) {
        URL.revokeObjectURL(url)
        urls.value.delete(id)
      }
    }
    for (const item of list) {
      if (!urls.value.has(item.id)) {
        urls.value.set(item.id, URL.createObjectURL(item.blob))
      }
    }
  }

  // Watch the *set of ids* (a fresh array each change) so that adding a photo
  // by mutating the list (`items.value.push(...)`) also triggers sync -- a plain
  // `watch(items, ...)` without deep does NOT fire on in-place array push, which
  // left newly-captured photos with no object URL (broken <img>, 破圖)。
  watch(
    () => items.value.map((item) => item.id),
    () => sync(items.value),
    { immediate: true },
  )

  onBeforeUnmount(() => {
    for (const url of urls.value.values()) {
      URL.revokeObjectURL(url)
    }
    urls.value.clear()
  })

  function getUrl(id: string): string {
    return urls.value.get(id) ?? ''
  }

  return { getUrl }
}
