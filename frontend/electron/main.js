const { app, BrowserWindow, ipcMain, globalShortcut, screen, Notification } = require('electron');
const path = require('path');

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (require('electron-squirrel-startup')) {
  app.quit();
}

/**
 * Determines whether the app is running in development mode.
 * In dev mode, the React dev server is used; in production, the built dist is loaded.
 */
const isDev = process.env.ELECTRON_DEV === 'true';
const DEV_SERVER_URL = 'http://localhost:5173';

let mainWindow;
let miniWindow;
let micOverlay;

// ─── Main Window ─────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0a0a0f',
    show: false, // Prevent white flash on load
    frame: true,
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#0a0a0f',
      symbolColor: '#a78bfa',
      height: 36,
    },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
    },
    // Rounded corners on Windows 11+ (handled by OS when using titleBarStyle: hidden)
    roundedCorners: true,
  });

  // Load the React app
  if (isDev) {
    mainWindow.loadURL(DEV_SERVER_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // Show window once content is ready (eliminates white flash)
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ─── Mini Always-On-Top Window ───────────────────────────────────

const MINI_WIDTH = 300;
const MINI_HEIGHT = 120;
const MINI_MARGIN = 16; // gap from screen edges

function createMiniWindow() {
  // Calculate bottom-right position
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;
  const x = screenW - MINI_WIDTH - MINI_MARGIN;
  const y = screenH - MINI_HEIGHT - MINI_MARGIN;

  miniWindow = new BrowserWindow({
    width: MINI_WIDTH,
    height: MINI_HEIGHT,
    x,
    y,
    alwaysOnTop: true,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    skipTaskbar: true,
    focusable: true,
    hasShadow: false, // we draw our own shadow in CSS
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload-mini.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
    },
  });

  miniWindow.loadFile(path.join(__dirname, 'mini-window.html'));

  miniWindow.on('closed', () => {
    miniWindow = null;
  });
}

/**
 * Toggle mini window visibility.
 * Creates the window lazily on first toggle.
 */
function toggleMiniWindow() {
  if (!miniWindow) {
    createMiniWindow();
    miniWindow.once('ready-to-show', () => miniWindow.show());
    return;
  }

  if (miniWindow.isVisible()) {
    miniWindow.hide();
  } else {
    // Re-position to bottom-right in case resolution changed
    const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;
    miniWindow.setPosition(
      screenW - MINI_WIDTH - MINI_MARGIN,
      screenH - MINI_HEIGHT - MINI_MARGIN
    );
    miniWindow.show();
  }
}

// ─── Floating Mic Overlay ─────────────────────────────────────────

const MIC_SIZE = 60;
const MIC_MARGIN = 20;

function createMicOverlay() {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;
  const x = screenW - MIC_SIZE - MIC_MARGIN;
  const y = screenH - MIC_SIZE - MINI_HEIGHT - MINI_MARGIN - MIC_MARGIN;

  micOverlay = new BrowserWindow({
    width: MIC_SIZE,
    height: MIC_SIZE,
    x,
    y,
    alwaysOnTop: true,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload-mic.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
    },
  });

  micOverlay.loadFile(path.join(__dirname, 'mic-overlay.html'));

  // Make window click-through when not hovered (circular shape)
  micOverlay.setIgnoreMouseEvents(false);

  micOverlay.on('closed', () => {
    micOverlay = null;
  });
}

/**
 * Toggle mic overlay visibility.
 * Creates the window lazily on first use.
 */
function toggleMicOverlay() {
  if (!micOverlay) {
    createMicOverlay();
    micOverlay.once('ready-to-show', () => micOverlay.show());
    return;
  }

  if (micOverlay.isVisible()) {
    micOverlay.hide();
  } else {
    // Re-position in case resolution changed
    const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;
    micOverlay.setPosition(
      screenW - MIC_SIZE - MIC_MARGIN,
      screenH - MIC_SIZE - MINI_HEIGHT - MINI_MARGIN - MIC_MARGIN
    );
    micOverlay.show();
  }
}

/**
 * Activate/toggle the mic listening from a global shortcut
 * without toggling the overlay visibility.
 */
