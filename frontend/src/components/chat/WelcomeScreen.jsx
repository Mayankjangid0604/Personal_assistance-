import { Suspense, lazy } from 'react'

// Lazy-load the 3D orb to avoid blocking initial paint
const AIOrb = lazy(() => import('../AIOrb'))

/**
 * Welcome screen shown when chat is empty — orb + suggestion chips.
 */
export default function WelcomeScreen({ onChipClick, speaking = false, orbState = 'idle' }) {
  const suggestions = [
    { text: "Hey Aisha, how are you?", icon: "👋" },
    { text: "I want to learn Python",  icon: "🐍" },
    { text: "I'm feeling stressed",    icon: "💜" },
    { text: "Add habit drink water",   icon: "✅" },
    { text: "Summarize my day",        icon: "📊" },
    { text: "Create plan for AI",      icon: "🗺️" },
  ]
  return (
    <div className="welcome">
      <div className="welcome__glow" />
      <div className="welcome__orb">
        <Suspense fallback={<div className="welcome__icon">A</div>}>
          <AIOrb speaking={speaking} orbState={orbState} style={{ width: '160px', height: '160px' }} />
        </Suspense>
      </div>
      <h1 className="welcome__title">Hello, I&apos;m Aisha</h1>
      <p className="welcome__subtitle">
        Your AI companion for learning, productivity, and emotional support.
      </p>
      <div className="welcome__chips">
        {suggestions.map((s, i) => (
          <button key={i} className="welcome__chip" onClick={() => onChipClick(s.text)}
            style={{ animationDelay: `${i * 0.08}s` }}>
            <span className="welcome__chip-icon">{s.icon}</span>{s.text}
          </button>
        ))}
      </div>
    </div>
  )
}
