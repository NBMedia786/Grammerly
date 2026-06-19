import React from 'react'

const BAND = {
  low: { color: '#2e9e5b', label: 'Low' },
  medium: { color: '#d9a400', label: 'Medium' },
  high: { color: '#e5484d', label: 'High' },
}

export default function OriginalityPanel({ data }) {
  if (!data) return null
  const ai = data.ai_detection || {}
  const plag = data.plagiarism || {}
  const band = BAND[ai.band] || BAND.low
  return (
    <div className="orig-panel">
      <div className="orig-title">Originality <span className="orig-tag">best-effort</span></div>

      <div className="orig-row">
        <div className="orig-row-top">
          <span>AI likelihood</span>
          <strong style={{ color: band.color }}>{ai.likelihood ?? 0}% · {band.label}</strong>
        </div>
        <div className="orig-meter"><div className="orig-meter-fill" style={{ width: `${ai.likelihood || 0}%`, background: band.color }} /></div>
        {ai.reasoning && <p className="orig-note">{ai.reasoning}</p>}
        {ai.disclaimer && <p className="orig-disclaimer">{ai.disclaimer}</p>}
      </div>

      <div className="orig-row">
        <div className="orig-row-top">
          <span>Plagiarism</span>
          <strong>{plag.count || 0} match{(plag.count || 0) === 1 ? '' : 'es'}</strong>
        </div>
        <p className="orig-note">
          {plag.web_grounded ? 'Checked against Google Search. ' : 'Web search unavailable. '}
          Verbatim web matches only — paraphrasing isn't detected. Verify manually.
        </p>
      </div>
    </div>
  )
}
