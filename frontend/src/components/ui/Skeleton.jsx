/**
 * Reusable loading skeleton components.
 */

export function Skeleton({ width = '100%', height = '20px', rounded = false }) {
  return <div className="skeleton" style={{
    width, height, borderRadius: rounded ? '50%' : '8px'
  }} />
}

export function CardSkeleton() {
  return (
    <div className="panel-card">
      <Skeleton width="40%" height="16px" />
      <Skeleton width="100%" height="12px" />
      <Skeleton width="70%" height="12px" />
    </div>
  )
}
