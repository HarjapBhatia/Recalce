/**
 * api.js
 * Centralises all calls to the Recalce backend.
 * Base URL is hardcoded to localhost:8000 for local development.
 */

const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const BASE = rawBase.endsWith('/api/v1') ? rawBase : `${rawBase.replace(/\/+$/, '')}/api/v1`

/** POST /upload — multipart, both CSV files */
export async function uploadFiles(internalFile, bankFile) {
  const form = new FormData()
  form.append('internal_ledger', internalFile)
  form.append('bank_statement', bankFile)

  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json() // { batch_id, status, uploaded_at, message }
}

/** GET /status/{batch_id} */
export async function getBatchStatus(batchId) {
  const res = await fetch(`${BASE}/status/${batchId}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Status fetch failed')
  }
  return res.json() // { batch_id, status, uploaded_at, error_message }
}

/** GET /batches — list all batches, newest first */
export async function listBatches() {
  const res = await fetch(`${BASE}/batches`)
  if (!res.ok) return []
  return res.json() // BatchListItem[]
}

/** GET /results/{batch_id} */
export async function getResults(batchId, params = {}) {
  const url = new URL(`${BASE}/results/${batchId}`)
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.append(key, value)
  }
  const res = await fetch(url)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Results fetch failed')
  }
  return res.json()
}

/** POST /results/{result_id}/match */
export async function markMatched(resultId) {
  const res = await fetch(`${BASE}/results/${resultId}/match`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Failed to mark as matched')
  }
  return res.json()
}
