import React from 'react'

function Bullets({ title, items }) {
  const list = (items || []).filter((x) => typeof x === 'string' && x.trim())
  if (!list.length) return null
  return (
    <>
      <h5>{title}</h5>
      <ul>{list.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </>
  )
}

// Renders the contents of the "Report" disclosure in the suggestion margin:
// per-category score bars + strengths / weaknesses / suggestions / summary.
export default function ScorePanel({ result }) {
  const { scores = {}, param_order = [], param_colors = {} } = result
  const ordered = param_order.filter((p) => p in scores)

  return (
    <div className="scorepanel">
      <h5>Scores</h5>
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

      <Bullets title="Strengths" items={result.strengths} />
      <Bullets title="Weaknesses" items={result.weaknesses} />
      <Bullets title="Suggestions" items={result.suggestions} />

      {result.summary && (
        <>
          <h5>Summary</h5>
          <p>{result.summary}</p>
        </>
      )}
    </div>
  )
}
