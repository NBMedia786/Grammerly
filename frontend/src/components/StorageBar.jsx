import React from 'react'

function gb(bytes) { return (bytes / (1024 ** 3)).toFixed(2) }

export default function StorageBar({ usage }) {
  if (!usage) return null
  const pct = Math.min(100, usage.percent || 0)
  const danger = pct >= 90
  return (
    <div className="storagebar">
      <div className="storagebar-label">
        History storage: {gb(usage.used_bytes)} GB of {gb(usage.quota_bytes)} GB ({pct.toFixed(1)}%)
      </div>
      <div className="storagebar-track">
        <div className={`storagebar-fill ${danger ? 'danger' : ''}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
