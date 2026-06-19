import React, { useEffect, useRef } from 'react'
import { buildSegments } from '../highlight.js'

// Renders the script as plain text with inline <mark> highlights.
// Clicking a highlight selects it (opens its card in the sidebar).
export default function ScriptView({ text, spans, decisions, aoi, activeAid, onSelect }) {
  const segments = buildSegments(text, spans, decisions, aoi)
  const activeRef = useRef(null)

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [activeAid])

  let markKey = 0
  return (
    <div className="docwrap">
      <p className="doc">
        {segments.map((seg, i) => {
          if (seg.kind === 'text') return <span key={`t${i}`}>{seg.text}</span>
          const isActive = seg.aid === activeAid
          const cls = `mark mark-${seg.state}${isActive ? ' active' : ''}`
          const style =
            seg.state === 'applied'
              ? undefined
              : { background: seg.color + '33', borderColor: seg.color }
          return (
            <mark
              key={`m${markKey++}`}
              ref={isActive ? activeRef : null}
              className={cls}
              style={style}
              title={seg.state === 'applied' ? 'Fix applied — click to review' : 'Click to see the suggestion'}
              onClick={() => onSelect(seg.aid)}
            >
              {seg.text}
            </mark>
          )
        })}
      </p>
    </div>
  )
}
