import React, { useEffect, useRef } from 'react'
import { buildSegments } from '../highlight.js'

// Renders the script with inline <mark> highlights. Clicking a highlight selects it.
// When `layout` (a VO|Visuals table) is present, renders two columns and maps the
// highlight spans onto each VO cell; otherwise renders the flat single-column view.
export default function ScriptView({ text, layout, spans, decisions, aoi, activeAid, onSelect }) {
  const activeRef = useRef(null)

  useEffect(() => {
    const el = activeRef.current
    if (!el) return
    // Scroll the SCRIPT panel (the .main scroll container) to center the active sentence.
    // Scoped to .main so it isn't affected by the sticky sidebar's own scrolling.
    const container = el.closest('.main')
    if (!container) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); return }
    const delta = el.getBoundingClientRect().top - container.getBoundingClientRect().top
      - container.clientHeight / 2 + el.clientHeight / 2
    container.scrollBy({ top: delta, behavior: 'smooth' })
  }, [activeAid])

  // Render an array of {kind:'text'|'mark', ...} segments into spans/marks.
  function renderSegments(segments, keyPrefix) {
    return segments.map((seg, i) => {
      if (seg.kind === 'text') return <span key={`${keyPrefix}t${i}`}>{seg.text}</span>
      const isActive = seg.aid === activeAid
      const cls = `mark mark-${seg.state}${isActive ? ' active' : ''}`
      const style = seg.state === 'applied'
        ? undefined
        : { '--mk': seg.color, borderBottomColor: seg.color }
      return (
        <mark
          key={`${keyPrefix}m${i}`}
          ref={isActive ? activeRef : null}
          className={cls}
          style={style}
          title={seg.state === 'applied' ? 'Fix applied — click to review' : 'Click to see the suggestion'}
          onClick={() => onSelect(seg.aid)}
        >
          {seg.text}
        </mark>
      )
    })
  }

  // --- Two-column VO | Visuals layout ---
  if (layout && Array.isArray(layout.rows) && layout.rows.length) {
    return (
      <div className="docwrap docwrap-wide">
        {layout.preamble && <div className="vo-preamble">{layout.preamble}</div>}
        <div className="vo-table">
          <div className="vo-row vo-head">
            <div className="vo-cell">Voice Over</div>
            <div className="vis-cell">Visuals</div>
          </div>
          {layout.rows.map((row, ri) => {
            const voText = text.slice(row.vo_start, row.vo_end)
            const rowSpans = (spans || [])
              .filter((s) => s.start >= row.vo_start && s.end <= row.vo_end)
              .map((s) => ({ ...s, start: s.start - row.vo_start, end: s.end - row.vo_start }))
            const segs = buildSegments(voText, rowSpans, decisions, aoi)
            return (
              <div className="vo-row" key={`r${ri}`}>
                <div className="vo-cell">{renderSegments(segs, `r${ri}-`)}</div>
                <div className="vis-cell">{row.visuals || ''}</div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // --- Single-column flat view ---
  const segments = buildSegments(text, spans, decisions, aoi)
  return (
    <div className="docwrap">
      <p className="doc">{renderSegments(segments, 's-')}</p>
    </div>
  )
}
