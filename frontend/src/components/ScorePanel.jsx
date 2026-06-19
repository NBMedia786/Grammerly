import React from 'react'

function Bullets({ title, items }) {
  const list = (items || []).filter((x) => typeof x === 'string' && x.trim())
  if (!list.length) return null
  return (
    <div className="block">
      <h4>{title}</h4>
      <ul>{list.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </div>
  )
}

export default function ScorePanel({ result }) {
  const { scores = {}, param_order = [], param_colors = {}, overall_rating } = result
  const ordered = param_order.filter((p) => p in scores)

  return (
    <div className="scorepanel">
      <div className="overall">
        <div className="overall-num">{overall_rating !== '' ? overall_rating : '—'}<span>/10</span></div>
        <div className="overall-label">Overall</div>
      </div>

      <div className="block">
        <h4>Scores</h4>
        {ordered.map((p) => {
          const v = Number(scores[p]) || 0
          const c = param_colors[p] || '#888'
          return (
            <div className="scorerow" key={p}>
              <div className="scorerow-top">
                <span>{p}</span><strong>{scores[p]}</strong>
              </div>
              <div className="bar"><div className="bar-fill" style={{ width: `${v * 10}%`, background: c }} /></div>
            </div>
          )
        })}
      </div>

      <Bullets title="Strengths" items={result.strengths} />
      <Bullets title="Weaknesses" items={result.weaknesses} />
      <Bullets title="Suggestions" items={result.suggestions} />

      {result.summary && (
        <div className="block">
          <h4>Summary</h4>
          <p>{result.summary}</p>
        </div>
      )}
    </div>
  )
}
