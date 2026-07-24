const { contextBridge, ipcRenderer } = require('electron');

/**
 * Preload for the mini always-on-top window.
 * Exposes a minimal `window.miniAPI` to the mini window renderer.
 */
contextBridge.exposeInMainWorld('miniAPI', {
  // Receive the latest Aisha response text
  onResponse: (callback) => {
    ipcRenderer.on('mini:response', (_event, text) => callback(text));
  },

  // Receive typing state updates
  onTyping: (callback) => {
    ipcRenderer.on('mini:typing', (_event, isTyping) => callback(isTyping));
  },

  // Receive handler + emotion info
  onHandler: (callback) => {
    ipcRenderer.on('mini:handler', (_event, handler, emotion) => callback(handler, emotion));
  },

  // Notify main process about mic toggle
  toggleMic: (active) => {
    ipcRenderer.send('mini:mic-toggle', active);
  },

  // Request the main process to hide this window
  hide: () => {
    ipcRenderer.send('mini:hide');
  },

  // Request to show/focus the main window
  expandMain: () => {
    ipcRenderer.send('mini:expand-main');
  },

  // Toggle voice mute
  muteVoice: (muted) => {
    ipcRenderer.send('mini:mute-voice', muted);
  },
});
