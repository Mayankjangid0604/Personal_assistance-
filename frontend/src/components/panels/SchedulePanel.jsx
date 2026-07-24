import { useState, useEffect } from 'react'
import { API_URL } from '../../config'
import { CardSkeleton } from '../ui/Skeleton'

/**
 * SchedulePanel — displays pending reminders.
 */
export default function SchedulePanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_URL}/reminders`).then(r => r.json()).then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="panel panel--fade-in">
      <h2 className="panel__title">📅 Schedule</h2>
      <CardSkeleton /><CardSkeleton /><CardSkeleton />
    </div>
  )

  const reminders = data?.reminders || []

  return (
    <div className="panel panel--fade-in" id="schedule-panel">
      <h2 className="panel__title">📅 Schedule</h2>
      {reminders.length === 0 ? (
        <div className="panel__empty-state">
          <div className="panel__empty-icon">📅</div>
          <p className="panel__empty">No pending reminders</p>
          <p className="panel__empty-hint">Say &quot;remind me to study at 5pm&quot; to create one</p>
        </div>
      ) : (
        <div className="panel__list">
          {reminders.map((r, i) => {
            const t = new Date(r.time)
            const timeStr = t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            const dateStr = t.toLocaleDateString([], { day: 'numeric', month: 'short' })
            return (
              <div key={r.id || i} className="panel-card panel-card--row">
                <div className="panel-card__time-block">
                  <div className="panel-card__time-big">{timeStr}</div>
                  <div className="panel-card__time-date">{dateStr}</div>
                </div>
                <div className="panel-card__divider" />
                <div className="panel-card__task">{r.task}</div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
