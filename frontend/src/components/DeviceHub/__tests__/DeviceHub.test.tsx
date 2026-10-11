import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import { DeviceFleetPanel } from '../DeviceFleetPanel';
import { ApplicationsPanel } from '../ApplicationsPanel';
import { PermissionsMatrixPanel } from '../PermissionsMatrixPanel';
import { LiveActivityAuditPanel } from '../LiveActivityAuditPanel';
import { ScreenSurfacePanel } from '../ScreenSurfacePanel';
import type {
  DeviceInfo,
  DiscoveredAppItem,
  PermissionGrant,
  VerificationRecord,
  RecoveryRecord,
  WorkspaceSurfaceSession,
} from '../DeviceHub';

describe('Phase 19: Universal App Control UI Component Suite', () => {
  const mockDevice: DeviceInfo = {
    id: 'dev_mock_host',
    user_id: 'user_test',
    device_name: 'ROXY Master Workstation',
    device_type: 'desktop',
    os_platform: 'windows',
    os_version: '11.0.26100',
    architecture: 'x86_64',
    hostname: 'DESKTOP-ROXY',
    ip_address: '192.168.1.100',
    status: 'online',
    is_current_host: true,
    capabilities: ['app_discovery', 'process_control', 'screen_capture'],
    telemetry: {
      cpu_percent: 18,
      memory_percent: 44,
      disk_free_gb: 256.2,
      active_window: 'Visual Studio Code',
      hostname: 'DESKTOP-ROXY',
      os_platform: 'windows',
      timestamp: new Date().toISOString(),
    },
    last_heartbeat_at: new Date().toISOString(),
  };

  const mockMobileCompanion: DeviceInfo = {
    id: 'dev_mock_mobile',
    user_id: 'user_test',
    device_name: 'Pixel 8 Pro Companion',
    device_type: 'mobile',
    os_platform: 'android',
    os_version: '14.0',
    architecture: 'arm64',
    hostname: 'pixel-companion',
    ip_address: '192.168.1.105',
    status: 'online',
    is_current_host: false,
    capabilities: ['android_automation', 'deep_links'],
    telemetry: {
      cpu_percent: 8,
      memory_percent: 32,
      active_window: 'com.spotify.music',
    },
    last_heartbeat_at: new Date().toISOString(),
  };

  const mockApps: DiscoveredAppItem[] = [
    {
      id: 'app_vscode',
      device_id: 'dev_mock_host',
      app_name: 'Visual Studio Code',
      executable_path: 'C:\\Users\\USER\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
      category: 'development',
      is_running: true,
      process_id: 10420,
      launch_count: 42,
    },
    {
      id: 'app_chrome',
      device_id: 'dev_mock_host',
      app_name: 'Google Chrome',
      executable_path: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      category: 'browser',
      is_running: false,
      launch_count: 85,
    },
  ];

  const mockGrants: PermissionGrant[] = [
    {
      id: 'grant_1',
      user_id: 'user_test',
      permission: 'device:read',
      policy: 'allow_automatically',
      scope: 'device',
      device_id: 'dev_mock_host',
    },
    {
      id: 'grant_2',
      user_id: 'user_test',
      permission: 'device:execute',
      policy: 'always_ask',
      scope: 'device',
      device_id: 'dev_mock_host',
    },
  ];

  const mockVerificationRecords: VerificationRecord[] = [
    {
      id: 'ver_proof_1',
      device_id: 'dev_mock_host',
      evidence_type: 'window',
      verified: true,
      confidence: 1.0,
      proof_hash: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      latency_ms: 12.5,
      details: { target: 'Spotify', window_state: 'foreground_focused' },
      timestamp: new Date().toISOString(),
    },
  ];

  const mockRecoveryRecords: RecoveryRecord[] = [
    {
      id: 'rec_trace_1',
      device_id: 'dev_mock_host',
      goal: 'Play Chill Hits on Spotify',
      primary_tier: 'api',
      final_status: 'recovered',
      tier_traversed: ['api', 'browser', 'desktop'],
      error_category: 'AUTH_EXPIRED',
      self_correction_applied: 'FALLBACK_TO_DESKTOP_ROUTE',
      cryptographic_proof_hash: '4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a',
      total_duration_ms: 1450,
      timestamp: new Date().toISOString(),
    },
  ];

  const mockWorkspaceSessions: WorkspaceSurfaceSession[] = [
    {
      session_id: 'sess_workspace_1',
      device_id: 'dev_mock_host',
      target_url: 'https://app.slack.com',
      embedding_mode: 'safe_iframe',
      status: 'active',
      created_at: new Date().toISOString(),
    },
  ];

  const cleanHtml = (raw: string) => raw.replace(/<!--.*?-->/g, '');

  it('renders Connected Devices Panel with platform badges and telemetry', () => {
    const rawHtml = renderToString(
      <DeviceFleetPanel
        devices={[mockDevice, mockMobileCompanion]}
        selectedDevice={mockDevice}
        onSelectDevice={() => {}}
        onRefreshDevices={async () => {}}
        onEnrollDevice={async () => {}}
        onCreateEnrollmentToken={async () => 'roxy_enroll_test'}
        onPingDevice={async () => {}}
        loading={false}
      />
    );
    const html = cleanHtml(rawHtml);

    // Verify Fleet stats & cards
    expect(html).toContain('ROXY Master Workstation');
    expect(html).toContain('Pixel 8 Pro Companion');
    expect(html).toContain('Host Machine');
    expect(html).toContain('Active Target');
    expect(html).toContain('WINDOWS (x86_64)');
    expect(html).toContain('192.168.1.100');
    expect(html).toContain('Controlling This Device');
    expect(html).toContain('Switch Control Focus');
  });

  it('renders Applications Catalog with route badges and running controls', () => {
    const html = renderToString(
      <ApplicationsPanel
        device={mockDevice}
        apps={mockApps}
        workspaceSessions={mockWorkspaceSessions}
        loadingApps={false}
        scanningApps={false}
        actingAppId={null}
        onScanApps={async () => {}}
        onLaunchApp={async () => {}}
        onCloseApp={async () => {}}
        onFocusApp={async () => {}}
        onCreateEmbedSession={async () => {}}
        onTerminateEmbedSession={async () => {}}
        onTriggerResilientExec={() => {}}
      />
    );

    expect(html).toContain('Visual Studio Code');
    expect(html).toContain('Google Chrome');
    expect(html).toContain('RUNNING');
    expect(html).toContain('Desktop Route');
    expect(html).toContain('Browser Route');
    expect(html).toContain('API Route');
    expect(html).toContain('Resilient Exec');
    expect(html).toContain('In-Roxy Workspace Active Surfaces (Phase 16)');
    expect(html).toContain('https://app.slack.com');
  });

  it('renders Target-Scoped Permissions Matrix with 3-way segmented switches', () => {
    const html = renderToString(
      <PermissionsMatrixPanel
        device={mockDevice}
        activeGrants={mockGrants}
        loadingGrants={false}
        onUpdatePermission={async () => {}}
        onRevokeGrant={async () => {}}
        onRefreshGrants={async () => {}}
      />
    );

    expect(html).toContain('System Discovery &amp; Telemetry');
    expect(html).toContain('App Process Control &amp; Launch');
    expect(html).toContain('Visual Screen Inspection &amp; OCR');
    expect(html).toContain('Synthetic Input &amp; Hotkeys');
    expect(html).toContain('Allow Automatically');
    expect(html).toContain('Always Ask');
    expect(html).toContain('Never Allow');
    expect(html).toContain('Strict Zero-Trust');
    expect(html).toContain('Autonomous Operator');
  });

  it('renders Live Activity Audit UX with Phase 17 proofs and Phase 18 recovery trajectories', () => {
    const rawHtml = renderToString(
      <LiveActivityAuditPanel
        device={mockDevice}
        actionLogs={[]}
        verificationRecords={mockVerificationRecords}
        recoveryRecords={mockRecoveryRecords}
        loading={false}
        onRefresh={async () => {}}
        onTriggerRecoverySimulation={async () => {}}
        simulatingRecovery={false}
      />
    );
    const html = cleanHtml(rawHtml);

    // Phase 17 Proofs
    expect(html).toContain('Phase 17 Verification');
    expect(html).toContain('Cryptographic Proof (SHA-256)');
    expect(html).toContain('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08');

    // Phase 18 Recovery Fallback Trajectory
    expect(html).toContain('Phase 18 Recovery');
    expect(html).toContain('Play Chill Hits on Spotify');
    expect(html).toContain('Fallback Trajectory:');
    expect(html).toContain('Tier 1: API ROUTE');
    expect(html).toContain('Tier 2: BROWSER ROUTE');
    expect(html).toContain('Tier 3: DESKTOP ROUTE');
    expect(html).toContain('FALLBACK_TO_DESKTOP_ROUTE');
  });

  it('renders Display & Screen Surface Panel with resolution metadata', () => {
    const rawHtml = renderToString(
      <ScreenSurfacePanel
        device={mockDevice}
        latestScreen={{
          device_id: 'dev_mock_host',
          image_url: '/static/screens/demo.png',
          width: 2560,
          height: 1440,
          captured_at: new Date().toISOString(),
        }}
        capturingScreen={false}
        onCaptureScreen={async () => {}}
        onShowNotification={() => {}}
      />
    );
    const html = cleanHtml(rawHtml);

    expect(html).toContain('Display &amp; Surface Inspection');
    expect(html).toContain('2560 × 1440 px');
    expect(html).toContain('Capture Screenshot');
    expect(html).toContain('/static/screens/demo.png');
  });
});
