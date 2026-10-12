import {
  PlatformType,
  DeviceInfoModel,
  DeepLinkRoute,
  PushNotificationPayload,
  AppUpdateInfo,
} from './types';

const DEVICE_ID_KEY = 'roxy.device.identity';
const PUSH_TOKEN_KEY = 'roxy.device.push_token';
const APP_VERSION = '2.0.0';

export class PlatformBridge {
  private static instance: PlatformBridge | null = null;
  private deepLinkListeners: Set<(route: DeepLinkRoute) => void> = new Set();
  private cachedDeviceInfo: DeviceInfoModel | null = null;

  private constructor() {
    this.initDeepLinkHandling();
  }

  public static getInstance(): PlatformBridge {
    if (!PlatformBridge.instance) {
      PlatformBridge.instance = new PlatformBridge();
    }
    return PlatformBridge.instance;
  }

  // ---------------------------------------------------------------------------
  // 1. Runtime Environment Detection
  // ---------------------------------------------------------------------------

  public getPlatform(): PlatformType {
    if (typeof window === 'undefined') return 'web';
    if (window.roxyDesktop?.isElectron) return 'desktop';
    if (window.Capacitor?.isNativePlatform()) {
      const capPlatform = window.Capacitor.getPlatform().toLowerCase();
      if (capPlatform === 'android') return 'android';
      if (capPlatform === 'ios') return 'ios';
    }
    return 'web';
  }

  public isDesktop(): boolean {
    return this.getPlatform() === 'desktop';
  }

  public isAndroid(): boolean {
    return this.getPlatform() === 'android';
  }

  public isIOS(): boolean {
    return this.getPlatform() === 'ios';
  }

  public isNativeMobile(): boolean {
    const p = this.getPlatform();
    return p === 'android' || p === 'ios';
  }

  public isWeb(): boolean {
    return this.getPlatform() === 'web';
  }

  // ---------------------------------------------------------------------------
  // 2. Hardware Device Identity & Metadata
  // ---------------------------------------------------------------------------

  public async getDeviceInfo(): Promise<DeviceInfoModel> {
    if (this.cachedDeviceInfo) {
      return this.cachedDeviceInfo;
    }

    const platform = this.getPlatform();
    let deviceId = await this.getSecureItem(DEVICE_ID_KEY);
    if (!deviceId) {
      const randomSegment = Math.random().toString(36).substring(2, 10);
      const timestampSegment = Date.now().toString(36);
      deviceId = `dev-${platform}-${randomSegment}-${timestampSegment}`;
      await this.setSecureItem(DEVICE_ID_KEY, deviceId);
    }

    let osPlatform: 'windows' | 'darwin' | 'linux' | 'android' | 'ios' | 'web' = 'web';
    let osVersion = 'Browser';
    let architecture = 'x86_64';
    let hostname = 'localhost';
    let deviceName = 'Roxy Web Client';

    if (platform === 'desktop' && window.roxyDesktop) {
      osPlatform = window.roxyDesktop.platform;
      osVersion = window.roxyDesktop.osVersion || 'Desktop OS';
      hostname = 'Desktop-Host';
      deviceName = `Roxy Desktop (${window.roxyDesktop.platform})`;
    } else if (platform === 'android') {
      osPlatform = 'android';
      osVersion = 'Android 14+';
      architecture = 'arm64-v8a';
      hostname = 'android-device';
      deviceName = 'Roxy Android Companion';
    } else if (platform === 'ios') {
      osPlatform = 'ios';
      osVersion = 'iOS 16+';
      architecture = 'arm64';
      hostname = 'ios-device';
      deviceName = 'Roxy iOS Client';
    } else if (typeof navigator !== 'undefined') {
      const ua = navigator.userAgent.toLowerCase();
      if (ua.includes('win')) osPlatform = 'windows';
      else if (ua.includes('mac')) osPlatform = 'darwin';
      else if (ua.includes('linux')) osPlatform = 'linux';
      osVersion = navigator.userAgent.substring(0, 32);
      deviceName = `Roxy Web (${osPlatform})`;
    }

    const capabilities = [
      'auth_session',
      'chat',
      'ide_studio',
      'voice_assistant',
      'reminders',
      'notifications',
      'deep_links',
    ];
    if (platform === 'desktop') {
      capabilities.push('system_tray', 'native_filesystem', 'desktop_automation');
    } else if (platform === 'android') {
      capabilities.push('android_intents', 'push_notifications', 'companion_telemetry');
    } else if (platform === 'ios') {
      capabilities.push('universal_links', 'app_intents', 'apple_shortcuts');
    }

    this.cachedDeviceInfo = {
      deviceId,
      deviceName,
      deviceType: platform === 'desktop' ? 'desktop' : platform === 'web' ? 'web' : 'mobile',
      osPlatform,
      osVersion,
      appVersion: APP_VERSION,
      architecture,
      hostname,
      capabilities,
      isCurrentHost: platform === 'desktop',
    };

    return this.cachedDeviceInfo;
  }

