const DATABASE_NAME = 'fieldnotes-interview-outbox'
const STORE_NAME = 'pending-events'
let databasePromise
let memoryEntries = []
let flushPromise

function openDatabase() {
  if (!('indexedDB' in window)) return Promise.resolve(null)
  if (!databasePromise) {
    databasePromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE_NAME, 1)
      request.onupgradeneeded = () => {
        request.result.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    }).catch(() => null)
  }
  return databasePromise
}

function withStore(mode, operation) {
  return openDatabase().then((database) => {
    if (!database) return operation(null)
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, mode)
      const store = transaction.objectStore(STORE_NAME)
      const result = operation(store)
      transaction.oncomplete = () => resolve(result?.result ?? result)
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error)
    })
  })
}

export async function enqueue(entry) {
  const item = { ...entry, id: crypto.randomUUID(), created_at: Date.now() }
  try {
    await withStore('readwrite', (store) => store ? store.put(item) : memoryEntries.push(item))
  } catch {
    memoryEntries.push(item)
  }
  return item.id
}

export async function queuedCount(sessionId) {
  const items = await getAll()
  return items.filter((item) => item.session_id === sessionId).length
}

async function getAll() {
  try {
    const database = await openDatabase()
    if (!database) return [...memoryEntries]
    return await new Promise((resolve, reject) => {
      const request = database.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).getAll()
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
  } catch {
    return [...memoryEntries]
  }
}

async function remove(id) {
  memoryEntries = memoryEntries.filter((item) => item.id !== id)
  await withStore('readwrite', (store) => store?.delete(id)).catch(() => {})
}

export function flushOutbox(sessionId, send) {
  if (flushPromise) return flushPromise
  flushPromise = (async () => {
    const entries = (await getAll())
      .filter((item) => item.session_id === sessionId)
      .sort((left, right) => left.created_at - right.created_at)
    for (const entry of entries) {
      try {
        await send(entry)
        await remove(entry.id)
      } catch {
        break
      }
    }
    return queuedCount(sessionId)
  })().finally(() => { flushPromise = undefined })
  return flushPromise
}