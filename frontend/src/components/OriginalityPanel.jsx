import React from 'react'

const BAND = {
  low: { color: '#2e9e5b', label: 'Low' },
  medium: { color: '#d9a400', label: 'Medium' },
  high: { color: '#e5484d', label: 'High' },
}

function plagColor(pct) {
  if (pct == null) return '#6b7280'
  if (pct >= 40) return '#e5484d'
  if (pct >= 15) return '#d9a400'
  return '#2e9e5b'
}

export default function OriginalityPanel({ data }) {
  if (!data) return null
  const ai = data.ai_detection || {}
  const plag = data.plagiarism || {}
  const band = BAND[ai.band] || BAND.low
  const isCopyleaks = plag.engine === 'copyleaks'
  return (
    <div className="orig-panel">
      <div className="orig-title">
        Originality{!isCopyleaks && <span className="orig-tag">best-effort</span>}
      </div>

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
        {isCopyleaks ? <PlagCopyleaks plag={plag} /> : <PlagGemini plag={plag} />}
      </div>
    </div>
  )
}

function PlagCopyleaks({ plag }) {
  if (plag.status === 'pending') {
    return (
      <>
        <div className="orig-row-top"><span>Plagiarism <span className="orig-tag">Copyleaks</span></span><strong>Scanning…</strong></div>
        <div className="orig-meter"><div className="orig-meter-fill orig-pulse" style={{ width: '100%', background: '#c7c2f0' }} /></div>
        <p className="orig-note">Checking your text against the web with Copyleaks — this can take up to a minute.</p>
      </>
    )
  }
  if (plag.status === 'error' || plag.status === 'timeout') {
    return (
      <>
        <div className="orig-row-top"><span>Plagiarism <span className="orig-tag">Copyleaks</span></span><strong>—</strong></div>
        <p className="orig-note">
          {plag.status === 'timeout'
            ? 'The scan is taking longer than expected — try again in a moment.'
            : (plag.error || 'The plagiarism scan failed.')}
        </p>
      </>
    )
  }
  const pct = plag.percent
  const color = plagColor(pct)
  const sources = plag.sources || []
  return (
    <>
      <div className="orig-row-top">
        <span>Plagiarism <span className="orig-tag">Copyleaks</span></span>
        <strong style={{ color }}>{pct == null ? '—' : `${pct}% similar`}</strong>
      </div>
      <div className="orig-meter"><div className="orig-meter-fill" style={{ width: `${pct || 0}%`, background: color }} /></div>
      {typeof plag.totalWords === 'number' && (
        <p className="orig-note">
          {plag.totalWords} words scanned
          {sources.length ? ` · ${sources.length} matched source${sources.length === 1 ? '' : 's'}` : ' · no matching sources found'}.
        </p>
      )}
      {sources.length > 0 && (
        <ul className="orig-sources">
          {sources.map((s, i) => (
            <li key={i}>
              {s.url
                ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                : <span>{s.title || 'source'}</span>}
              {typeof s.matchedWords === 'number' && <span className="orig-src-meta"> · {s.matchedWords} words</span>}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function PlagGemini({ plag }) {
  return (
    <>
      <div className="orig-row-top">
        <span>Plagiarism</span>
        <strong>{plag.count || 0} match{(plag.count || 0) === 1 ? '' : 'es'}</strong>
      </div>
      <p className="orig-note">
        {plag.web_grounded ? 'Checked against Google Search. ' : 'Web search unavailable. '}
        Verbatim web matches only — paraphrasing isn't detected. Verify manually.
      </p>
    </>
  )
}