function activateMic() {
  if (!micOverlay) {
    createMicOverlay();
    micOverlay.once('ready-to-show', () => {
      micOverlay.show();
      micOverlay.webContents.send('mic:activate');
    });
    return;
  }

  if (!micOverlay.isVisible()) {
    micOverlay.show();
  }
  micOverlay.webContents.send('mic:activate');
}

// ─── IPC Handlers ────────────────────────────────────────────────
// Basic IPC setup — extend these as needed

ipcMain.handle('app:getVersion', () => {
  return app.getVersion();
});

ipcMain.handle('app:getPlatform', () => {
  return process.platform;
});

ipcMain.handle('window:minimize', () => {
  mainWindow?.minimize();
});

ipcMain.handle('window:maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});

ipcMain.handle('window:close', () => {
  mainWindow?.close();
});

// ─── Native Desktop Notifications ────────────────────────────────

/**
 * Show a native OS notification. Clicking it brings the main window
 * back into focus.
 */
ipcMain.handle('notification:show', (_event, title, body) => {
  if (!Notification.isSupported()) return;

  const notif = new Notification({
    title: title || 'Aisha',
    body: body || 'New notification',
    icon: path.join(__dirname, '..', 'public', 'vite.svg'),
    silent: false,
  });

  notif.on('click', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  notif.show();
});

// ─── Mini Window IPC ─────────────────────────────────────────────

// React app sends latest response → forward to mini window
ipcMain.on('mini:send-response', (_event, text) => {
  if (miniWindow && !miniWindow.isDestroyed()) {
    miniWindow.webContents.send('mini:response', text);
  }
});

// React app sends typing state → forward to mini window
ipcMain.on('mini:send-typing', (_event, isTyping) => {
  if (miniWindow && !miniWindow.isDestroyed()) {
    miniWindow.webContents.send('mini:typing', isTyping);
  }
});

// Mini window requests hide
ipcMain.on('mini:hide', () => {
  miniWindow?.hide();
});

// Mini window mic toggle → forward to main window
ipcMain.on('mini:mic-toggle', (_event, active) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('fromMain', { type: 'mic-toggle', active });
  }
});

// Mini window expand → show and focus main window
ipcMain.on('mini:expand-main', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
  }
});

// Mini window mute voice → forward to main window
ipcMain.on('mini:mute-voice', (_event, muted) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('fromMain', { type: 'voice-mute', muted });
  }
});

// Toggle mini window from React app
ipcMain.handle('mini:toggle', () => {
  toggleMiniWindow();
});

// ─── Mic Overlay IPC ─────────────────────────────────────────────

// Mic overlay sends speech transcript → forward to main React window
ipcMain.on('mic:transcript', (_event, { text, isFinal }) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('fromMain', {
      type: 'voice-transcript',
      text,
      isFinal,
    });
  }
  // Also update the mini window with final transcripts
  if (isFinal && miniWindow && !miniWindow.isDestroyed()) {
    miniWindow.webContents.send('mini:typing', false);
  }
});

// Mic overlay sends listening state → forward to React
ipcMain.on('mic:state', (_event, isListening) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('fromMain', {
      type: 'voice-state',
      isListening,
    });
  }
  // Show typing indicator on mini window when listening
  if (miniWindow && !miniWindow.isDestroyed()) {
    miniWindow.webContents.send('mini:typing', isListening);
  }
});

// Toggle mic overlay from React app
ipcMain.handle('mic:toggle', () => {
  toggleMicOverlay();
});

// Show mic overlay and activate listening from React
ipcMain.handle('mic:activate', () => {
  activateMic();
});

// ─── App Lifecycle ───────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();

  // Register global shortcut: Ctrl+Shift+A toggles mini window
  globalShortcut.register('CommandOrControl+Shift+A', () => {
    toggleMiniWindow();
  });

  // Register global shortcut: Alt+Space activates mic overlay
  globalShortcut.register('Alt+Space', () => {
    activateMic();
  });

  app.on('activate', () => {
    // macOS: re-create window when dock icon is clicked and no windows are open
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('will-quit', () => {
  // Unregister all shortcuts when app is quitting
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
