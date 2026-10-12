import { contextBridge, ipcRenderer } from 'electron';

export interface AppUpdateInfo {
  platform: string;
  latestVersion: string;
  downloadUrl: string;
  sha256: string;
  releaseNotes: string;
  mandatory: boolean;
  publishedAt: string;
}

const roxyDesktop = {
  platform: process.platform === 'win32' ? 'windows' : process.platform === 'darwin' ? 'macos' : 'linux',
  version: '2.0.0',

  getDeviceId: async (): Promise<string> => {
    return ipcRenderer.invoke('roxy:getDeviceId');
  },

  getSecureToken: async (key: string): Promise<string | null> => {
    return ipcRenderer.invoke('roxy:getSecureToken', key);
  },

  setSecureToken: async (key: string, value: string): Promise<boolean> => {
    return ipcRenderer.invoke('roxy:setSecureToken', key, value);
  },

  deleteSecureToken: async (key: string): Promise<boolean> => {
    return ipcRenderer.invoke('roxy:deleteSecureToken', key);
  },

  showNotification: async (title: string, options?: NotificationOptions): Promise<boolean> => {
    return ipcRenderer.invoke('roxy:showNotification', title, options);
  },

  checkForUpdates: async (): Promise<AppUpdateInfo | null> => {
    return ipcRenderer.invoke('roxy:checkForUpdates');
  },

  onDeepLink: (callback: (url: string) => void): (() => void) => {
    const handler = (_event: any, url: string) => {
      callback(url);
    };
    ipcRenderer.on('roxy:deepLink', handler);
    return () => {
      ipcRenderer.removeListener('roxy:deepLink', handler);
    };
  },

  openExternal: async (url: string): Promise<void> => {
    return ipcRenderer.invoke('roxy:openExternal', url);
  },
};

contextBridge.exposeInMainWorld('roxyDesktop', roxyDesktop);
