import { memo } from 'react'
import { getHandlerMode } from '../../config'

/**
 * Contextual thinking state indicator — shows the current AI processing phase.
 */
function ThinkingIndicator({ phase = 'thinking', handler = 'general' }) {
  const mode = getHandlerMode(handler)
  const labels = {
    thinking:  mode.thinkText,
    analyzing: 'Analyzing your request...',
    streaming: 'Composing response...',
  }

  return (
    <div className="thinking">
      <div className="thinking__avatar">A</div>
      <div className="thinking__bubble">
        <div className="thinking__brain">
          <span className="thinking__brain-icon">{mode.icon}</span>
          <div className="thinking__brain-waves">
            <span className="thinking__wave" />
            <span className="thinking__wave" />
            <span className="thinking__wave" />
            <span className="thinking__wave" />
          </div>
        </div>
        <span className="thinking__label">{labels[phase] || labels.thinking}</span>
      </div>
    </div>
  )
}

export default memo(ThinkingIndicator)
