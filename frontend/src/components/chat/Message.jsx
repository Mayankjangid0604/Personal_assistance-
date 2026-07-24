import { useState, useEffect, memo } from 'react'
import { formatTime, getHandlerMode } from '../../config'
import MarkdownMessage from './MarkdownMessage'

/* ================================================================
   Streaming Text Hook — humanized word-by-word reveal
   ================================================================ */

const PUNCT_DELAYS = { '.': 120, '!': 120, '?': 150, ',': 60, ';': 80, ':': 60, '—': 80 }
const BASE_SPEED = 32 // ms per word
const JITTER = 15     // ±ms random variation
const INITIAL_DELAY = 400 // ms pause before first word

/**
 * Hook that reveals fullText word-by-word with humanized timing.
 * Used as fallback when SSE streaming is not available.
 */
function useStreamingText(fullText, isStreaming) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!isStreaming || !fullText) {
      setDisplayed(fullText || '')
      setDone(true)
      return
    }

    // Split preserving spaces so we can reassemble perfectly
    const words = fullText.split(/( )/)
    let i = 0
    let timer = null
    setDisplayed('')
    setDone(false)

    function scheduleNext() {
      if (i >= words.length) {
        setDone(true)
        return
      }

      // Calculate delay: base + jitter + punctuation pause
      let delay = BASE_SPEED + (Math.random() * JITTER * 2 - JITTER)

      // Check if previous word ended with punctuation
      if (i > 0) {
        const prevWord = words[i - 1]
        const lastChar = prevWord[prevWord.length - 1]
        if (PUNCT_DELAYS[lastChar]) {
          delay += PUNCT_DELAYS[lastChar]
        }
      }

      timer = setTimeout(() => {
        i++
        const chunk = words.slice(0, i).join('')
        setDisplayed(chunk)

        // Throttled mini-window sync: every 4th word or final
        if (typeof window !== 'undefined' && window.electronAPI?.sendToMini) {
          if (i % 4 === 0 || i >= words.length) {
            window.electronAPI.sendToMini(chunk)
          }
        }

        scheduleNext()
      }, delay)
    }

    // Initial pause before streaming begins
    timer = setTimeout(scheduleNext, INITIAL_DELAY)

    return () => { if (timer) clearTimeout(timer) }
  }, [fullText, isStreaming])

  return { displayed, done }
}

/* ================================================================
   Message Component
   ================================================================ */

function Message({ message, onStreamingDone }) {
  const isUser = message.role === 'user'
  const { displayed, done } = useStreamingText(
    message.text,
    message.streaming === true
  )

  // Notify parent when streaming finishes
  useEffect(() => {
    if (message.streaming && done && onStreamingDone) {
      onStreamingDone(message.id)
    }
  }, [done, message.streaming, message.id, onStreamingDone])

  const mode = !isUser && message.handler ? getHandlerMode(message.handler) : null

  return (
    <div className={`message message--${message.role}`}>
      <div className="message__avatar">{isUser ? 'U' : 'A'}</div>
      <div className="message__content">
        <div className={`message__bubble ${message.streaming && !done ? 'message__bubble--streaming' : ''}`}>
          {isUser ? message.text : (
            <MarkdownMessage content={displayed} />
          )}
          {message.streaming && !done && <span className="message__cursor" />}
        </div>
        <div className="message__meta">
          <span className="message__time">{formatTime(message.time)}</span>
          {mode && (
            <span className={`message__handler message__handler--${message.handler}`}>
              {mode.icon} {mode.label}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export default memo(Message)
