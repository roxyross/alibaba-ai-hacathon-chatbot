import {
  app,
  BrowserWindow,
  ipcMain,
  safeStorage,
  Notification,
  Tray,
  Menu,
  shell,
  nativeImage,
} from 'electron';
import path from 'path';
import fs from 'fs';
import os from 'os';
import crypto from 'crypto';
import { fetchRemoteUpdateManifest, initAutoUpdater } from './updater';

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;
let pendingDeepLinkUrl: string | null = null;

// Enforce single application instance lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', (_event, commandLine) => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
    // Check command line arguments for deep links on Windows/Linux
    const deepLink = commandLine.find((arg: string) => arg.startsWith('roxy://'));
    if (deepLink && mainWindow) {
      mainWindow.webContents.send('roxy:deepLink', deepLink);
    }
  });
}

// Register roxy:// custom protocol
if (process.defaultApp) {
  if (process.argv.length >= 2) {
    app.setAsDefaultProtocolClient('roxy', process.execPath, [path.resolve(process.argv[1])]);
  }
} else {
  app.setAsDefaultProtocolClient('roxy');
}

// Handle deep links on macOS
app.on('open-url', (event, url) => {
  event.preventDefault();
  if (mainWindow && mainWindow.webContents) {
    mainWindow.webContents.send('roxy:deepLink', url);
  } else {
    pendingDeepLinkUrl = url;
  }
});

// Secure Device Identity Persistence
function getOrCreateDeviceId(): string {
  const configDir = path.join(app.getPath('userData'), 'roxy-config');
  if (!fs.existsSync(configDir)) {
    fs.mkdirSync(configDir, { recursive: true });
  }
  const idFile = path.join(configDir, 'device-identity.json');
  try {
    if (fs.existsSync(idFile)) {
      const data = JSON.parse(fs.readFileSync(idFile, 'utf-8'));
      if (data.deviceId) return data.deviceId;
    }
  } catch (err) {
    console.warn('Error reading device-identity.json:', err);
  }

  // Generate hardware-fingerprinted UUID
  const hardwareSeed = `${os.hostname()}-${os.platform()}-${os.arch()}-${os.cpus()[0]?.model || 'cpu'}`;
  const hash = crypto.createHash('sha256').update(hardwareSeed).digest('hex').slice(0, 12);
  const newId = `desktop-${os.platform()}-${hash}-${Date.now().toString(36)}`;
  try {
    fs.writeFileSync(idFile, JSON.stringify({ deviceId: newId, createdAt: new Date().toISOString() }, null, 2));
  } catch (err) {
    console.warn('Error writing device-identity.json:', err);
  }
  return newId;
}

// Token storage using Electron safeStorage (OS-level encryption: DPAPI on Windows, Keychain on macOS)
function getSecureTokensFile(): string {
  const dir = path.join(app.getPath('userData'), 'roxy-config');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, 'vault.dat');
}

function readVault(): Record<string, string> {
  const vaultPath = getSecureTokensFile();
  if (!fs.existsSync(vaultPath)) return {};
  try {
    const raw = fs.readFileSync(vaultPath);
    if (safeStorage.isEncryptionAvailable()) {
      const decrypted = safeStorage.decryptString(raw);
      return JSON.parse(decrypted);
    } else {
      return JSON.parse(raw.toString('utf-8'));
    }
  } catch {
    return {};
  }
}

function writeVault(data: Record<string, string>): boolean {
  const vaultPath = getSecureTokensFile();
  try {
    const serialized = JSON.stringify(data);
    if (safeStorage.isEncryptionAvailable()) {
      const encrypted = safeStorage.encryptString(serialized);
      fs.writeFileSync(vaultPath, encrypted);
    } else {
      fs.writeFileSync(vaultPath, Buffer.from(serialized, 'utf-8'));
    }
    return true;
  } catch (err) {
    console.error('Failed to write vault:', err);
    return false;
  }
}

function createWindow(): void {
  const iconPath = path.join(__dirname, '../resources/icon.png');

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Roxy AI',
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
    backgroundColor: '#0a0a0f',
    show: false,
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
    if (pendingDeepLinkUrl && mainWindow?.webContents) {
      mainWindow.webContents.send('roxy:deepLink', pendingDeepLinkUrl);
      pendingDeepLinkUrl = null;
    }
  });

  // Minimize to tray on close if user chooses, or prevent accidental close
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  // Load production bundle or local dev server
  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    mainWindow.loadURL(devUrl);
  } else {
    const localWebPath = path.join(__dirname, '../web/index.html');
    if (fs.existsSync(localWebPath)) {
      mainWindow.loadFile(localWebPath);
    } else {
      // Connect directly to live backend / frontend hosted environment
      mainWindow.loadURL('https://roxy-personal-ai-backend.vercel.app');
    }
  }

  // Crash recovery
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error('Renderer process gone:', details.reason);
    if (details.reason !== 'clean-exit') {
      mainWindow?.reload();
    }
  });

  initAutoUpdater(mainWindow);
}

function createTray(): void {
  const iconPath = path.join(__dirname, '../resources/icon.png');
  if (!fs.existsSync(iconPath)) return;

  const trayImage = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  tray = new Tray(trayImage);
  tray.setToolTip('Roxy AI - Autonomous Intelligence');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open Roxy AI',
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      },
    },
    {
      label: 'New Task',
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
        mainWindow?.webContents.send('roxy:deepLink', 'roxy://task/new');
      },
    },
    {
      label: 'Code Studio IDE',
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
        mainWindow?.webContents.send('roxy:deepLink', 'roxy://code/studio');
      },
    },
    { type: 'separator' },
    {
      label: 'Quit Roxy AI',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    mainWindow?.show();
    mainWindow?.focus();
  });
}

// -----------------------------------------------------------------------------
// IPC Handlers
// -----------------------------------------------------------------------------

ipcMain.handle('roxy:getDeviceId', async () => {
  return getOrCreateDeviceId();
});

ipcMain.handle('roxy:getSecureToken', async (_event, key: string) => {
  const vault = readVault();
  return vault[key] || null;
});

ipcMain.handle('roxy:setSecureToken', async (_event, key: string, value: string) => {
  const vault = readVault();
  vault[key] = value;
  return writeVault(vault);
});

ipcMain.handle('roxy:deleteSecureToken', async (_event, key: string) => {
  const vault = readVault();
  delete vault[key];
  return writeVault(vault);
});

ipcMain.handle('roxy:showNotification', async (_event, title: string, options?: NotificationOptions) => {
  if (Notification.isSupported()) {
    const notif = new Notification({
      title,
      body: options?.body,
      silent: options?.silent ?? false,
    });
    notif.show();
    return true;
  }
  return false;
});

ipcMain.handle('roxy:checkForUpdates', async () => {
  const plat = process.platform === 'win32' ? 'windows' : process.platform === 'darwin' ? 'macos' : 'linux';
  return fetchRemoteUpdateManifest(plat);
});

ipcMain.handle('roxy:openExternal', async (_event, url: string) => {
  if (url.startsWith('https://') || url.startsWith('http://') || url.startsWith('mailto:')) {
    await shell.openExternal(url);
  }
});

// App lifecycle
app.whenReady().then(() => {
  createWindow();
  createTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on('before-quit', () => {
  isQuitting = true;
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
