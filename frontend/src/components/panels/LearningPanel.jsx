import { useState, useEffect } from 'react'
import { API_URL } from '../../config'
import { CardSkeleton } from '../ui/Skeleton'

/**
 * LearningPanel — interests and learning plan progress.
 */
export default function LearningPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_URL}/learning`).then(r => r.json()).then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="panel panel--fade-in">
      <h2 className="panel__title">📚 Learning</h2>
      <CardSkeleton /><CardSkeleton />
    </div>
  )

  const interests = data?.interests || []
  const plans = data?.plans || []

  return (
    <div className="panel panel--fade-in" id="learning-panel">
      <h2 className="panel__title">📚 Learning</h2>

      {/* Interests */}
      {interests.length > 0 && (
        <div className="panel-card">
          <div className="panel-card__label">Your Interests</div>
          <div className="interest-tags">
            {interests.map((int, i) => (
              <span key={i} className="interest-tag">
                {int.topic} <span className="interest-tag__count">{int.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Plans */}
      {plans.length > 0 ? plans.map((p, i) => (
        <div key={i} className="panel-card">
          <div className="panel-card__label">{p.topic}</div>
          <div className="progress-bar">
            <div className="progress-bar__fill" style={{ width: `${p.percent}%` }} />
          </div>
          <div className="panel-card__sub">{p.done}/{p.total} steps ({p.percent}%)</div>
        </div>
      )) : (
        <div className="panel__empty-state">
          <div className="panel__empty-icon">📚</div>
          <p className="panel__empty">No learning plans yet</p>
          <p className="panel__empty-hint">Say &quot;create plan for Python&quot; to start</p>
        </div>
      )}
    </div>
  )
}
