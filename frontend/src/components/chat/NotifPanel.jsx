/**
 * Notification dropdown panel component.
 */
export default function NotifPanel({ notifications, onClose }) {
  return (
    <div className="notif-panel" id="notification-panel">
      <div className="notif-panel__header">
        <span>Notifications</span>
        <button className="notif-panel__close" onClick={onClose}>✕</button>
      </div>
      <div className="notif-panel__list">
        {notifications.length === 0 ? (
          <div className="notif-panel__empty">No notifications yet</div>
        ) : notifications.map(n => (
          <div key={n.id} className={`notif-item ${n.read ? '' : 'notif-item--unread'}`}>
            <div className="notif-item__icon">
              {n.category === 'reminder' ? '⏰' : n.category === 'emotion' ? '💜' :
               n.category === 'autonomous' ? '🤖' : '📌'}
            </div>
            <div className="notif-item__content">
              <div className="notif-item__text">{n.message}</div>
              <div className="notif-item__time">
                {n.time ? new Date(n.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}
                {n.source ? ` · ${n.source}` : ''}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
