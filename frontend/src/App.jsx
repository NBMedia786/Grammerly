import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  analyzeFile, analyzeText, getHistory, getHistoryItem, deleteHistoryItem, renameHistoryItem, getStorage,
} from './api.js'
import { buildEditedText, copyToClipboard } from './highlight.js'
import Sidebar from './components/Sidebar.jsx'
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
  const [decisions, setDecisions] = useState({})
  const [pasteText, setPasteText] = useState('')

  const [historyItems, setHistoryItems] = useState([])
  const [storage, setStorage] = useState(null)
  const [saveWarning, setSaveWarning] = useState(false)

  const fileInput = useRef(null)

  // ---- load history + storage for the sidebar ----
  async function refreshSidebar() {
    try {
      const [items, usage] = await Promise.all([getHistory(), getStorage()])
      setHistoryItems(items); setStorage(usage)
    } catch (_) { /* sidebar is non-critical */ }
  }
  useEffect(() => { refreshSidebar() }, [])

  // ---- derived ----
  const orderedItems = useMemo(() => {
    if (!result) return []
    const order = new Map(result.spans.map((sp) => [sp.aid, sp.start]))
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

  const countByParam = useMemo(() => {
    const m = {}
    for (const it of orderedItems) m[it.param] = (m[it.param] || 0) + 1
    return m
  }, [orderedItems])

  const factCount = countByParam['Fact Check'] || 0

  // ---- result + flow ----
  function onResult(data) {
    setResult(data); setDecisions({}); setSelectedParam(null); setActiveAid(null)
    if (data && data.title) setFileName(data.title)
    setSaveWarning(data && data.saved === false)
    setView('review')
    refreshSidebar()
  }

  async function onPick(file) {
    if (!file) return
    setFileName(file.name); setView('loading'); setError('')
    try { onResult(await analyzeFile(file)) }
    catch (e) { setError(e.message || 'Something went wrong.'); setView('error') }
  }

  async function onAnalyzeText() {
    if (pasteText.trim().length < 50) return
    setFileName('Pasted text'); setView('loading'); setError('')
    try { onResult(await analyzeText(pasteText)) }
    catch (e) { setError(e.message || 'Something went wrong.'); setView('error') }
  }

  function setDecision(aid, decision) {
    setDecisions((d) => {
      const next = { ...d }
      if (decision === null) delete next[aid]; else next[aid] = decision
      return next
    })
    setActiveAid(aid)
  }

  function reset() {
    setResult(null); setView('upload'); setError(''); setFileName('')
    setDecisions({}); setSelectedParam(null); setActiveAid(null)
    setSaveWarning(false); setPasteText('')
  }

  async function openHistoryItem(id) {
    setView('loading'); setError('')
    try { onResult(await getHistoryItem(id)) }
    catch (e) { setError(e.message || 'Could not open that review.'); setView('error') }
  }

  async function removeHistoryItem(id) {
    if (!window.confirm('Permanently delete this saved review? This cannot be undone.')) return
    try {
      const usage = await deleteHistoryItem(id)
      setStorage(usage)
      setHistoryItems(await getHistory())
      if (result && result.id === id) reset()
    } catch (_) { /* ignore */ }
  }

  async function renameItem(id, title) {
    try {
      await renameHistoryItem(id, title)
      setHistoryItems(await getHistory())
      if (result && result.id === id) setFileName(title)
    } catch (_) { /* ignore */ }
  }

  async function copyEdited() {
    await copyToClipboard(buildEditedText(result.script_text, result.spans, decisions, result.aoi))
  }
  function downloadEdited() {
    const txt = buildEditedText(result.script_text, result.spans, decisions, result.aoi)
    const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (fileName.replace(/\.[^.]+$/, '') || 'script') + '.edited.txt'
    a.click(); URL.revokeObjectURL(url)
  }

  // ---------- Main content ----------
  function MainContent() {
    if (view === 'loading') {
      return (
        <div className="center-card">
          <div className="loadcard">
            <div className="spinner" />
            <p>Reviewing <strong>{fileName}</strong> for tense, hooks, grammar, spelling, punctuation &amp; facts…</p>
            <p className="muted">This runs several AI passes, so it can take a moment.</p>
          </div>
        </div>
      )
    }
    if (view === 'error') {
      return (
        <div className="center-card">
          <div className="loadcard">
            <h3>That didn’t work</h3>
            <p className="errmsg">{error}</p>
            <button className="btn" onClick={reset}>Start over</button>
          </div>
        </div>
      )
    }
    if (view === 'review' && result) return <Review />
    return <Upload />
  }

  function Upload() {
    return (
      <div className="empty-wrap">
        <div className="empty-inner">
          <div className="empty-kicker">Script proofreading</div>
          <h1 className="empty-title">Review a script<span style={{ color: '#8b6dff' }}>.</span></h1>
          <p className="empty-sub">
            Marked up in the margin like a proofreader’s desk — every issue with a fix you
            can apply in one click.
          </p>
          <div className="checks">
            {[
              ['Tense', '#a78bfa'], ['Hooks', '#14b8a6'], ['Grammar', '#ff6b6b'],
              ['Spelling', '#6b8cff'], ['Punctuation', '#eab308'], ['Facts', '#22c55e'],
            ].map(([name, c]) => (
              <span className="check" key={name}>
                <span className="check-dot" style={{ background: c, boxShadow: `0 0 0 3px ${c}22` }} />
                {name}
              </span>
            ))}
          </div>

          <div
            className="dropzone"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); onPick(e.dataTransfer.files?.[0]) }}
          >
            <div className="dz-icon" aria-hidden>↑</div>
            <h2>Upload a script</h2>
            <p className="muted">Drag &amp; drop or click — .docx, .pdf, or .txt</p>
            <input
              ref={fileInput} type="file" accept=".docx,.pdf,.txt" hidden
              onChange={(e) => onPick(e.target.files?.[0])}
            />
          </div>

          <div className="paste-area">
            <div className="paste-or">or paste text</div>
            <textarea
              className="paste-input" value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder="Paste your script here (at least 50 characters)…"
            />
            <button
              className="btn primary" disabled={pasteText.trim().length < 50}
              onClick={onAnalyzeText}
            >Review text</button>
          </div>
        </div>
      </div>
    )
  }

  function Review() {
    const cats = (result.param_order || []).filter((p) => p in (result.scores || {}))
    const fc = result.fact_check
    return (
      <div className="review">
        <div className="rev-head">
          <div className="overall">
            <span className="num">{result.overall_rating !== '' ? result.overall_rating : '—'}</span>
            <span className="den">/10</span>
            <span className="lbl">overall</span>
          </div>
          <div className="rev-divider" />

          <div className="chips">
            <button
              className={`chip-filter chip-all ${selectedParam === null ? 'on' : ''}`}
              onClick={() => setSelectedParam(null)}
            >All <span className="cnt">{orderedItems.length}</span></button>

            {cats.map((p) => {
              const c = result.param_colors[p] || '#888'
              const n = countByParam[p] || 0
              return (
                <button
                  key={p}
                  className={`chip-filter ${selectedParam === p ? 'on' : ''}`}
                  style={selectedParam === p ? { color: c } : undefined}
                  onClick={() => setSelectedParam(p)}
                >
                  <span className="swatch" style={{ background: c }} />
                  {p} <span className="cnt">{n}</span>
                </button>
              )
            })}

            {factCount > 0 && (
              <button
                className={`chip-filter ${selectedParam === 'Fact Check' ? 'on' : ''}`}
                style={selectedParam === 'Fact Check' ? { color: '#c0392f' } : undefined}
                onClick={() => setSelectedParam('Fact Check')}
              >
                <span className="swatch" style={{ background: '#e5484d' }} />
                Fact Check <span className="cnt">{factCount}</span>
              </button>
            )}
          </div>

          <div className="rev-actions">
            <span className="rev-counts">
              {counts.open} open · <span className="ok">{counts.applied} applied</span>
            </span>
            <button className="btn" onClick={copyEdited}>Copy edited</button>
            <button className="btn" onClick={downloadEdited}>Download</button>
          </div>
        </div>

        {saveWarning && (
          <div className="save-warning">
            History is full (50 GB). Delete old reviews in the sidebar to save new ones.
          </div>
        )}

        <div className="rev-body">
          <div className="script-col">
            <ScriptView
              text={result.script_text}
              spans={visibleSpans}
              decisions={decisions}
              aoi={result.aoi}
              activeAid={activeAid}
              onSelect={setActiveAid}
            />
          </div>

          <aside className="margin-col">
            <details className="report">
              <summary>Report <span aria-hidden>▾</span></summary>
              <div className="report-body"><ScorePanel result={result} /></div>
            </details>

            {fc && factCount > 0 && (
              <div className={`fc-banner ${fc.web_grounded ? 'ok' : 'warn'}`}>
                {fc.web_grounded
                  ? '✓ Facts verified against Google Search'
                  : '⚠ Web grounding unavailable — checked with model knowledge only'}
                {fc.counts && (
                  <span className="fc-counts">
                    {' · '}{fc.counts.incorrect || 0} wrong, {fc.counts.unverifiable || 0} unverifiable
                  </span>
                )}
              </div>
            )}

            <div className="margin-title">
              {selectedParam ? selectedParam : 'All suggestions'} · {visibleItems.length}
            </div>
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

  return (
    <div className="shell">
      <Sidebar
        items={historyItems}
        usage={storage}
        activeId={result?.id || null}
        onNew={reset}
        onOpen={openHistoryItem}
        onDelete={removeHistoryItem}
        onRename={renameItem}
      />
      <main className="main">
        <MainContent />
      </main>
    </div>
  )
}
