import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Monitor,
  Radio,
  Layers,
  Shield,
  Activity,
  Camera,
  ArrowLeft,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ShieldCheck,
  Smartphone,
  Globe,
  Check,
  X,
} from 'lucide-react';
import { DeviceFleetPanel } from './DeviceFleetPanel';
import { ApplicationsPanel } from './ApplicationsPanel';
import { PermissionsMatrixPanel } from './PermissionsMatrixPanel';
import { LiveActivityAuditPanel } from './LiveActivityAuditPanel';
import { ScreenSurfacePanel } from './ScreenSurfacePanel';
import { TestingMatrixPanel } from './TestingMatrixPanel';
import './DeviceHub.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export type DeviceTab = 'devices' | 'apps' | 'permissions' | 'audit' | 'screen' | 'matrix';

export interface DeviceInfo {
  id: string;
  user_id: string;
  device_name: string;
  device_type: string;
  os_platform: string;
  os_version: string;
  architecture: string;
  hostname: string;
  ip_address: string;
  status: string;
  is_current_host: boolean;
  capabilities: string[];
  telemetry: {
    cpu_percent?: number;
    memory_percent?: number;
    disk_free_gb?: number;
    active_window?: string;
    hostname?: string;
    os_platform?: string;
    timestamp?: string;
  };
  last_heartbeat_at?: string | null;
}

export interface DiscoveredAppItem {
  id: string;
  device_id: string;
  app_name: string;
  executable_path: string;
  category: string;
  version?: string | null;
  icon_url?: string | null;
  is_running: boolean;
  process_id?: number | null;
  launch_count: number;
  last_launched_at?: string | null;
}

export interface ScreenCaptureData {
  device_id: string;
  image_url: string;
  image_base64?: string | null;
  width: number;
  height: number;
  captured_at: string;
}

export interface ActionLogItem {
  id: string;
  device_id: string;
  action_type: string;
  target: string;
  parameters: Record<string, any>;
  status: string;
  result: Record<string, any>;
  error_message?: string | null;
  created_at?: string;
}

export interface PermissionGrant {
  id: string;
  user_id: string;
  tool_id?: string | null;
  permission: string;
  policy: 'allow_automatically' | 'always_ask' | 'never_allow' | 'revoked';
  scope: 'global' | 'device' | 'app';
  device_id?: string | null;
  target_app?: string | null;
  capability?: string | null;
  expires_at?: string | null;
}

export interface VerificationRecord {
  id: string;
  device_id: string;
  evidence_type: 'window' | 'ocr' | 'dom' | 'api' | 'composite';
  verified: boolean;
  confidence: number;
  proof_hash: string;
  latency_ms: number;
  details: Record<string, any>;
  timestamp: string;
}

export interface RecoveryRecord {
  id: string;
  device_id: string;
  goal: string;
  primary_tier: 'api' | 'browser' | 'desktop';
  final_status: 'success' | 'recovered' | 'failed';
  tier_traversed: Array<'api' | 'browser' | 'desktop'>;
  error_category?: string;
  self_correction_applied?: string;
  cryptographic_proof_hash?: string;
  total_duration_ms: number;
  timestamp: string;
}

export interface WorkspaceSurfaceSession {
  session_id: string;
  device_id: string;
  target_url?: string | null;
  app_id?: string | null;
  embedding_mode: string;
  status: string;
  created_at: string;
}

export interface DeviceLiveState {
  status: string;
  active_window: string | null;
  telemetry: {
    cpu_percent?: number;
    memory_percent?: number;
    disk_free_gb?: number;
    active_window?: string;
    hostname?: string;
    os_platform?: string;
    timestamp?: string;
  };
  connected_mobile_devices: {
    adb_installed: boolean;
    attached_devices: string[];
    device_count: number;
    recommendations?: string[];
    install_command?: string | null;
  };
  browser_profiles: {
    whatsapp?: Record<string, {
      state: string;
      is_ready: boolean;
      details?: string;
    }>;
  };
  timestamp?: string;
}

