const { contextBridge, ipcRenderer } = require('electron');

/**
 * Preload for the floating mic overlay.
 * Exposes a minimal `window.micAPI` to the overlay renderer.
 */
contextBridge.exposeInMainWorld('micAPI', {
  // Send speech transcript to main process (interim or final)
  sendTranscript: (text, isFinal) => {
    ipcRenderer.send('mic:transcript', { text, isFinal });
  },

  // Send listening state change to main process
  sendState: (isListening) => {
    ipcRenderer.send('mic:state', isListening);
  },

  // Receive remote activation (from Alt+Space shortcut)
  onActivate: (callback) => {
    ipcRenderer.on('mic:activate', () => callback());
  },

  // Receive remote deactivation
  onDeactivate: (callback) => {
    ipcRenderer.on('mic:deactivate', () => callback());
  },
});
