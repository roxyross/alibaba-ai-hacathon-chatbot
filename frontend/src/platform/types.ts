/**
 * Platform Abstraction Types for ROXY-AI Multi-Client Distribution
 * (Windows Desktop, macOS Desktop, Linux, Android, iOS, and Web)
 */

export type PlatformType = 'desktop' | 'android' | 'ios' | 'web';

export interface DeviceInfoModel {
  deviceId: string;
  deviceName: string;
  deviceType: 'desktop' | 'mobile' | 'web';
  osPlatform: 'windows' | 'darwin' | 'linux' | 'android' | 'ios' | 'web';
  osVersion: string;
  appVersion: string;
  architecture: string;
  hostname: string;
  capabilities: string[];
  isCurrentHost: boolean;
}

export interface DeepLinkRoute {
  rawUrl: string;
  scheme: string;
  view: string;
  sessionId?: string;
  taskId?: string;
  projectId?: string;
  codePath?: string;
  params: Record<string, string>;
}

export interface PushNotificationPayload {
  title: string;
  body: string;
  sound?: string;
  channelId?: string;
  actionUrl?: string;
  data?: Record<string, any>;
}

export interface AppUpdateInfo {
  platform: string;
  latestVersion: string;
  downloadUrl: string;
  sha256: string;
  releaseNotes: string;
  mandatory: boolean;
  publishedAt: string;
}

export interface SecureStorageProvider {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
}

/**
 * Window extension for Electron Desktop IPC Bridge
 */
export interface RoxyDesktopBridge {
  isElectron: boolean;
  platform: 'windows' | 'darwin' | 'linux';
  osVersion: string;
  appVersion: string;
  secureStorage: {
    getItem: (key: string) => Promise<string | null>;
    setItem: (key: string, value: string) => Promise<void>;
    removeItem: (key: string) => Promise<void>;
  };
  notifications: {
    show: (payload: PushNotificationPayload) => Promise<boolean>;
  };
  deepLinks: {
    onDeepLink: (callback: (url: string) => void) => () => void;
  };
  tray: {
    updateStatus: (status: string) => void;
  };
  updater: {
    checkForUpdates: () => Promise<AppUpdateInfo | null>;
    installUpdate: () => Promise<void>;
  };
  windowControls?: {
    minimize: () => void;
    maximize: () => void;
    close: () => void;
  };
}

declare global {
  interface Window {
    roxyDesktop?: RoxyDesktopBridge;
    Capacitor?: {
      isNativePlatform: () => boolean;
      getPlatform: () => string;
    };
  }
}