export interface ConfirmationChallenge {
  challenge_id: string;
  action_type: string;
  title: string;
  summary: string;
  details?: Record<string, any>;
  risk_tier: string;
  risk_score: number;
  requires_2fa: boolean;
  status: string;
  created_at: string;
  expires_at: string;
  challenge_token?: string;
}

interface DeviceHubProps {
  accessToken: string | null;
  onBack: () => void;
  onSendToChat?: (text: string) => void;
}

export const DeviceHub: React.FC<DeviceHubProps> = ({
  accessToken,
  onBack,
  onSendToChat,
}) => {
  // Navigation & Active Device State
  const [activeTab, setActiveTab] = useState<DeviceTab>('devices');
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<DeviceInfo | null>(null);

  // Data States
  const [apps, setApps] = useState<DiscoveredAppItem[]>([]);
  const [workspaceSessions, setWorkspaceSessions] = useState<WorkspaceSurfaceSession[]>([]);
  const [activeGrants, setActiveGrants] = useState<PermissionGrant[]>([]);
  const [actionLogs, setActionLogs] = useState<ActionLogItem[]>([]);
  const [verificationRecords, setVerificationRecords] = useState<VerificationRecord[]>([]);
  const [recoveryRecords, setRecoveryRecords] = useState<RecoveryRecord[]>([]);
  const [latestScreen, setLatestScreen] = useState<ScreenCaptureData | null>(null);

  // Loading & Action States
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [loadingApps, setLoadingApps] = useState(false);
  const [scanningApps, setScanningApps] = useState(false);
  const [actingAppId, setActingAppId] = useState<string | null>(null);
  const [loadingGrants, setLoadingGrants] = useState(false);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [capturingScreen, setCapturingScreen] = useState(false);
  const [simulatingRecovery, setSimulatingRecovery] = useState(false);

  // Phase 3 Live Observability & Trust Challenges State
  const [liveState, setLiveState] = useState<DeviceLiveState | null>(null);
  const [pendingChallenges, setPendingChallenges] = useState<ConfirmationChallenge[]>([]);
  const [loadingLiveState, setLoadingLiveState] = useState(false);
  const [resolvingChallengeId, setResolvingChallengeId] = useState<string | null>(null);

  // Notification Toast
  const [notification, setNotification] = useState<{
    type: 'success' | 'error' | 'info';
    message: string;
  } | null>(null);

  const authHeaders = useMemo(() => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (accessToken) {
      h.Authorization = `Bearer ${accessToken}`;
    }
    return h;
  }, [accessToken]);

  const showNotification = (type: 'success' | 'error' | 'info', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 4500);
  };

  // 1. Fetch Fleet Devices
  const fetchDevices = useCallback(async () => {
    setLoadingDevices(true);
    try {
      // 1. Try listing registered devices
      let fetchedDevices: DeviceInfo[] = [];
      const res = await fetch(`${API_BASE}/devices`, { headers: authHeaders });
      if (res.ok) {
        fetchedDevices = await res.json();
      }

      // 2. Fetch or initialize the local host device
      const hostRes = await fetch(`${API_BASE}/devices/current`, { headers: authHeaders });
      let currentHost: DeviceInfo | null = null;
      if (hostRes.ok) {
        currentHost = await hostRes.json();
      }

      // Merge ensuring currentHost is included
      if (currentHost && !fetchedDevices.some((d) => d.id === currentHost!.id)) {
        fetchedDevices = [currentHost, ...fetchedDevices];
      }

      // Ensure at least one fallback demo device if list is completely empty
      if (fetchedDevices.length === 0) {
        const fallbackDev: DeviceInfo = {
          id: 'dev_local_primary',
          user_id: 'user_default',
          device_name: 'Primary Workstation',
          device_type: 'desktop',
          os_platform: 'windows',
          os_version: '11.0.26100',
          architecture: 'x86_64',
          hostname: 'ROXY-WORKSTATION',
          ip_address: '192.168.1.45',
          status: 'online',
          is_current_host: true,
          capabilities: ['app_discovery', 'process_control', 'screen_capture', 'input_simulation'],
          telemetry: {
            cpu_percent: 14,
            memory_percent: 41,
            disk_free_gb: 128.4,
            active_window: 'Visual Studio Code',
            hostname: 'ROXY-WORKSTATION',
            os_platform: 'windows',
            timestamp: new Date().toISOString(),
          },
          last_heartbeat_at: new Date().toISOString(),
        };
        fetchedDevices = [fallbackDev];
      }

      setDevices(fetchedDevices);

      // Preserve or set selected device
      setSelectedDevice((prev) => {
        if (prev && fetchedDevices.some((d) => d.id === prev.id)) {
          return fetchedDevices.find((d) => d.id === prev.id)!;
        }
        return fetchedDevices.find((d) => d.is_current_host) || fetchedDevices[0];
      });
    } catch (err: any) {
      showNotification('error', `Failed to load devices: ${err.message}`);
    } finally {
      setLoadingDevices(false);
    }
  }, [authHeaders]);

  // 2. Fetch Apps for Device
  const fetchApps = useCallback(
    async (deviceId: string) => {
      setLoadingApps(true);
      try {
        const res = await fetch(`${API_BASE}/devices/${deviceId}/apps`, { headers: authHeaders });
        if (res.ok) {
          const data: DiscoveredAppItem[] = await res.json();
          setApps(data);
        }
      } catch (err: any) {
        showNotification('error', `Failed to load apps: ${err.message}`);
      } finally {
        setLoadingApps(false);
      }
    },
    [authHeaders]
  );

  // 3. Fetch Workspace Surface Sessions (Phase 16)
  const fetchWorkspaceSessions = useCallback(
    async (deviceId: string) => {
      try {
        const res = await fetch(`${API_BASE}/devices/${deviceId}/embedding/sessions`, {
          headers: authHeaders,
        });
        if (res.ok) {
          const data = await res.json();
          setWorkspaceSessions(data.sessions || []);
        }
      } catch {
        // Soft fail
      }
    },
    [authHeaders]
  );

  // 4. Fetch Permissions
  const fetchPermissions = useCallback(async () => {
    setLoadingGrants(true);
    try {
      const res = await fetch(`${API_BASE}/permissions`, { headers: authHeaders });
      if (res.ok) {
        const data: PermissionGrant[] = await res.json();
        setActiveGrants(data);
      }
    } catch (err: any) {
      // Soft fail
    } finally {
      setLoadingGrants(false);
    }
  }, [authHeaders]);

  // 5. Fetch Action Logs, Verification & Recovery History
  const fetchAuditData = useCallback(
    async (deviceId: string) => {
      setLoadingAudit(true);
      try {
        // Actions
        const aRes = await fetch(`${API_BASE}/devices/${deviceId}/actions`, { headers: authHeaders });
        if (aRes.ok) {
          const aData: ActionLogItem[] = await aRes.json();
          setActionLogs(aData);
        }

        // Verification (Phase 17)
        const vRes = await fetch(`${API_BASE}/devices/${deviceId}/verification/history`, {
          headers: authHeaders,
        });
        if (vRes.ok) {
          const vData = await vRes.json();
          setVerificationRecords(vData.verifications || []);
        }

        // Recovery (Phase 18)
        const rRes = await fetch(`${API_BASE}/devices/${deviceId}/recovery/history`, {
          headers: authHeaders,
        });
        if (rRes.ok) {
          const rData = await rRes.json();
          setRecoveryRecords(rData.records || []);
        }
      } catch {
        // Soft fail
      } finally {
        setLoadingAudit(false);
      }
    },
    [authHeaders]
  );

  // 6. Fetch Live Observability State (Active Window, Mobile ADB, WhatsApp Profile)
  const fetchLiveState = useCallback(async () => {
    setLoadingLiveState(true);
    try {
      const res = await fetch(`${API_BASE}/devices/state`, { headers: authHeaders });
      if (res.ok) {
        const data: DeviceLiveState = await res.json();
        setLiveState(data);
      }
    } catch {
      // Soft fail
    } finally {
      setLoadingLiveState(false);
    }
  }, [authHeaders]);

  // 7. Fetch Pending Confirmation Challenges
  const fetchChallenges = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/trust/challenges`, { headers: authHeaders });
      if (res.ok) {
        const data: ConfirmationChallenge[] = await res.json();
        setPendingChallenges(data);
      }
    } catch {
      // Soft fail
    }
  }, [authHeaders]);

  // 8. Resolve Confirmation Challenge (Approve or Reject)
  const handleResolveChallenge = async (challenge: ConfirmationChallenge, decision: 'approved' | 'rejected') => {
    setResolvingChallengeId(challenge.challenge_id);
    try {
      const res = await fetch(`${API_BASE}/trust/challenges/${challenge.challenge_id}/resolve`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          decision,
          challenge_token: challenge.challenge_token,
          comment: `${decision.toUpperCase()} by user via DeviceHub dashboard`,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showNotification('success', `Challenge '${challenge.title}' was ${decision}.`);
      await fetchChallenges();
    } catch (err: any) {
      showNotification('error', `Failed to ${decision} challenge: ${err.message}`);
    } finally {
      setResolvingChallengeId(null);
    }
  };

  // Initial Load & Telemetry Polling
  useEffect(() => {
    fetchDevices();
    fetchPermissions();
    fetchLiveState();
    fetchChallenges();

    const pollTimer = setInterval(() => {
      fetchLiveState();
      fetchChallenges();
    }, 5000);

    return () => clearInterval(pollTimer);
  }, [fetchDevices, fetchPermissions, fetchLiveState, fetchChallenges]);

  // Load device-specific data when selectedDevice changes
  useEffect(() => {
    if (selectedDevice) {
      fetchApps(selectedDevice.id);
      fetchWorkspaceSessions(selectedDevice.id);
      fetchAuditData(selectedDevice.id);
    }
  }, [selectedDevice, fetchApps, fetchWorkspaceSessions, fetchAuditData]);

  // Action: Create Enrollment Token
  const handleCreateEnrollmentToken = async (): Promise<string | null> => {
    try {
      const res = await fetch(`${API_BASE}/devices/enrollment/token`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ label: 'Universal App Control Client', ttl_seconds: 900 }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return data.token;
    } catch (err: any) {
      showNotification('error', `Could not generate token: ${err.message}`);
      return null;
    }
  };

  // Action: Register Companion Device manually
  const handleEnrollDevice = async (deviceData: {
    device_name: string;
    device_type: string;
    os_platform: string;
    hostname: string;
    ip_address: string;
  }) => {
    try {
      const res = await fetch(`${API_BASE}/devices/register`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(deviceData),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const newDev = await res.json();
      showNotification('success', `Enrolled device '${deviceData.device_name}'`);
      await fetchDevices();
      setSelectedDevice(newDev);
    } catch (err: any) {
      showNotification('error', `Enrollment failed: ${err.message}`);
    }
  };

  // Action: Ping Device
  const handlePingDevice = async (deviceId: string) => {
    try {
      const res = await fetch(`${API_BASE}/devices/${deviceId}/telemetry`, { headers: authHeaders });
      if (res.ok) {
        showNotification('success', 'Heartbeat acknowledged by device daemon.');
        fetchDevices();
      }
    } catch {
      showNotification('error', 'Ping failed. Device may be unreachable.');
    }
  };

  // Action: Scan Apps
  const handleScanApps = async (forceRefresh: boolean = false) => {
    if (!selectedDevice) return;
    setScanningApps(true);
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/apps/scan`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ force_refresh: forceRefresh, include_system_apps: true }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      showNotification(
        'success',
        `Discovered ${data.scanned_count} apps in ${data.scan_duration_ms}ms`
      );
      await fetchApps(selectedDevice.id);
    } catch (err: any) {
      showNotification('error', `Scan failed: ${err.message}`);
    } finally {
      setScanningApps(false);
    }
  };

  // Action: Launch App
  const handleLaunchApp = async (app: DiscoveredAppItem) => {
    if (!selectedDevice) return;
    setActingAppId(app.id);
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/apps/launch`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ app_name_or_path: app.id }),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'failed') throw new Error(data.error || 'Launch failed');
      showNotification('success', `Launched ${app.app_name} (PID: ${data.process_id || 'Active'})`);
      await fetchApps(selectedDevice.id);
      fetchAuditData(selectedDevice.id);
    } catch (err: any) {
      showNotification('error', `Failed to launch ${app.app_name}: ${err.message}`);
    } finally {
      setActingAppId(null);
    }
  };

  // Action: Close App
  const handleCloseApp = async (app: DiscoveredAppItem, force: boolean = false) => {
    if (!selectedDevice) return;
    setActingAppId(app.id);
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/apps/close`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ app_name_or_pid: app.process_id || app.app_name, force }),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'failed') throw new Error(data.error || 'Close failed');
      showNotification('info', `Terminated ${app.app_name}`);
      await fetchApps(selectedDevice.id);
      fetchAuditData(selectedDevice.id);
    } catch (err: any) {
      showNotification('error', `Failed to terminate ${app.app_name}: ${err.message}`);
    } finally {
      setActingAppId(null);
    }
  };

  // Action: Focus App
  const handleFocusApp = async (app: DiscoveredAppItem) => {
    if (!selectedDevice) return;
    setActingAppId(app.id);
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/apps/focus`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ app_name: app.app_name }),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'failed') throw new Error(data.error || 'Focus failed');
      showNotification('success', `Brought ${app.app_name} to foreground`);
    } catch (err: any) {
      showNotification('error', `Focus failed: ${err.message}`);
    } finally {
      setActingAppId(null);
    }
  };

  // Action: In-Roxy Workspace Embedding (Phase 16)
  const handleCreateEmbedSession = async (appIdOrUrl: string, mode: string = 'safe_iframe') => {
    if (!selectedDevice) return;
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/embedding/sessions`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          device_id: selectedDevice.id,
          target_url: appIdOrUrl.startsWith('http') ? appIdOrUrl : undefined,
          app_id: !appIdOrUrl.startsWith('http') ? appIdOrUrl : undefined,
          embedding_mode: mode,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showNotification('success', `Workspace surface session created (${mode})`);
      fetchWorkspaceSessions(selectedDevice.id);
    } catch (err: any) {
      showNotification('error', `Embedding failed: ${err.message}`);
    }
  };

  // Action: Terminate Embed Session
  const handleTerminateEmbedSession = async (sessionId: string) => {
    if (!selectedDevice) return;
    try {
      await fetch(`${API_BASE}/devices/${selectedDevice.id}/embedding/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      showNotification('info', 'Workspace surface session closed');
      fetchWorkspaceSessions(selectedDevice.id);
    } catch {
      // Soft fail
    }
  };

  // Action: Update Target-Scoped Permission
  const handleUpdatePermission = async (
    permission: string,
    policy: 'allow_automatically' | 'always_ask' | 'never_allow',
    scope: 'global' | 'device' | 'app',
    targetApp?: string
  ) => {
    try {
      if (policy === 'never_allow') {
        // Revoke
        await fetch(`${API_BASE}/permissions/revoke`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            permission,
            scope,
            device_id: scope === 'device' ? selectedDevice?.id : undefined,
            target_app: scope === 'app' ? targetApp : undefined,
          }),
        });
        showNotification('info', `Revoked policy for '${permission}'`);
      } else {
        // Grant / update
        await fetch(`${API_BASE}/permissions/grant`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            permission,
            policy,
            scope,
            device_id: scope === 'device' ? selectedDevice?.id : undefined,
            target_app: scope === 'app' ? targetApp : undefined,
          }),
        });
        showNotification('success', `Configured policy: ${policy} for ${permission}`);
      }
      await fetchPermissions();
    } catch (err: any) {
      showNotification('error', `Permission update failed: ${err.message}`);
    }
  };

  // Action: Revoke Grant directly
  const handleRevokeGrant = async (grantId: string) => {
    try {
      await fetch(`${API_BASE}/permissions/grants/${grantId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      showNotification('info', 'Permission grant removed');
      await fetchPermissions();
    } catch (err: any) {
      showNotification('error', `Revocation failed: ${err.message}`);
    }
  };

  // Action: Capture Screen
  const handleCaptureScreen = async () => {
    if (!selectedDevice) return;
    setCapturingScreen(true);
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/screenshot`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ScreenCaptureData = await res.json();
      setLatestScreen(data);
      showNotification('success', `Captured display (${data.width} × ${data.height} px)`);
    } catch (err: any) {
      showNotification('error', `Screenshot failed: ${err.message}`);
    } finally {
      setCapturingScreen(false);
    }
  };

  // Action: Trigger Multi-Tier Recovery Fallback Simulation (Phase 18)
  const handleTriggerRecoverySimulation = async (params: {
    goal: string;
    target_app: string;
    primary_tier: 'api' | 'browser' | 'desktop';
    simulate_failure: boolean;
  }) => {
    if (!selectedDevice) return;
    setSimulatingRecovery(true);
    try {
      const res = await fetch(`${API_BASE}/devices/${selectedDevice.id}/recovery/execute`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          device_id: selectedDevice.id,
          goal: params.goal,
          target_app: params.target_app,
          primary_tier: params.primary_tier,
          enable_api_tier: true,
          enable_browser_tier: true,
          enable_desktop_tier: true,
          policy: {
            max_attempts_per_tier: 2,
            self_correction_enabled: true,
            allowed_tiers: ['api', 'browser', 'desktop'],
          },
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      showNotification(
        'success',
        `Recovery executed successfully: Status [${result.final_status.toUpperCase()}] via ${result.winning_tier?.toUpperCase() || 'DESKTOP'} ROUTE`
      );

      // Refresh audit data to show the new recovery trajectory
      await fetchAuditData(selectedDevice.id);
    } catch (err: any) {
      showNotification('error', `Recovery simulation failed: ${err.message}`);
    } finally {
      setSimulatingRecovery(false);
    }
  };

  return (
    <div className="device-hub">
      {/* 1. Header Toolbar */}
      <div className="device-hub__header">
        <div className="device-hub__header-left">
          <button
            type="button"
            className="device-hub__back-btn"
            onClick={onBack}
            aria-label="Back to Chat"
            title="Back to Chat"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="device-hub__title-wrap">
            <h1 className="device-hub__title">
              <Monitor size={22} className="device-hub__title-icon" />
              <span>Universal App Control Hub</span>
            </h1>
            <p className="device-hub__subtitle">
              Connected devices fleet, cross-platform apps, target-scoped permissions & live
              verification audit UX
            </p>
          </div>
        </div>

        <div className="device-hub__header-actions">
          {selectedDevice && (
            <div className="device-hub__active-pill">
              <span className="device-hub__active-pill-dot" />
              <span className="device-hub__active-pill-text">
                Target: {selectedDevice.device_name}
              </span>
            </div>
          )}

          <button
            type="button"
            className="device-hub__action-btn"
            onClick={() => {
              fetchDevices();
              fetchLiveState();
              fetchChallenges();
              if (selectedDevice) {
                fetchApps(selectedDevice.id);
                fetchAuditData(selectedDevice.id);
              }
            }}
            disabled={loadingDevices || loadingApps || loadingLiveState}
            title="Refresh All System Data"
          >
            <RefreshCw size={14} className={loadingDevices || loadingLiveState ? 'spin' : ''} />
            <span>Refresh All</span>
          </button>

          {onSendToChat && (
            <button
              type="button"
              className="device-hub__action-btn device-hub__action-btn--primary"
              onClick={() =>
                onSendToChat(
                  `Inspect connected devices and list all running applications on ${
                    selectedDevice?.device_name || 'host'
                  }`
                )
              }
              title="Instruct ROXY via Natural Language"
            >
              <Sparkles size={14} />
              <span>Ask ROXY</span>
            </button>
          )}
        </div>
      </div>

      {/* Notification Toast */}
      {notification && (
        <div className={`device-hub__toast device-hub__toast--${notification.type}`}>
          {notification.type === 'success' && <CheckCircle2 size={16} />}
          {notification.type === 'error' && <XCircle size={16} />}
          {notification.type === 'info' && <AlertCircle size={16} />}
          <span>{notification.message}</span>
        </div>
      )}

      {/* P3 Live Observability Status Bar */}
      <div className="device-hub__live-status-bar" role="region" aria-label="System Observability">
        <div className="device-hub__live-status-item">
          <Monitor size={15} style={{ color: '#38bdf8' }} />
          <span className="device-hub__live-status-label">Active Window:</span>
          <span className="device-hub__live-status-val">
            {liveState?.active_window || selectedDevice?.telemetry?.active_window || 'ROXY Desktop Studio'}
          </span>
        </div>

        <div className="device-hub__status-divider" />

        <div className="device-hub__live-status-item">
          <Smartphone size={15} style={{ color: liveState?.connected_mobile_devices?.adb_installed ? '#34d399' : '#fbbf24' }} />
          <span className="device-hub__live-status-label">Android ADB:</span>
          {liveState?.connected_mobile_devices?.adb_installed ? (
            <span className="device-hub__status-tag device-hub__status-tag--success">
              Ready ({liveState.connected_mobile_devices.device_count} device{liveState.connected_mobile_devices.device_count === 1 ? '' : 's'})
            </span>
          ) : (
            <span
              className="device-hub__status-tag device-hub__status-tag--warning"
              title={liveState?.connected_mobile_devices?.recommendations?.[0] || 'Run winget install Google.PlatformTools'}
            >
              ADB Not Installed
            </span>
          )}
        </div>

        <div className="device-hub__status-divider" />

        <div className="device-hub__live-status-item">
          <Globe size={15} style={{ color: '#a78bfa' }} />
          <span className="device-hub__live-status-label">WhatsApp Session:</span>
          {(() => {
            const waWeb = liveState?.browser_profiles?.whatsapp?.web;
            const waDesktop = liveState?.browser_profiles?.whatsapp?.desktop;
            const isReady = waWeb?.is_ready || waDesktop?.is_ready;
            const stateStr = waWeb?.state || waDesktop?.state || 'UNCONFIGURED';
            return (
              <span className={`device-hub__status-tag ${isReady ? 'device-hub__status-tag--success' : 'device-hub__status-tag--info'}`}>
                {isReady ? 'Authenticated' : stateStr}
              </span>
            );
          })()}
        </div>

        {pendingChallenges.length > 0 && (
          <>
            <div className="device-hub__status-divider" />
            <div className="device-hub__live-status-item">
              <Shield size={15} style={{ color: '#ef4444' }} />
              <span className="device-hub__status-tag device-hub__status-tag--warning">
                {pendingChallenges.length} Pending Approval{pendingChallenges.length === 1 ? '' : 's'}
              </span>
            </div>
          </>
        )}
      </div>

      {/* P3 Pending Confirmation Challenges Banner */}
      {pendingChallenges.length > 0 && (
        <div className="device-hub__challenge-banner" role="alert">
          <div className="device-hub__challenge-info">
            <AlertCircle size={20} style={{ color: '#ef4444', flexShrink: 0 }} />
            <div className="device-hub__challenge-text">
              <span className="device-hub__challenge-title">
                Action Approval Required ({pendingChallenges[0].risk_tier.toUpperCase()} RISK): {pendingChallenges[0].title}
              </span>
              <span className="device-hub__challenge-desc">
                {pendingChallenges[0].summary}
              </span>
            </div>
          </div>
          <div className="device-hub__challenge-actions">
            <button
              type="button"
              className="device-hub__btn-reject"
              onClick={() => handleResolveChallenge(pendingChallenges[0], 'rejected')}
              disabled={resolvingChallengeId === pendingChallenges[0].challenge_id}
            >
              <X size={13} />
              <span>Reject</span>
            </button>
            <button
              type="button"
              className="device-hub__btn-approve"
              onClick={() => handleResolveChallenge(pendingChallenges[0], 'approved')}
              disabled={resolvingChallengeId === pendingChallenges[0].challenge_id}
            >
              <Check size={13} />
              <span>Approve & Execute</span>
            </button>
          </div>
        </div>
      )}

      {/* 2. Top-Level Tab Navigation */}
      <div className="device-hub__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'devices'}
          className={`device-hub__tab ${activeTab === 'devices' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('devices')}
        >
          <Radio size={16} />
          <span>Connected Devices</span>
          <span className="device-hub__tab-count">{devices.length}</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'apps'}
          className={`device-hub__tab ${activeTab === 'apps' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('apps')}
        >
          <Layers size={16} />
          <span>Applications & Surfaces</span>
          <span className="device-hub__tab-count">{apps.length}</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'permissions'}
          className={`device-hub__tab ${
            activeTab === 'permissions' ? 'device-hub__tab--active' : ''
          }`}
          onClick={() => setActiveTab('permissions')}
        >
          <Shield size={16} />
          <span>Permissions Matrix</span>
          <span className="device-hub__tab-count">{activeGrants.length}</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'audit'}
          className={`device-hub__tab ${activeTab === 'audit' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          <Activity size={16} />
          <span>Live Activity Audit UX</span>
          <span className="device-hub__tab-count">
            {actionLogs.length + verificationRecords.length + recoveryRecords.length}
          </span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'screen'}
          className={`device-hub__tab ${activeTab === 'screen' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('screen')}
        >
          <Camera size={16} />
          <span>Display & Screen</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'matrix'}
          className={`device-hub__tab ${activeTab === 'matrix' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('matrix')}
        >
          <ShieldCheck size={16} />
          <span>Testing Matrix</span>
        </button>
      </div>

      {/* 3. Tab Contents */}
      <div className="device-hub__content-pane">
        {activeTab === 'devices' && (
          <DeviceFleetPanel
            devices={devices}
            selectedDevice={selectedDevice}
            onSelectDevice={(dev) => setSelectedDevice(dev)}
            onRefreshDevices={fetchDevices}
            onEnrollDevice={handleEnrollDevice}
            onCreateEnrollmentToken={handleCreateEnrollmentToken}
            onPingDevice={handlePingDevice}
            loading={loadingDevices}
          />
        )}

        {activeTab === 'apps' && (
          <ApplicationsPanel
            device={selectedDevice}
            apps={apps}
            workspaceSessions={workspaceSessions}
            loadingApps={loadingApps}
            scanningApps={scanningApps}
            actingAppId={actingAppId}
            onScanApps={handleScanApps}
            onLaunchApp={handleLaunchApp}
            onCloseApp={handleCloseApp}
            onFocusApp={handleFocusApp}
            onCreateEmbedSession={handleCreateEmbedSession}
            onTerminateEmbedSession={handleTerminateEmbedSession}
            onTriggerResilientExec={() => {
              setActiveTab('audit');
            }}
          />
        )}

        {activeTab === 'permissions' && (
          <PermissionsMatrixPanel
            device={selectedDevice}
            activeGrants={activeGrants}
            loadingGrants={loadingGrants}
            onUpdatePermission={handleUpdatePermission}
            onRevokeGrant={handleRevokeGrant}
            onRefreshGrants={fetchPermissions}
          />
        )}

        {activeTab === 'audit' && (
          <LiveActivityAuditPanel
            device={selectedDevice}
            actionLogs={actionLogs}
            verificationRecords={verificationRecords}
            recoveryRecords={recoveryRecords}
            loading={loadingAudit}
            onRefresh={() => (selectedDevice ? fetchAuditData(selectedDevice.id) : Promise.resolve())}
            onTriggerRecoverySimulation={handleTriggerRecoverySimulation}
            simulatingRecovery={simulatingRecovery}
          />
        )}

        {activeTab === 'screen' && (
          <ScreenSurfacePanel
            device={selectedDevice}
            latestScreen={latestScreen}
            capturingScreen={capturingScreen}
            onCaptureScreen={handleCaptureScreen}
            onShowNotification={showNotification}
          />
        )}

        {activeTab === 'matrix' && (
          <TestingMatrixPanel
            authHeaders={authHeaders}
            apiBase={API_BASE}
          />
        )}
      </div>
    </div>
  );
};

export default DeviceHub;
