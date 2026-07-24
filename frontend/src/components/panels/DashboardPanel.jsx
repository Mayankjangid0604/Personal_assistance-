import { useState, useEffect } from 'react'
import { API_URL } from '../../config'
import { Skeleton, CardSkeleton } from '../ui/Skeleton'

/**
 * DashboardPanel — user profile, stats grid, and emotion trend.
 */
export default function DashboardPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_URL}/dashboard`).then(r => r.json()).then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="panel panel--fade-in">
      <h2 className="panel__title">📊 Dashboard</h2>
      <div className="panel__grid">
        <CardSkeleton /><CardSkeleton /><CardSkeleton /><CardSkeleton />
      </div>
    </div>
  )

  if (!data) return <div className="panel"><p className="panel__empty">Could not load dashboard data.</p></div>

  const emotionEmoji = { happy: '😊', sad: '😢', stressed: '😰', angry: '😡', neutral: '😐' }
  const trend = data.emotion_trend || {}

  return (
    <div className="panel panel--fade-in" id="dashboard-panel">
      <h2 className="panel__title">📊 Dashboard</h2>

      {/* Profile Card */}
      <div className="panel-card panel-card--accent">
        <div className="panel-card__row">
          <div className="panel-card__avatar">
            {(data.user_name || 'U')[0].toUpperCase()}
          </div>
          <div>
            <div className="panel-card__name">{data.user_name || 'User'}</div>
            <div className="panel-card__sub">Goal: {data.goal || 'Not set'}</div>
          </div>
        </div>
        <div className="panel-card__emotion">
          {emotionEmoji[data.emotion] || '😐'} Currently {data.emotion}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="panel__grid">
        <StatCard label="Conversations" value={data.stats?.conversations || 0} icon="💬" />
        <StatCard label="Reminders" value={data.stats?.reminders || 0} icon="📅" />
        <StatCard label="Habits" value={data.stats?.habits || 0} icon="✅" />
        <StatCard label="Interests" value={data.stats?.interests || 0} icon="📚" />
      </div>

      {/* Emotion Trend */}
      {trend.recent && trend.recent.length > 0 && (
        <div className="panel-card">
          <div className="panel-card__label">Emotion Trend</div>
          <div className="trend-bar">
            {trend.recent.slice(-10).map((e, i) => (
              <span key={i} className={`trend-dot trend-dot--${e}`}
                title={e}>{emotionEmoji[e] || '😐'}</span>
            ))}
          </div>
          {trend.direction && (
            <div className="panel-card__sub">
              Trend: <span className={`trend-label trend-label--${trend.direction}`}>
                {trend.direction === 'improving' ? '📈 Improving' :
                 trend.direction === 'declining' ? '📉 Declining' : '➡️ Stable'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, icon }) {
  return (
    <div className="stat-card">
      <div className="stat-card__icon">{icon}</div>
      <div className="stat-card__value">{value}</div>
      <div className="stat-card__label">{label}</div>
    </div>
  )
}
