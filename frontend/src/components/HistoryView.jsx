import React from 'react'
import StorageBar from './StorageBar.jsx'

export default function HistoryView({ items, usage, onOpen, onDelete, onBack }) {
  return (
    <div className="historyview">
      <div className="history-head">
        <button className="btn ghost" onClick={onBack}>← Back</button>
        <h2>History</h2>
      </div>
      <StorageBar usage={usage} />
      {(!items || items.length === 0) ? (
        <p className="muted">No saved reviews yet.</p>
      ) : (
        <ul className="history-list">
          {items.map((it) => (
            <li key={it.id} className="history-row">
              <button className="history-open" onClick={() => onOpen(it.id)}>
                <span className="history-title">{it.title}</span>
                <span className="history-meta">{it.created_at} · Overall {it.overall_rating || '—'}/10</span>
              </button>
              <button className="btn ghost danger" onClick={() => onDelete(it.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
