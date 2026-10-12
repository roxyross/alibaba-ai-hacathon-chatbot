import { autoUpdater } from 'electron-updater';
import { dialog, BrowserWindow } from 'electron';
import https from 'https';

export interface UpdateManifest {
  platform: string;
  latestVersion: string;
  downloadUrl: string;
  sha256: string;
  releaseNotes: string;
  mandatory: boolean;
  publishedAt: string;
}

const UPDATE_MANIFEST_ENDPOINT =
  process.env.ROXY_UPDATE_URL ||
  'https://roxy-personal-ai-backend.vercel.app/api/v1/devices/updates';

export async function fetchRemoteUpdateManifest(platformName: string): Promise<UpdateManifest | null> {
  const url = `${UPDATE_MANIFEST_ENDPOINT}?platform=${encodeURIComponent(platformName)}`;

  return new Promise((resolve) => {
    https
      .get(url, (res) => {
        if (res.statusCode !== 200) {
          resolve(null);
          return;
        }
        let raw = '';
        res.on('data', (chunk) => (raw += chunk));
        res.on('end', () => {
          try {
            const data = JSON.parse(raw) as UpdateManifest;
            resolve(data);
          } catch {
            resolve(null);
          }
        });
      })
      .on('error', () => {
        resolve(null);
      });
  });
}

export function initAutoUpdater(mainWindow: BrowserWindow): void {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('update-available', (info) => {
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: 'Roxy AI Update Available',
        message: `Version ${info.version} is now available. Would you like to download and install it?`,
        buttons: ['Download Update', 'Remind Me Later'],
        defaultId: 0,
        cancelId: 1,
      })
      .then((result) => {
        if (result.response === 0) {
          autoUpdater.downloadUpdate().catch((err) => {
            console.error('Failed to download update:', err);
          });
        }
      });
  });

  autoUpdater.on('update-downloaded', () => {
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        title: 'Update Ready to Install',
        message: 'Roxy AI has downloaded the new update. Restart now to apply?',
        buttons: ['Restart and Install', 'Later'],
        defaultId: 0,
        cancelId: 1,
      })
      .then((result) => {
        if (result.response === 0) {
          autoUpdater.quitAndInstall();
        }
      });
  });

  autoUpdater.on('error', (err) => {
    console.warn('AutoUpdater warning:', err?.message || err);
  });
}