  public async getDeviceId(): Promise<string> {
    const info = await this.getDeviceInfo();
    return info.deviceId;
  }

  // ---------------------------------------------------------------------------
  // 3. Secure Token & Credential Storage
  // ---------------------------------------------------------------------------

  public async getSecureItem(key: string): Promise<string | null> {
    if (typeof window === 'undefined') return null;
    if (window.roxyDesktop?.secureStorage) {
      return await window.roxyDesktop.secureStorage.getItem(key);
    }
    return localStorage.getItem(key);
  }

  public async setSecureItem(key: string, value: string): Promise<void> {
    if (typeof window === 'undefined') return;
    if (window.roxyDesktop?.secureStorage) {
      await window.roxyDesktop.secureStorage.setItem(key, value);
    }
    localStorage.setItem(key, value);
  }

  public async removeSecureItem(key: string): Promise<void> {
    if (typeof window === 'undefined') return;
    if (window.roxyDesktop?.secureStorage) {
      await window.roxyDesktop.secureStorage.removeItem(key);
    }
    localStorage.removeItem(key);
  }

  public async deleteSecureItem(key: string): Promise<void> {
    return this.removeSecureItem(key);
  }

  // ---------------------------------------------------------------------------
  // 4. Device Registration & Backend Synchronization
  // ---------------------------------------------------------------------------

