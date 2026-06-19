import React, { useMemo, useState } from 'react'

function gb(bytes) { return (Number(bytes || 0) / (1024 ** 3)).toFixed(2) }

function shortDate(iso) {
  if (!iso) return ''
  // created_at is "YYYY-MM-DDTHH:MM:SS" — show "Jun 19, 14:32"
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (!m) return iso
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[+m[2] - 1]} ${+m[3]}, ${m[4]}:${m[5]}`
}

export default function Sidebar({ items, usage, activeId, onNew, onOpen, onDelete }) {
  const [q, setQ] = useState('')
  const list = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return ql ? (items || []).filter((it) => (it.title || '').toLowerCase().includes(ql)) : (items || [])
  }, [items, q])

  const pct = Math.min(100, usage?.percent || 0)
  const meterCls = pct >= 90 ? 'danger' : pct >= 70 ? 'warn' : ''

  return (
    <aside className="sidebar">
      <div className="sb-brand"><span className="dot" /> Writing Assistant</div>

      <button className="sb-new" onClick={onNew}>
        <span aria-hidden>+</span> New review
      </button>

      <div className="sb-section">History</div>
      <div className="sb-search">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search reviews…"
          aria-label="Search reviews"
        />
      </div>

      <div className="sb-list">
        {list.length === 0 ? (
          <div className="sb-empty">{q ? 'No matches.' : 'No saved reviews yet.'}</div>
        ) : (
          list.map((it) => (
            <button
              key={it.id}
              className={`sb-item ${it.id === activeId ? 'active' : ''}`}
              onClick={() => onOpen(it.id)}
              title={it.title}
            >
              <span className="sb-item-body">
                <span className="sb-item-title">{it.title || 'Untitled'}</span>
                <span className="sb-item-meta">{shortDate(it.created_at)}</span>
              </span>
              {it.overall_rating !== '' && it.overall_rating != null && (
                <span className="sb-score">{it.overall_rating}</span>
              )}
              <span
                className="sb-del"
                role="button"
                aria-label="Delete review"
                title="Delete permanently"
                onClick={(e) => { e.stopPropagation(); onDelete(it.id) }}
              >
                ×
              </span>
            </button>
          ))
        )}
      </div>

      <div className="sb-storage">
        <div className="sb-storage-top">
          <span>Storage</span>
          <span><b>{gb(usage?.used_bytes)}</b> / {gb(usage?.quota_bytes)} GB</span>
        </div>
        <div className="sb-meter">
          <div className={`sb-meter-fill ${meterCls}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
    </aside>
  )
}
