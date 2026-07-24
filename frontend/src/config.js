/**
 * Shared configuration for Aisha frontend.
 */

export const API_URL = 'http://localhost:5000'

export function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/* ================================================================
   Handler Mode Config — maps handler names to display info
   ================================================================ */

export const HANDLER_MODES = {
  emotion:  { icon: '💜', label: 'Emotion',  color: '#ec4899', thinkText: 'Feeling your emotions...' },
  task:     { icon: '⚙️', label: 'Task',     color: '#34d399', thinkText: 'Executing task...' },
  learning: { icon: '📚', label: 'Learning', color: '#3b82f6', thinkText: 'Researching...' },
  power:    { icon: '⚡', label: 'Power',    color: '#f59e0b', thinkText: 'Running command...' },
  safety:   { icon: '🛡️', label: 'Safety',   color: '#ef4444', thinkText: 'Checking safety...' },
  general:  { icon: '🧠', label: 'General',  color: '#a78bfa', thinkText: 'Thinking...' },
}

export function getHandlerMode(handler) {
  return HANDLER_MODES[handler] || HANDLER_MODES.general
}

/* ================================================================
   Sidebar Navigation Items
   ================================================================ */

export const NAV_ITEMS = [
  { id: 'chat',      label: 'Chat',      icon: '💬' },
  { id: 'dashboard', label: 'Dashboard',  icon: '📊' },
  { id: 'schedule',  label: 'Schedule',   icon: '📅' },
  { id: 'habits',    label: 'Habits',     icon: '✅' },
  { id: 'learning',  label: 'Learning',   icon: '📚' },
  { id: 'journal',   label: 'Journal',    icon: '📓' },
]
