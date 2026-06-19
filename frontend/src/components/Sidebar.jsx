import React, { useEffect, useMemo, useRef, useState } from 'react'

function gb(bytes) { return (Number(bytes || 0) / (1024 ** 3)).toFixed(2) }

function shortDate(iso) {
  if (!iso) return ''
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (!m) return iso
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[+m[2] - 1]} ${+m[3]}, ${m[4]}:${m[5]}`
}

export default function Sidebar({ items, usage, activeId, onNew, onOpen, onDelete, onRename }) {
  const [q, setQ] = useState('')
  const [menuFor, setMenuFor] = useState(null)   // id whose ⋯ menu is open
  const [renameFor, setRenameFor] = useState(null) // id being renamed
  const [draft, setDraft] = useState('')
  const renameRef = useRef(null)

  const list = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return ql ? (items || []).filter((it) => (it.title || '').toLowerCase().includes(ql)) : (items || [])
  }, [items, q])

  // close the ⋯ menu on any outside click
  useEffect(() => {
    if (!menuFor) return
    const close = (e) => { if (!e.target.closest('.sb-menu-wrap')) setMenuFor(null) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [menuFor])

  useEffect(() => {
    if (renameFor && renameRef.current) { renameRef.current.focus(); renameRef.current.select() }
  }, [renameFor])

  function startRename(it) {
    setMenuFor(null); setRenameFor(it.id); setDraft(it.title || '')
  }
  function commitRename(id) {
    const t = draft.trim()
    setRenameFor(null)
    if (t) onRename(id, t)
  }

  const pct = Math.min(100, usage?.percent || 0)
  const meterCls = pct >= 90 ? 'danger' : pct >= 70 ? 'warn' : ''

  return (
    <aside className="sidebar">
      <div className="sb-brand"><span className="dot" /> Writing Assistant</div>

      <button className="sb-new" onClick={onNew}><span aria-hidden>+</span> New review</button>

      <div className="sb-section">History</div>
      <div className="sb-search">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search reviews…" aria-label="Search reviews" />
      </div>

      <div className="sb-list">
        {list.length === 0 ? (
          <div className="sb-empty">{q ? 'No matches.' : 'No saved reviews yet.'}</div>
        ) : (
          list.map((it) => (
            <div key={it.id} className={`sb-item ${it.id === activeId ? 'active' : ''}`}>
              {renameFor === it.id ? (
                <input
                  ref={renameRef}
                  className="sb-rename"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitRename(it.id)
                    if (e.key === 'Escape') setRenameFor(null)
                  }}
                  onBlur={() => commitRename(it.id)}
                />
              ) : (
                <>
                  <button className="sb-item-open" onClick={() => onOpen(it.id)} title={it.title}>
                    <span className="sb-item-title">{it.title || 'Untitled'}</span>
                    <span className="sb-item-meta">{shortDate(it.created_at)}</span>
                  </button>

                  {it.overall_rating !== '' && it.overall_rating != null && (
                    <span className="sb-score">{it.overall_rating}</span>
                  )}

                  <div className="sb-menu-wrap">
                    <button
                      className="sb-kebab" aria-label="More options"
                      onClick={() => setMenuFor(menuFor === it.id ? null : it.id)}
                    >⋯</button>
                    {menuFor === it.id && (
                      <div className="sb-menu" role="menu">
                        <button onClick={() => { setMenuFor(null); onOpen(it.id) }}>Open</button>
                        <button onClick={() => startRename(it)}>Rename</button>
                        <button className="danger" onClick={() => { setMenuFor(null); onDelete(it.id) }}>Delete</button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
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
