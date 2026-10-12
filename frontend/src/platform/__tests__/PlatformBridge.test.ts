import { describe, it, expect, beforeEach, vi } from 'vitest';
import { platformBridge } from '../PlatformBridge';

describe('Roxy-AI PlatformBridge Client Architecture', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('detects default web environment when run in browser or jsdom', () => {
    expect(platformBridge.getPlatform()).toBe('web');
    expect(platformBridge.isWeb()).toBe(true);
    expect(platformBridge.isDesktop()).toBe(false);
    expect(platformBridge.isNativeMobile()).toBe(false);
  });

  it('generates, persists, and reuses hardware device ID in secure storage', async () => {
    const id1 = await platformBridge.getDeviceId();
    expect(id1).toBeTruthy();
    expect(id1.startsWith('dev-web-')).toBe(true);

    const id2 = await platformBridge.getDeviceId();
    expect(id2).toBe(id1);

    const info = await platformBridge.getDeviceInfo();
    expect(info.deviceId).toBe(id1);
    expect(info.appVersion).toBe('2.0.0');
    expect(info.capabilities).toContain('chat');
    expect(info.capabilities).toContain('ide_studio');
  });

  it('stores, retrieves, and removes secure credentials', async () => {
    await platformBridge.setSecureItem('auth_token', 'jwt_test_token_sample');
    const retrieved = await platformBridge.getSecureItem('auth_token');
    expect(retrieved).toBe('jwt_test_token_sample');

    await platformBridge.deleteSecureItem('auth_token');
    const afterDelete = await platformBridge.getSecureItem('auth_token');
    expect(afterDelete).toBeNull();
  });

  it('correctly parses custom scheme deep links (roxy://)', () => {
    const chatRoute = platformBridge.parseDeepLink('roxy://chat/sess-12345');
    expect(chatRoute.view).toBe('chat');
    expect(chatRoute.sessionId).toBe('sess-12345');

    const codeRoute = platformBridge.parseDeepLink('roxy://code?path=frontend%2Fsrc%2FApp.tsx');
    expect(codeRoute.view).toBe('coding');
    expect(codeRoute.codePath).toBe('frontend/src/App.tsx');

    const taskRoute = platformBridge.parseDeepLink('roxy://task/new');
    expect(taskRoute.view).toBe('chat');
    expect(taskRoute.taskId).toBe('new');
    expect(taskRoute.params.openTask).toBe('true');

    const settingsRoute = platformBridge.parseDeepLink('roxy://settings');
    expect(settingsRoute.view).toBe('settings');

    const deviceRoute = platformBridge.parseDeepLink('roxy://device/status');
    expect(deviceRoute.view).toBe('device_hub');
  });

  it('correctly parses universal links (https://app.roxy.ai)', () => {
    const universalChat = platformBridge.parseDeepLink('https://app.roxy.ai/chat/conv-999');
    expect(universalChat.view).toBe('chat');
    expect(universalChat.sessionId).toBe('conv-999');

    const universalProject = platformBridge.parseDeepLink('https://app.roxy.ai/project/proj-456');
    expect(universalProject.view).toBe('workspace_hub');
    expect(universalProject.projectId).toBe('proj-456');
  });

  it('gracefully checks update availability from backend endpoint', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        platform: 'web',
        latest_version: '2.0.0',
        download_url: 'https://app.roxy.ai',
        sha256: 'abc123sha',
        release_notes: 'Production 2.0 release',
        mandatory: false,
        published_at: '2026-10-13T00:00:00Z',
      }),
    } as any);

    const update = await platformBridge.checkForUpdates('http://test/api/v1');
    expect(update).not.toBeNull();
    expect(update?.latestVersion).toBe('2.0.0');
    expect(update?.mandatory).toBe(false);
  });

  it('safely triggers synthesized reminder chime without throwing errors', () => {
    expect(() => platformBridge.playReminderSound()).not.toThrow();
  });
});
