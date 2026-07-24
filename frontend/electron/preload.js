const { contextBridge, ipcRenderer } = require('electron');

/**
 * Preload script — exposes a safe, limited API to the renderer process
 * via `window.electronAPI`. Context isolation is enabled, so the renderer
 * cannot access Node.js or Electron internals directly.
 */
contextBridge.exposeInMainWorld('electronAPI', {
  // ─── App Info ────────────────────────────────────────────────
  getVersion: () => ipcRenderer.invoke('app:getVersion'),
  getPlatform: () => ipcRenderer.invoke('app:getPlatform'),

  // ─── Window Controls ────────────────────────────────────────
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  close: () => ipcRenderer.invoke('window:close'),

  // ─── Native Notifications ──────────────────────────────────────
  showNotification: (title, body) => ipcRenderer.invoke('notification:show', title, body),

  // ─── Mini Window ────────────────────────────────────────────
  // Send latest Aisha response to the mini overlay
  sendToMini: (text) => {
    ipcRenderer.send('mini:send-response', text);
  },

  // Send typing indicator state to the mini overlay
  sendTypingToMini: (isTyping) => {
    ipcRenderer.send('mini:send-typing', isTyping);
  },

  // Toggle mini window visibility from React
  toggleMiniWindow: () => ipcRenderer.invoke('mini:toggle'),

  // ─── Mic Overlay ────────────────────────────────────────────
  // Toggle mic overlay visibility
  toggleMic: () => ipcRenderer.invoke('mic:toggle'),

  // Show mic overlay and start listening
  activateMic: () => ipcRenderer.invoke('mic:activate'),

  // Listen for voice transcripts from the mic overlay
  onVoiceTranscript: (callback) => {
    const handler = (_event, data) => {
      if (data.type === 'voice-transcript') {
        callback(data.text, data.isFinal);
      }
    };
    ipcRenderer.on('fromMain', handler);
    return () => ipcRenderer.removeListener('fromMain', handler);
  },

  // Listen for voice listening state changes
  onVoiceState: (callback) => {
    const handler = (_event, data) => {
      if (data.type === 'voice-state') {
        callback(data.isListening);
      }
    };
    ipcRenderer.on('fromMain', handler);
    return () => ipcRenderer.removeListener('fromMain', handler);
  },

  // ─── Generic IPC ────────────────────────────────────────────
  // Send a message to the main process
  send: (channel, ...args) => {
    const allowedChannels = ['toMain', 'mini:send-response', 'mini:send-typing'];
    if (allowedChannels.includes(channel)) {
      ipcRenderer.send(channel, ...args);
    }
  },

  // Receive a message from the main process
  on: (channel, callback) => {
    const allowedChannels = ['fromMain'];
    if (allowedChannels.includes(channel)) {
      const subscription = (_event, ...args) => callback(...args);
      ipcRenderer.on(channel, subscription);
      // Return cleanup function
      return () => ipcRenderer.removeListener(channel, subscription);
    }
  },

  // One-time listener
  once: (channel, callback) => {
    const allowedChannels = ['fromMain'];
    if (allowedChannels.includes(channel)) {
      ipcRenderer.once(channel, (_event, ...args) => callback(...args));
    }
  },
});
