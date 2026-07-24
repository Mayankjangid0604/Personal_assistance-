import { useRef, Suspense, lazy } from 'react'
import WelcomeScreen from '../chat/WelcomeScreen'
import Message from '../chat/Message'
import ThinkingIndicator from '../chat/ThinkingIndicator'

// Lazy-load the 3D orb to avoid blocking initial paint
const AIOrb = lazy(() => import('../AIOrb'))

/**
 * ChatPanel — the main conversation view with messages, orb, and welcome screen.
 */
export default function ChatPanel({
  messages, isTyping, chatRef, onChipClick, speaking,
  orbState, thinkingPhase, activeHandler, onStreamingDone,
}) {
  return (
    <div className="chat" ref={chatRef} id="chat-area">
      {messages.length === 0 ? (
        <WelcomeScreen onChipClick={onChipClick} speaking={speaking} orbState={orbState} />
      ) : (
        <>
          {messages.map(msg => (
            <Message key={msg.id} message={msg} onStreamingDone={onStreamingDone} />
          ))}
          {isTyping && <ThinkingIndicator phase={thinkingPhase} handler={activeHandler} />}
        </>
      )}
    </div>
  )
}
