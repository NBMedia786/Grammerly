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

async function _streamAnalyze(url, init, onProgress) {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try { const j = await res.json(); if (j && j.detail) detail = j.detail } catch (_) {}
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = '', result = null, errDetail = null
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const frames = buf.split('\n\n'); buf = frames.pop()
    for (const f of frames) {
      let event = 'message', data = ''
      for (const line of f.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let parsed; try { parsed = JSON.parse(data) } catch (_) { continue }
      if (event === 'stages') onProgress && onProgress({ type: 'stages', stages: parsed.stages })
      else if (event === 'progress') onProgress && onProgress({ type: 'progress', stage: parsed.stage })
      else if (event === 'result') result = parsed
      else if (event === 'error') errDetail = parsed.detail
    }
  }
  if (errDetail) throw new Error(errDetail)
  if (!result) throw new Error('No result received from the server.')
  return result
}

export function analyzeTextStream(text, onProgress) {
  return _streamAnalyze('/api/analyze-stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
  }, onProgress)
}
export function analyzeFileStream(file, onProgress) {
  const fd = new FormData(); fd.append('file', file)
  return _streamAnalyze('/api/analyze-file-stream', { method: 'POST', body: fd }, onProgress)
}
