import React, { useEffect, useRef } from 'react'
import { copyToClipboard } from '../highlight.js'

const VERDICT = {
  incorrect: { label: '✗ Incorrect', cls: 'v-bad' },
  unverifiable: { label: '? Unverifiable', cls: 'v-warn' },
  correct: { label: '✓ Correct', cls: 'v-ok' },
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}

function SuggestionCard({ item, color, decision, isActive, onSelect, onDecision }) {
  const ref = useRef(null)
  const [copied, setCopied] = React.useState(false)
  const isFact = item.kind === 'fact'

  useEffect(() => {
    if (isActive && ref.current) ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [isActive])

  const doCopy = async (e) => {
    e.stopPropagation()
    const ok = await copyToClipboard(item.fix || item.line || '')
    if (ok) { setCopied(true); setTimeout(() => setCopied(false), 1300) }
  }

  const v = isFact ? (VERDICT[item.verdict] || VERDICT.unverifiable) : null
  const canApply = item.matched && item.fix
  const applyLabel = isFact ? 'Apply correction' : 'Apply'

  return (
    <div
      ref={ref}
      className={`card ${decision ? `card-${decision}` : ''} ${isActive ? 'active' : ''}`}
      style={{ borderLeftColor: color }}
      onClick={() => onSelect(item.aid)}
    >
      <div className="card-top">
        <span className="chip" style={{ background: color + '22', color }}>{item.param}</span>
        {isFact && <span className={`verdict ${v.cls}`}>{v.label}</span>}
        {decision === 'applied' && <span className="state-tag ok">✓ {isFact ? 'Corrected' : 'Applied'}</span>}
        {decision === 'dismissed' && <span className="state-tag muted">Dismissed</span>}
        {!item.matched && <span className="state-tag warn" title="Quote could not be located in the script">⚠ not in text</span>}
      </div>

      {item.line && <p className="quote">“{item.line}”</p>}
      {item.issue && <p><strong>{isFact ? 'Claim:' : 'Issue:'}</strong> {item.issue}</p>}
      {item.fix && <p className="fix"><strong>{isFact ? 'Correct:' : 'Fix:'}</strong> {item.fix}</p>}
      {item.why && <p className="why">{item.why}</p>}

      {isFact && item.sources && item.sources.length > 0 && (
        <p className="sources">
          Sources:{' '}
          {item.sources.map((s, i) => (
            <a key={i} href={s} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              {hostOf(s)}
            </a>
          ))}
        </p>
      )}

      <div className="card-actions">
        {decision ? (
          <button className="btn ghost" onClick={(e) => { e.stopPropagation(); onDecision(item.aid, null) }}>↶ Undo</button>
        ) : (
          <>
            {canApply && (
              <button className="btn primary" onClick={(e) => { e.stopPropagation(); onDecision(item.aid, 'applied') }}>{applyLabel}</button>
            )}
            {item.fix && (
              <button className="btn" onClick={doCopy}>{copied ? '✓ Copied' : (isFact ? 'Copy correction' : 'Copy fix')}</button>
            )}
            <button className="btn ghost" onClick={(e) => { e.stopPropagation(); onDecision(item.aid, 'dismissed') }}>Dismiss</button>
          </>
        )}
      </div>
    </div>
  )
}

export default function SuggestionList({ items, paramColors, decisions, activeAid, onSelect, onDecision }) {
  if (!items.length) {
    return <div className="empty">No items for this filter. 🎉</div>
  }
  return (
    <div className="suglist">
      {items.map((item) => (
        <SuggestionCard
          key={item.aid}
          item={item}
          color={paramColors[item.param] || '#888'}
          decision={decisions[item.aid] || null}
          isActive={item.aid === activeAid}
          onSelect={onSelect}
          onDecision={onDecision}
        />
      ))}
    </div>
  )
}
