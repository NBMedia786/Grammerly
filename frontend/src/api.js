// Thin API client for the FastAPI backend.

export async function analyzeFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch('/api/analyze', { method: 'POST', body: fd })
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const j = await res.json()
      if (j && j.detail) detail = j.detail
    } catch (_) { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

async function _json(res) {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try { const j = await res.json(); if (j && j.detail) detail = j.detail } catch (_) {}
    throw new Error(detail)
  }
  return res.json()
}

export async function analyzeText(text) {
  return _json(await fetch('/api/analyze-text', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }))
}

export async function getHistory() { return _json(await fetch('/api/history')) }
export async function getHistoryItem(id) { return _json(await fetch(`/api/history/${id}`)) }
export async function deleteHistoryItem(id) {
  return _json(await fetch(`/api/history/${id}`, { method: 'DELETE' }))
}
export async function renameHistoryItem(id, title) {
  return _json(await fetch(`/api/history/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  }))
}
export async function getStorage() { return _json(await fetch('/api/storage')) }

export async function checkOriginality(text) {
  return _json(await fetch('/api/originality', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }))
}
