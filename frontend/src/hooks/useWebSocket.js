/**
 * useWebSocket — React hook for real-time WebSocket communication with Aisha backend.
 *
 * Features:
 *   - Auto-connect on mount
 *   - Exponential backoff reconnection
 *   - Ping/pong heartbeat keepalive
 *   - Message dispatching by type
 *   - Graceful cleanup on unmount
 *
 * Usage:
 *   const { connected, orbState, sessionId, send } = useWebSocket(API_URL)
 */

import { useState, useEffect, useRef, useCallback } from 'react'

const WS_RECONNECT_BASE_MS = 1000
const WS_RECONNECT_MAX_MS = 15000
const WS_PING_INTERVAL_MS = 25000

export default function useWebSocket(apiUrl, { onOrbState, onNotification, onChatResponse } = {}) {
  const [connected, setConnected] = useState(false)
  const [orbState, setOrbState] = useState('idle')
  const [sessionId, setSessionId] = useState(null)
  const [clientId, setClientId] = useState(null)

  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const pingTimer = useRef(null)
  const reconnectDelay = useRef(WS_RECONNECT_BASE_MS)
  const unmountedRef = useRef(false)

  // Callbacks stored in refs to avoid stale closures
  const onOrbStateRef = useRef(onOrbState)
  const onNotificationRef = useRef(onNotification)
  const onChatResponseRef = useRef(onChatResponse)
  onOrbStateRef.current = onOrbState
  onNotificationRef.current = onNotification
  onChatResponseRef.current = onChatResponse

  const wsUrl = apiUrl.replace(/^http/, 'ws') + '/ws'

  const connect = useCallback(() => {
    if (unmountedRef.current) return
    if (wsRef.current && wsRef.current.readyState <= 1) return // already connecting/open

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[WS] Connected to', wsUrl)
        setConnected(true)
        reconnectDelay.current = WS_RECONNECT_BASE_MS

        // Start heartbeat
        pingTimer.current = setInterval(() => {
          if (ws.readyState === 1) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, WS_PING_INTERVAL_MS)
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          const type = msg.type

          if (type === 'pong') return // heartbeat response

          if (type === 'connected') {
            setSessionId(msg.session_id || null)
            setClientId(msg.client_id || null)
          }

          if (type === 'orb_state') {
            setOrbState(msg.state || 'idle')
            onOrbStateRef.current?.(msg)
          }

          if (type === 'notification') {
            onNotificationRef.current?.(msg)
          }

          if (type === 'chat_response') {
            onChatResponseRef.current?.(msg)
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        console.log('[WS] Disconnected')
        setConnected(false)
        if (pingTimer.current) clearInterval(pingTimer.current)

        // Reconnect with exponential backoff
        if (!unmountedRef.current) {
          reconnectTimer.current = setTimeout(() => {
            reconnectDelay.current = Math.min(
              reconnectDelay.current * 1.5,
              WS_RECONNECT_MAX_MS
            )
            connect()
          }, reconnectDelay.current)
        }
      }

      ws.onerror = (err) => {
        console.warn('[WS] Error:', err)
        // onclose will fire after this, triggering reconnect
      }
    } catch (err) {
      console.warn('[WS] Failed to create WebSocket:', err)
      // Schedule reconnect
      if (!unmountedRef.current) {
        reconnectTimer.current = setTimeout(connect, reconnectDelay.current)
      }
    }
  }, [wsUrl])

  // Send a message over WebSocket
  const send = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === 1) {
      wsRef.current.send(JSON.stringify(data))
      return true
    }
    return false
  }, [])

  // Send typing indicator
  const sendTyping = useCallback((active) => {
    send({ type: 'typing', active })
  }, [send])

  useEffect(() => {
    unmountedRef.current = false
    connect()

    return () => {
      unmountedRef.current = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (pingTimer.current) clearInterval(pingTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null // prevent reconnect on intentional close
        wsRef.current.close()
      }
    }
  }, [connect])

  return {
    connected,
    orbState,
    sessionId,
    clientId,
    send,
    sendTyping,
  }
}
