import { useState, useEffect } from 'react'
import { API_URL } from '../../config'
import { CardSkeleton } from '../ui/Skeleton'

/**
 * HabitsPanel — displays tracked habits with streaks.
 */
export default function HabitsPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_URL}/habits`).then(r => r.json()).then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="panel panel--fade-in">
      <h2 className="panel__title">✅ Habits</h2>
      <CardSkeleton /><CardSkeleton />
    </div>
  )

  const habits = data?.habits || []

  return (
    <div className="panel panel--fade-in" id="habits-panel">
      <h2 className="panel__title">✅ Habits</h2>
      {habits.length === 0 ? (
        <div className="panel__empty-state">
          <div className="panel__empty-icon">✅</div>
          <p className="panel__empty">No habits tracked yet</p>
          <p className="panel__empty-hint">Say &quot;add habit exercise&quot; to start tracking</p>
        </div>
      ) : (
        <div className="panel__list">
          {habits.map(h => (
            <div key={h.id} className={`panel-card habit-card ${h.done_today ? 'habit-card--done' : ''}`}>
              <div className="habit-card__top">
                <div className="habit-card__check">
                  {h.done_today ? '✅' : '⬜'}
                </div>
                <div className="habit-card__name">{h.name}</div>
              </div>
              <div className="habit-card__stats">
                <div className="habit-stat">
                  <span className="habit-stat__val">🔥 {h.streak}</span>
                  <span className="habit-stat__label">streak</span>
                </div>
                <div className="habit-stat">
                  <span className="habit-stat__val">⭐ {h.best_streak}</span>
                  <span className="habit-stat__label">best</span>
                </div>
                <div className="habit-stat">
                  <span className="habit-stat__val">📊 {h.total}</span>
                  <span className="habit-stat__label">total</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
