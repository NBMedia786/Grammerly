// Pure helpers for turning (text + spans + decisions) into render segments
// and into the final edited script. Offsets are always against the ORIGINAL
// text; "applied" only changes what is *displayed* inside a span, never the
// offsets — so highlights can never drift.

export function mergeNonOverlap(spans) {
  const sorted = [...spans].sort((a, b) => a.start - b.start || b.end - a.end)
  const out = []
  let lastEnd = -1
  for (const sp of sorted) {
    if (sp.start >= lastEnd) {
      out.push(sp)
      lastEnd = sp.end
    }
  }
  return out
}

// segments: { kind:'text', text } | { kind:'mark', aid, color, state, text }
export function buildSegments(text, spans, decisions, aoi) {
  const used = mergeNonOverlap(spans)
  const segs = []
  let cur = 0
  for (const sp of used) {
    if (sp.start > cur) segs.push({ kind: 'text', text: text.slice(cur, sp.start) })
    const dec = decisions[sp.aid]
    const orig = text.slice(sp.start, sp.end)
    if (dec === 'dismissed') {
      segs.push({ kind: 'text', text: orig })
    } else if (dec === 'applied') {
      segs.push({ kind: 'mark', aid: sp.aid, color: sp.color, state: 'applied', text: (aoi[sp.aid]?.fix || orig) })
    } else {
      segs.push({ kind: 'mark', aid: sp.aid, color: sp.color, state: 'open', text: orig })
    }
    cur = sp.end
  }
  if (cur < text.length) segs.push({ kind: 'text', text: text.slice(cur) })
  return segs
}

export function buildEditedText(text, spans, decisions, aoi) {
  const used = mergeNonOverlap(spans)
  let out = ''
  let cur = 0
  for (const sp of used) {
    out += text.slice(cur, sp.start)
    const dec = decisions[sp.aid]
    if (dec === 'applied') out += (aoi[sp.aid]?.fix || text.slice(sp.start, sp.end))
    else out += text.slice(sp.start, sp.end)
    cur = sp.end
  }
  out += text.slice(cur)
  return out
}

export async function copyToClipboard(textToCopy) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(textToCopy)
      return true
    }
  } catch (_) { /* fall through */ }
  try {
    const ta = document.createElement('textarea')
    ta.value = textToCopy
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch (_) {
    return false
  }
}
