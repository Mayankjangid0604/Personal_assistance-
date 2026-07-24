import { useState, useEffect } from 'react'
import { API_URL } from '../../config'
import { CardSkeleton } from '../ui/Skeleton'

/**
 * JournalPanel — displays journal entries with emotions.
 */
export default function JournalPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_URL}/journal`).then(r => r.json()).then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="panel panel--fade-in">
      <h2 className="panel__title">📓 Journal</h2>
      <CardSkeleton /><CardSkeleton />
    </div>
  )

  const entries = data?.entries || []

  const emotionEmoji = { happy: '😊', sad: '😢', stressed: '😰', angry: '😡', neutral: '😐' }

  return (
    <div className="panel panel--fade-in" id="journal-panel">
      <h2 className="panel__title">📓 Journal</h2>
      {entries.length === 0 ? (
        <div className="panel__empty-state">
          <div className="panel__empty-icon">📓</div>
          <p className="panel__empty">No journal entries yet</p>
          <p className="panel__empty-hint">Say &quot;save this as journal&quot; to create one</p>
        </div>
      ) : (
        <div className="panel__list">
          {entries.map((e, i) => (
            <div key={i} className="panel-card journal-card">
              <div className="journal-card__header">
                <span className="journal-card__date">{e.date || 'Unknown'}</span>
                <span className="journal-card__emotion">
                  {emotionEmoji[e.emotion] || '😐'} {e.emotion || 'neutral'}
                </span>
              </div>
              {e.summary && <div className="journal-card__summary">{e.summary}</div>}
              {e.notes && <div className="journal-card__notes">{e.notes}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
