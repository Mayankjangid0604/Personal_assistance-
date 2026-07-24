import { useState, useRef, useEffect, useCallback, Suspense, lazy } from 'react'
import './App.css'

// Config
import { API_URL, NAV_ITEMS, getHandlerMode } from './config'

// Hooks
import useWebSocket from './hooks/useWebSocket'

// Panels
import ChatPanel from './components/panels/ChatPanel'
import DashboardPanel from './components/panels/DashboardPanel'
import SchedulePanel from './components/panels/SchedulePanel'
import HabitsPanel from './components/panels/HabitsPanel'
import LearningPanel from './components/panels/LearningPanel'
import JournalPanel from './components/panels/JournalPanel'

// Chat components
import NotifPanel from './components/chat/NotifPanel'

// Lazy-load the 3D orb to avoid blocking initial paint
const AIOrb = lazy(() => import('./components/AIOrb'))

/* ================================================================
   App Component — Slim Shell
   ================================================================ */

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeTab, setActiveTab] = useState('chat')
  const chatRef = useRef(null)
  const inputRef = useRef(null)

  // AI intelligence state
  const [activeHandler, setActiveHandler] = useState('general')
  const [thinkingPhase, setThinkingPhase] = useState(null) // null | 'thinking' | 'analyzing' | 'streaming'
  const [isSpeaking, setIsSpeaking] = useState(false) // mic overlay feedback

  // Notification state
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [showNotifPanel, setShowNotifPanel] = useState(false)

  // WebSocket connection (Step 2 — real-time state sync)
  const {
    connected: wsConnected,
    orbState: wsOrbState,
    sessionId,
  } = useWebSocket(API_URL, {
    onOrbState: (msg) => {
      // Update handler from WS orb state when available
      if (msg.handler) setActiveHandler(msg.handler)
    },
    onNotification: () => {
      // Refresh notifications when a new one arrives via WS
      fetchNotifications()
    },
  })

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight
    }
  }, [messages, isTyping, thinkingPhase])

  // Focus input on mount and when switching to chat
  useEffect(() => {
    if (activeTab === 'chat') inputRef.current?.focus()
  }, [activeTab])

  // Listen for mic overlay voice state via Electron IPC
  useEffect(() => {
    if (typeof window === 'undefined' || !window.electronAPI) return

    const cleanupVoice = window.electronAPI.onVoiceState?.((isListening) => {
      setIsSpeaking(isListening)
    })

    const cleanupTranscript = window.electronAPI.onVoiceTranscript?.((text, isFinal) => {
      if (isFinal && text.trim()) {
        handleSend(text.trim())
      }
    })

    return () => {
      cleanupVoice?.()
      cleanupTranscript?.()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch notifications periodically
  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/notifications`)
      if (res.ok) {
        const data = await res.json()
        setNotifications(data.notifications || [])
        setUnreadCount(data.unread_count || 0)

        // Trigger native desktop notification for new unread items
        if (data.unread_count > 0 && window.electronAPI?.showNotification) {
          const latest = (data.notifications || [])[0]
          if (latest && !latest.read) {
            window.electronAPI.showNotification(
              'Aisha',
              latest.message || 'New notification'
            )
          }
        }
      }
    } catch {
      // Backend not running
    }
  }, [])

  useEffect(() => {
    fetchNotifications()
    // Poll less frequently when WebSocket is connected (WS handles push)
    const interval = setInterval(fetchNotifications, wsConnected ? 30000 : 8000)
    return () => clearInterval(interval)
  }, [fetchNotifications, wsConnected])

  const handleBellClick = async () => {
    const opening = !showNotifPanel
    setShowNotifPanel(opening)
    if (opening && unreadCount > 0) {
      try {
        await fetch(`${API_URL}/notifications/read`, { method: 'POST' })
        setUnreadCount(0)
        setNotifications(prev => prev.map(n => ({ ...n, read: true })))
      } catch { /* ignore */ }
    }
  }

  /* ================================================================
     Send message — tries SSE streaming first, falls back to fetch
     ================================================================ */

  const handleSend = async (text) => {
    const messageText = text || input.trim()
    if (!messageText || isTyping) return

    // Switch to chat tab when sending
    setActiveTab('chat')

    const userMsg = {
      id: Date.now(),
      role: 'user',
      text: messageText,
      time: new Date(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsTyping(true)
    setThinkingPhase('thinking')

    // Notify mini window
    window.electronAPI?.sendTypingToMini?.(true)

    try {
      // --- Try SSE streaming first ---
      const streamed = await _tryStreamingChat(messageText)
      if (streamed) return // success — SSE handled everything

      // --- Fallback: classic fetch ---
      setThinkingPhase('thinking')

      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      // Phase 2: Analyzing (brief pause to show we got the response)
      setThinkingPhase('analyzing')
      const data = await res.json()

      const handler = data.handler || 'general'
      setActiveHandler(handler)

      // Phase 3: Streaming — add message with streaming flag
      setThinkingPhase('streaming')
      setIsTyping(false)

      const aishaMsg = {
        id: Date.now() + 1,
        role: 'aisha',
        text: data.response || 'Sorry, I could not generate a response.',
        time: new Date(),
        handler,
        emotion: data.emotion || 'neutral',
        streaming: true, // triggers word-by-word reveal
      }
      setMessages(prev => [...prev, aishaMsg])

      // Send handler info to mini window
      window.electronAPI?.sendToMini?.(`[${getHandlerMode(handler).label}] ${data.response?.slice(0, 80) || ''}`)

      setTimeout(fetchNotifications, 500)
    } catch {
      setThinkingPhase(null)
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'aisha',
        text: 'Connection error — make sure the backend is running (python backend/server.py)',
        time: new Date(),
      }])
    } finally {
      setIsTyping(false)
      window.electronAPI?.sendTypingToMini?.(false)
    }
  }

  /**
   * Attempt to use SSE streaming endpoint.
   * Returns true if streaming succeeded, false to fall back.
   */
  const _tryStreamingChat = async (messageText) => {
    try {
      const res = await fetch(`${API_URL}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })

      if (!res.ok || !res.body) return false

      // Read SSE stream
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullText = ''
      let handler = 'general'
      let emotion = 'neutral'
      let gotMeta = false

      // Create the message placeholder
      const msgId = Date.now() + 1
      setThinkingPhase('streaming')
      setIsTyping(false)

      setMessages(prev => [...prev, {
        id: msgId,
        role: 'aisha',
        text: '',
        time: new Date(),
        handler: 'general',
        emotion: 'neutral',
        streaming: false, // we update text directly, no word-by-word sim needed
      }])

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // keep incomplete line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6)

            if (payload === '[DONE]') continue

            try {
              const event = JSON.parse(payload)

              if (event.type === 'meta') {
                handler = event.handler || 'general'
                emotion = event.emotion || 'neutral'
                gotMeta = true
                setActiveHandler(handler)
              } else if (event.type === 'chunk') {
                fullText += event.text
                setMessages(prev => prev.map(m =>
                  m.id === msgId ? { ...m, text: fullText, handler, emotion } : m
                ))
                // Throttled mini window sync
                if (fullText.length % 20 < 5) {
                  window.electronAPI?.sendToMini?.(fullText.slice(-80))
                }
              } else if (event.type === 'error') {
                fullText += event.text || 'An error occurred.'
                setMessages(prev => prev.map(m =>
                  m.id === msgId ? { ...m, text: fullText, handler, emotion } : m
                ))
              }
            } catch {
              // Malformed JSON line — skip
            }
          }
        }
      }

      // Final sync
      if (fullText) {
        window.electronAPI?.sendToMini?.(`[${getHandlerMode(handler).label}] ${fullText.slice(0, 80)}`)
      }

      setThinkingPhase(null)
      setTimeout(fetchNotifications, 500)
      return true
    } catch {
      // SSE not available — fall back
      return false
    }
  }

  // Called when word-by-word streaming animation finishes (fallback mode)
  const handleStreamingDone = useCallback((msgId) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId ? { ...m, streaming: false } : m
    ))
    setThinkingPhase(null)
  }, [])

  const handleSubmit = (e) => { e.preventDefault(); handleSend() }
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="app-layout">
      {/* ---- Sidebar ---- */}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : 'sidebar--collapsed'}`}>
        <div className="sidebar__header">
          <div className="sidebar__logo">
            <div className="sidebar__logo-icon">A</div>
            {sidebarOpen && <span className="sidebar__logo-text">Aisha</span>}
          </div>
          <button className="sidebar__toggle" onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? 'Collapse' : 'Expand'} id="sidebar-toggle">
            {sidebarOpen ? '◂' : '▸'}
          </button>
        </div>

        <nav className="sidebar__nav" id="sidebar-nav">
          {NAV_ITEMS.map(item => (
            <button key={item.id}
              className={`sidebar__item ${activeTab === item.id ? 'sidebar__item--active' : ''}`}
              onClick={() => setActiveTab(item.id)}
              title={item.label} id={`nav-${item.id}`}>
              <span className="sidebar__item-icon">{item.icon}</span>
              {sidebarOpen && <span className="sidebar__item-label">{item.label}</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <button className="sidebar__item sidebar__item--settings"
            onClick={() => handleSend('export my data')}
            title="Export Data" id="nav-export">
            <span className="sidebar__item-icon">📦</span>
            {sidebarOpen && <span className="sidebar__item-label">Export Data</span>}
          </button>
        </div>
      </aside>

      {/* ---- Main Panel ---- */}
      <div className="main-panel">
        {/* ---- Top Bar ---- */}
        <header className="topbar" id="topbar">
          <div className="topbar__left">
            <button className="topbar__mobile-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
            <div className="topbar__status">
              <span className={`topbar__dot ${isTyping || thinkingPhase ? 'topbar__dot--thinking' : ''}`} />
              <span className="topbar__status-text">
                {thinkingPhase === 'thinking' ? 'Thinking...' :
                 thinkingPhase === 'analyzing' ? 'Analyzing...' :
                 thinkingPhase === 'streaming' ? 'Responding...' :
                 isSpeaking ? 'Listening...' :
                 wsConnected ? 'Aisha Online' : 'Connecting...'}
              </span>
            </div>
          </div>
          <div className="topbar__right">
            {/* Active Mode Indicator */}
            {(() => {
              const mode = getHandlerMode(activeHandler)
              return (
                <div className="topbar__mode" id="active-mode-indicator">
                  <span className="topbar__mode-icon">{mode.icon}</span>
                  <span className="topbar__mode-label" style={{ color: mode.color }}>
                    {mode.label}
                  </span>
                </div>
              )
            })()}

            {/* Thinking phase badge */}
            {thinkingPhase && thinkingPhase !== 'streaming' && (
              <span className="topbar__thinking-badge">
                <span className="topbar__thinking-dot" />
                {getHandlerMode(activeHandler).thinkText}
              </span>
            )}

            <div className="notif-wrapper">
              <button className="notif-bell" onClick={handleBellClick}
                title="Notifications" id="notification-bell">
                🔔
                {unreadCount > 0 && (
                  <span className="notif-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
                )}
              </button>
              {showNotifPanel && (
                <NotifPanel
                  notifications={notifications}
                  onClose={() => setShowNotifPanel(false)}
                />
              )}
            </div>
          </div>
        </header>

        {/* ---- Dynamic Panel Content ---- */}
        <div className="panel-content">
          {activeTab === 'chat' && (
            <ChatPanel
              messages={messages} isTyping={isTyping}
              chatRef={chatRef} onChipClick={handleSend}
              speaking={isTyping || isSpeaking}
              orbState={wsOrbState !== 'idle' ? wsOrbState : (isSpeaking ? 'listening' : thinkingPhase === 'streaming' ? 'responding' : isTyping ? 'thinking' : 'idle')}
              thinkingPhase={thinkingPhase}
              activeHandler={activeHandler}
              onStreamingDone={handleStreamingDone}
            />
          )}
          {activeTab === 'dashboard' && <DashboardPanel />}
          {activeTab === 'schedule'  && <SchedulePanel />}
          {activeTab === 'habits'    && <HabitsPanel />}
          {activeTab === 'learning'  && <LearningPanel />}
          {activeTab === 'journal'   && <JournalPanel />}
        </div>

        {/* ---- Background 3D Orb (ambient depth) ---- */}
        <div className="bg-orb-wrapper" aria-hidden="true">
          <Suspense fallback={null}>
            <AIOrb
              speaking={isTyping || isSpeaking}
              orbState={wsOrbState !== 'idle' ? wsOrbState : (isSpeaking ? 'listening' : thinkingPhase === 'streaming' ? 'responding' : isTyping ? 'thinking' : 'idle')}
              style={{ width: '280px', height: '280px', opacity: 0.08 }}
            />
          </Suspense>
        </div>

        {/* ---- Input Area (always visible) ---- */}
        <div className="input-area">
          <form className="input-area__form" onSubmit={handleSubmit}>
            <input ref={inputRef} className="input-area__input" type="text"
              placeholder="Message Aisha..." value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              autoComplete="off" id="chat-input" />
            <button className="input-area__btn" type="submit"
              disabled={!input.trim() || isTyping} title="Send" id="send-button">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
