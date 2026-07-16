// IndexedDB wrapper for the M2 offline capture queue (06-UI-UX.md §2:
// "離線佇列:無網路時拍的照片與表單存 IndexedDB,恢復連線自動補送"). Kept
// tiny and isolated behind `idb` so src/offline/queue.ts never touches the
// raw IDB callback API.
import { openDB, type IDBPDatabase } from 'idb'

export const DB_NAME = 'openmailroom-offline-queue'
export const DB_VERSION = 1
export const STORE_NAME = 'pending-registrations'

let dbPromise: Promise<IDBPDatabase> | null = null

export function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        }
      },
    })
  }
  return dbPromise
}

/**
 * Test-only: drops the cached connection so a fresh `getDb()` call re-opens
 * against whatever IndexedDB implementation is currently installed as the
 * global (tests swap in `fake-indexeddb` per-test). Not used by app code.
 */
export async function __resetDbForTests(): Promise<void> {
  if (dbPromise) {
    const db = await dbPromise
    db.close()
  }
  dbPromise = null
}
