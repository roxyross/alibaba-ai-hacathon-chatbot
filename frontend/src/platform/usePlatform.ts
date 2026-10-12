import { useState, useEffect, useCallback } from 'react';
import { platformBridge } from './PlatformBridge';
import type { PlatformType, DeviceInfoModel, DeepLinkRoute, AppUpdateInfo } from './types';

export interface UsePlatformResult {
  platform: PlatformType;
  isNative: boolean;
  isDesktop: boolean;
  isMobile: boolean;
  deviceId: string | null;
  deviceInfo: DeviceInfoModel | null;
  currentDeepLink: DeepLinkRoute | null;
  updateInfo: AppUpdateInfo | null;
  checkForUpdates: (apiBase?: string) => Promise<AppUpdateInfo | null>;
  showNotification: (title: string, body?: string) => Promise<boolean>;
  playReminderSound: () => void;
  registerWithBackend: (apiBase: string, authToken: string) => Promise<boolean>;
}

export function usePlatform(): UsePlatformResult {
  const [platform, setPlatform] = useState<PlatformType>('web');
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfoModel | null>(null);
  const [currentDeepLink, setCurrentDeepLink] = useState<DeepLinkRoute | null>(null);
  const [updateInfo, setUpdateInfo] = useState<AppUpdateInfo | null>(null);

  useEffect(() => {
    let mounted = true;

    async function initPlatform() {
      const plat = platformBridge.getPlatform();
      const devId = await platformBridge.getDeviceId();
      const devInfo = await platformBridge.getDeviceInfo();

      if (mounted) {
        setPlatform(plat);
        setDeviceId(devId);
        setDeviceInfo(devInfo);
      }
    }

    initPlatform();

    const unsubscribe = platformBridge.onDeepLink((route) => {
      if (mounted) {
        setCurrentDeepLink(route);
      }
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  const checkForUpdates = useCallback(async (apiBase?: string): Promise<AppUpdateInfo | null> => {
    const info = await platformBridge.checkForUpdates(apiBase);
    setUpdateInfo(info);
    return info;
  }, []);

  const showNotification = useCallback(
    async (title: string, body: string = ''): Promise<boolean> => {
      return platformBridge.showNotification({ title, body });
    },
    []
  );

  const playReminderSound = useCallback((): void => {
    platformBridge.playReminderSound();
  }, []);

  const registerWithBackend = useCallback(
    async (apiBase: string, authToken: string): Promise<boolean> => {
      const success = await platformBridge.registerDeviceWithBackend(apiBase, authToken);
      if (success) {
        const updated = await platformBridge.getDeviceInfo();
        setDeviceInfo(updated);
      }
      return success;
    },
    []
  );

  const isDesktop = platform === 'desktop';
  const isMobile = platform === 'android' || platform === 'ios';
  const isNative = isDesktop || isMobile;

  return {
    platform,
    isNative,
    isDesktop,
    isMobile,
    deviceId,
    deviceInfo,
    currentDeepLink,
    updateInfo,
    checkForUpdates,
    showNotification,
    playReminderSound,
    registerWithBackend,
  };
}