  public async registerDeviceWithBackend(apiBase: string, authToken: string): Promise<boolean> {
    try {
      const dev = await this.getDeviceInfo();
      const payload = {
        device_id: dev.deviceId,
        device_name: dev.deviceName,
        device_type: dev.deviceType,
        os_platform: dev.osPlatform,
        os_version: dev.osVersion,
        architecture: dev.architecture,
        hostname: dev.hostname,
        daemon_version: dev.appVersion,
        capabilities: dev.capabilities,
        is_current_host: dev.isCurrentHost,
        telemetry: {
          registered_at: new Date().toISOString(),
          platform_type: this.getPlatform(),
          app_version: dev.appVersion,
        },
      };

      const res = await fetch(`${apiBase}/devices/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(payload),
      });

      return res.ok;
    } catch (err) {
      console.warn('[PlatformBridge] Device registration skipped or failed:', err);
      return false;
    }
  }

  public async registerPushTokenWithBackend(
    apiBase: string,
    authToken: string,
    pushToken: string
  ): Promise<boolean> {
    try {
      const dev = await this.getDeviceInfo();
      await this.setSecureItem(PUSH_TOKEN_KEY, pushToken);

      const res = await fetch(`${apiBase}/devices/${dev.deviceId}/push-token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          push_token: pushToken,
          platform: this.getPlatform(),
        }),
      });

      return res.ok;
    } catch (err) {
      console.warn('[PlatformBridge] Push token registration error:', err);
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // 5. Native Notifications & Reminder Sound System
  // ---------------------------------------------------------------------------

  public async showNotification(payload: PushNotificationPayload): Promise<boolean> {
    // 1. Electron Desktop
    if (window.roxyDesktop?.notifications) {
      return await window.roxyDesktop.notifications.show(payload);
    }

    // 2. Web / Native Web Notification API
    if (typeof window !== 'undefined' && 'Notification' in window) {
      if (Notification.permission === 'granted') {
        new Notification(payload.title, {
          body: payload.body,
          icon: '/roxy-app-logo-120x120.png',
          data: payload.data,
        });
        this.playReminderSound(payload.sound);
        return true;
      } else if (Notification.permission !== 'denied') {
        const perm = await Notification.requestPermission();
        if (perm === 'granted') {
          new Notification(payload.title, {
            body: payload.body,
            icon: '/roxy-app-logo-120x120.png',
            data: payload.data,
          });
          this.playReminderSound(payload.sound);
          return true;
        }
      }
    }

    // Fallback: Audio tone only
    this.playReminderSound(payload.sound);
    return false;
  }

  public playReminderSound(_customSound?: string): void {
    if (typeof window === 'undefined') return;
    try {
      // Trigger synthesized clean chime tone via Web Audio API
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.exponentialRampToValueAtTime(880.0, ctx.currentTime + 0.15); // A5

      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.8);
    } catch {
      // Suppress audio context restrictions
    }
  }

  // ---------------------------------------------------------------------------
  // 6. Deep Linking Architecture (roxy:// and Universal Links)
  // ---------------------------------------------------------------------------

  public parseDeepLink(url: string): DeepLinkRoute {
    try {
      const parsed = new URL(url);
      const scheme = parsed.protocol.replace(':', '');
      const hostname = parsed.hostname.toLowerCase();
      const pathname = parsed.pathname.replace(/^\//, '');
      const pathParts = pathname.split('/').filter(Boolean);

      const params: Record<string, string> = {};
      parsed.searchParams.forEach((v, k) => {
        params[k] = v;
      });

      let view = 'chat';
      let sessionId: string | undefined;
      let taskId: string | undefined;
      let projectId: string | undefined;
      let codePath: string | undefined;

      // roxy://chat/xyz or https://app.roxy.ai/chat/xyz
      if (hostname === 'chat' || pathParts[0] === 'chat') {
        view = 'chat';
        sessionId = hostname === 'chat' ? pathParts[0] : pathParts[1];
      } else if (hostname === 'task' || pathParts[0] === 'task') {
        view = 'chat';
        taskId = hostname === 'task' ? pathParts[0] : pathParts[1];
        params.openTask = 'true';
      } else if (hostname === 'project' || pathParts[0] === 'project') {
        view = 'workspace_hub';
        projectId = hostname === 'project' ? pathParts[0] : pathParts[1];
      } else if (hostname === 'code' || pathParts[0] === 'code') {
        view = 'coding';
        codePath = params.path || pathParts[0];
      } else if (hostname === 'settings' || pathParts[0] === 'settings') {
        view = 'settings';
      } else if (hostname === 'device' || pathParts[0] === 'device') {
        view = 'device_hub';
      } else if (hostname === 'calendar' || pathParts[0] === 'calendar') {
        view = 'calendar';
      } else if (hostname === 'jobs' || pathParts[0] === 'jobs') {
        view = 'jobs';
      }

      return {
        rawUrl: url,
        scheme,
        view,
        sessionId,
        taskId,
        projectId,
        codePath,
        params,
      };
    } catch {
      return {
        rawUrl: url,
        scheme: 'unknown',
        view: 'chat',
        params: {},
      };
    }
  }

  public onDeepLink(callback: (route: DeepLinkRoute) => void): () => void {
    this.deepLinkListeners.add(callback);
    return () => {
      this.deepLinkListeners.delete(callback);
    };
  }

  private initDeepLinkHandling(): void {
    if (typeof window === 'undefined') return;

    // Electron desktop bridge
    if (window.roxyDesktop?.deepLinks) {
      window.roxyDesktop.deepLinks.onDeepLink((url: string) => {
        const route = this.parseDeepLink(url);
        this.deepLinkListeners.forEach((cb) => cb(route));
      });
    }

    // Web Custom Scheme / Custom Event listener
    window.addEventListener('roxy-deeplink', ((event: CustomEvent<{ url: string }>) => {
      if (event.detail?.url) {
        const route = this.parseDeepLink(event.detail.url);
        this.deepLinkListeners.forEach((cb) => cb(route));
      }
    }) as EventListener);
  }

  // ---------------------------------------------------------------------------
  // 7. App Updates Check
  // ---------------------------------------------------------------------------

  public async checkForUpdates(apiBase: string = '/api/v1'): Promise<AppUpdateInfo | null> {
    try {
      const platform = this.getPlatform();
      const res = await fetch(`${apiBase}/devices/updates?platform=${platform}`);
      if (!res.ok) return null;
      const data = await res.json();
      return {
        platform: data.platform,
        latestVersion: data.latest_version,
        downloadUrl: data.download_url,
        sha256: data.sha256,
        releaseNotes: data.release_notes,
        mandatory: Boolean(data.mandatory),
        publishedAt: data.published_at,
      };
    } catch {
      return null;
    }
  }
}

export const platformBridge = PlatformBridge.getInstance();
