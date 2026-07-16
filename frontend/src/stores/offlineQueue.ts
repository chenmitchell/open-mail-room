// Reactive glue around src/offline/queue.ts for the UI (06 §2: "UI 顯示
// 「離線,已排入佇列」與佇列數"). The enqueue/flush *logic* is unit-tested
// directly against src/offline/queue.ts (fake-indexeddb); this store is thin
// wiring (online/offline listeners + counts) and is exercised indirectly via
// the pages that use it.
import { defineStore } from 'pinia'
import { uploadPhotos as apiUploadPhotos } from '@/api/uploads'
import { createOcrJob } from '@/api/ocr'
import {
  clearRegistrations,
  countRegistrations,
  enqueueRegistration,
  flushRegistrations,
  type PendingPhoto,
  type PendingRegistration,
} from '@/offline/queue'

interface OfflineQueueState {
  pendingCount: number
  isOnline: boolean
  flushing: boolean
  listenersRegistered: boolean
}

export const useOfflineQueueStore = defineStore('offlineQueue', {
  state: (): OfflineQueueState => ({
    pendingCount: 0,
    isOnline: typeof navigator === 'undefined' ? true : navigator.onLine,
    flushing: false,
    listenersRegistered: false,
  }),

  actions: {
    async refreshCount(): Promise<void> {
      this.pendingCount = await countRegistrations()
    },

    async enqueue(input: Omit<PendingRegistration, 'id' | 'createdAt'>): Promise<PendingRegistration> {
      const record = await enqueueRegistration(input)
      await this.refreshCount()
      return record
    },

    async flush(): Promise<void> {
      if (this.flushing || !this.isOnline) return
      this.flushing = true
      try {
        await flushRegistrations({
          uploadPhotos: async (photos: PendingPhoto[]) => {
            const { attachmentIds, failures } = await apiUploadPhotos(
              photos.map((p) => ({ localId: p.photoId, blob: p.blob, filename: p.filename })),
            )
            const firstFailure = Object.values(failures)[0]
            if (firstFailure) throw firstFailure
            return photos.map((p) => attachmentIds[p.photoId])
          },
          createOcrJob: (attachmentIds: string[], barcodeHints?: Record<string, string>) =>
            createOcrJob(attachmentIds, barcodeHints),
        })
      } finally {
        this.flushing = false
        await this.refreshCount()
      }
    },

    // M2-R1 suggestion (adopted): the offline queue stores captured photos +
    // any typed-in fields un-encrypted in IndexedDB (06-UI-UX.md §2) so a
    // shared/kiosk device left logged in after a counter's shift keeps
    // whatever was still queued (unsent because there was no network)
    // sitting in browser storage indefinitely. Clearing it on logout bounds
    // that exposure to "still queued at the moment this specific counter
    // logged out" rather than "forever, until someone manually flushes the
    // IndexedDB store". Never allowed to throw/block logout -- IndexedDB may
    // be unavailable (private browsing, already closed, ...) and that must
    // never prevent the session itself from ending.
    async clearOnLogout(): Promise<void> {
      try {
        await clearRegistrations()
      } catch {
        // best-effort; see comment above.
      } finally {
        this.pendingCount = 0
      }
    },

    /** Call once from app startup (e.g. AppShell) to keep the queue live. */
    initListeners(): void {
      if (this.listenersRegistered || typeof window === 'undefined') return
      this.listenersRegistered = true
      this.isOnline = navigator.onLine
      window.addEventListener('online', () => {
        this.isOnline = true
        void this.flush()
      })
      window.addEventListener('offline', () => {
        this.isOnline = false
      })
      void this.refreshCount()
    },
  },
})
