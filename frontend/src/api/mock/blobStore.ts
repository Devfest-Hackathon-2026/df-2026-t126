// 録画の本体を IndexedDB（ブラウザ内の保存領域）に置く。
// localStorage には動画を入れられないため、モックの録画だけここに保存する。

const DB_NAME = 'gesture-relay-mock'
const STORE = 'blobs'

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function run<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const request = work(db.transaction(STORE, mode).objectStore(STORE))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export function putBlob(id: string, blob: Blob): Promise<IDBValidKey> {
  return run('readwrite', (store) => store.put(blob, id))
}

export function getBlob(id: string): Promise<Blob | undefined> {
  return run<Blob | undefined>('readonly', (store) => store.get(id))
}

export function deleteBlob(id: string): Promise<undefined> {
  return run('readwrite', (store) => store.delete(id))
}
