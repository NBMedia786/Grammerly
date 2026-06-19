import React, { useMemo, useRef, useState } from 'react'
import { analyzeFile } from './api.js'
import { buildEditedText, copyToClipboard } from './highlight.js'
import ScriptView from './components/ScriptView.jsx'
import SuggestionList from './components/SuggestionList.jsx'
import ScorePanel from './components/ScorePanel.jsx'

export default function App() {
  const [view, setView] = useState('upload') // upload | loading | review | error
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [fileName, setFileName] = useState('')

  const [selectedParam, setSelectedParam] = useState(null) // null = all
  const [activeAid, setActiveAid] = useState(null)
  const [decisions, setDecisions] = useState({}) // aid -> 'applied' | 'dismissed'
  const fileInput = useRef(null)

  // Ordered suggestion items (by position in the script).
  const orderedItems = useMemo(() => {
    if (!result) return []
    const order = new Map(result.spans.map((sp, i) => [sp.aid, sp.start]))
    return Object.entries(result.aoi)
      .map(([aid, v]) => ({ aid, ...v, start: order.has(aid) ? order.get(aid) : Number.MAX_SAFE_INTEGER }))
      .sort((a, b) => a.start - b.start)
  }, [result])

  const visibleItems = useMemo(
    () => (selectedParam ? orderedItems.filter((it) => it.param === selectedParam) : orderedItems),
    [orderedItems, selectedParam],
  )

  const visibleSpans = useMemo(() => {
    if (!result) return []
    return selectedParam ? result.spans.filter((sp) => sp.param === selectedParam) : result.spans
  }, [result, selectedParam])

  const counts = useMemo(() => {
    const total = orderedItems.length
    const applied = orderedItems.filter((it) => decisions[it.aid] === 'applied').length
    const dismissed = orderedItems.filter((it) => decisions[it.aid] === 'dismissed').length
    return { total, applied, dismissed, open: total - applied - dismissed }
  }, [orderedItems, decisions])

  const factCount = useMemo(
    () => orderedItems.filter((it) => it.param === 'Fact Check').length,
    [orderedItems],
  )

  async function onPick(file) {
    if (!file) return
    setFileName(file.name)
    setView('loading')
    setError('')
    try {
      const data = await analyzeFile(file)
      setResult(data)
      setDecisions({})
      setSelectedParam(null)
      setActiveAid(null)
      setView('review')
    } catch (e) {
      setError(e.message || 'Something went wrong.')
      setView('error')
    }
  }

  function setDecision(aid, decision) {
    setDecisions((d) => {
      const next = { ...d }
      if (decision === null) delete next[aid]
      else next[aid] = decision
      return next
    })
    setActiveAid(aid)
  }

  function reset() {
    setResult(null); setView('upload'); setError(''); setFileName('')
    setDecisions({}); setSelectedParam(null); setActiveAid(null)
  }

  async function copyEdited() {
    const txt = buildEditedText(result.script_text, result.spans, decisions, result.aoi)
    await copyToClipboard(txt)
  }

  function downloadEdited() {
    const txt = buildEditedText(result.script_text, result.spans, decisions, result.aoi)
    const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (fileName.replace(/\.[^.]+$/, '') || 'script') + '.edited.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  // ---------- Upload / loading / error screens ----------
  if (view !== 'review') {
    return (
      <div className="app">
        <header className="topbar">
          <div className="brand">📝 Viral Script Reviewer</div>
        </header>
        <div className="center-screen">
          {view === 'loading' && (
            <div className="loadcard">
              <div className="spinner" />
              <p>Analyzing <strong>{fileName}</strong> across 7 storytelling parameters…</p>
              <p className="muted">This runs 8 AI passes, so it can take a bit.</p>
            </div>
          )}
          {view === 'error' && (
            <div className="loadcard">
              <h3>Couldn’t analyze that file</h3>
              <p className="errmsg">{error}</p>
              <button className="btn primary" onClick={reset}>Try again</button>
            </div>
          )}
          {view === 'upload' && (
            <div
              className="dropzone"
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); onPick(e.dataTransfer.files?.[0]) }}
            >
              <div className="dz-icon">⬆️</div>
              <h2>Upload a script</h2>
              <p className="muted">Drag &amp; drop or click — .docx, .pdf, or .txt</p>
              <input
                ref={fileInput}
                type="file"
                accept=".docx,.pdf,.txt"
                hidden
                onChange={(e) => onPick(e.target.files?.[0])}
              />
            </div>
          )}
        </div>
      </div>
    )
  }

  // ---------- Review screen ----------
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">📝 Viral Script Reviewer</div>
        <div className="topbar-right">
          <span className="counts">
            {counts.open} open · <span className="ok">{counts.applied} applied</span> · {counts.dismissed} dismissed
          </span>
          <button className="btn" onClick={copyEdited}>Copy edited script</button>
          <button className="btn" onClick={downloadEdited}>Download</button>
          <button className="btn ghost" onClick={reset}>New review</button>
        </div>
      </header>

      <div className="layout">
        <aside className="col-left">
          <ScorePanel result={result} />
        </aside>

        <main className="col-center">
          <ScriptView
            text={result.script_text}
            spans={visibleSpans}
            decisions={decisions}
            aoi={result.aoi}
            activeAid={activeAid}
            onSelect={setActiveAid}
          />
        </main>

        <aside className="col-right">
          <div className="filters">
            <button
              className={`pill ${selectedParam === null ? 'on' : ''}`}
              onClick={() => setSelectedParam(null)}
            >All ({orderedItems.length})</button>
            {result.param_order.filter((p) => p in (result.scores || {})).map((p) => {
              const n = orderedItems.filter((it) => it.param === p).length
              const c = result.param_colors[p] || '#888'
              return (
                <button
                  key={p}
                  className={`pill ${selectedParam === p ? 'on' : ''}`}
                  style={selectedParam === p ? { background: c + '22', borderColor: c, color: c } : undefined}
                  onClick={() => setSelectedParam(p)}
                >{p} ({n})</button>
              )
            })}
            {factCount > 0 && (
              <button
                className={`pill ${selectedParam === 'Fact Check' ? 'on' : ''}`}
                style={selectedParam === 'Fact Check' ? { background: '#ef444422', borderColor: '#ef4444', color: '#ef4444' } : undefined}
                onClick={() => setSelectedParam('Fact Check')}
              >🔎 Fact Check ({factCount})</button>
            )}
          </div>
          {result.fact_check && factCount > 0 && (
            <div className={`fc-banner ${result.fact_check.web_grounded ? 'ok' : 'warn'}`}>
              {result.fact_check.web_grounded
                ? '✓ Facts verified against Google Search'
                : '⚠ Web grounding unavailable — checked with model knowledge only'}
              {result.fact_check.counts && (
                <span className="fc-counts">
                  {' · '}{result.fact_check.counts.incorrect || 0} wrong,{' '}
                  {result.fact_check.counts.unverifiable || 0} unverifiable
                </span>
              )}
            </div>
          )}
          <SuggestionList
            items={visibleItems}
            paramColors={result.param_colors}
            decisions={decisions}
            activeAid={activeAid}
            onSelect={setActiveAid}
            onDecision={setDecision}
          />
        </aside>
      </div>
    </div>
  )
}
