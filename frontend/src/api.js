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
