import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Monitor,
  Cpu,
  HardDrive,
  Activity,
  Play,
  Square,
  Camera,
  RefreshCw,
  Search,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Terminal,
  Download,
  Copy,
  Sparkles,
  Layers,
  Maximize2,
} from 'lucide-react';
import './DeviceHub.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export type DeviceTab = 'apps' | 'screen' | 'logs';

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
  const [activeTab, setActiveTab] = useState<DeviceTab>('apps');
  const [currentDevice, setCurrentDevice] = useState<DeviceInfo | null>(null);
  const [apps, setApps] = useState<DiscoveredAppItem[]>([]);
  const [actionLogs, setActionLogs] = useState<ActionLogItem[]>([]);
  const [latestScreen, setLatestScreen] = useState<ScreenCaptureData | null>(null);

  const [loadingDevice, setLoadingDevice] = useState(false);
  const [loadingApps, setLoadingApps] = useState(false);
  const [scanningApps, setScanningApps] = useState(false);
  const [capturingScreen, setCapturingScreen] = useState(false);
  const [actingAppId, setActingAppId] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [runningOnly, setRunningOnly] = useState(false);
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

  // 1. Fetch Current Host Device
  const fetchCurrentDevice = useCallback(async () => {
    setLoadingDevice(true);
    try {
      const res = await fetch(`${API_BASE}/devices/current`, { headers: authHeaders });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: DeviceInfo = await res.json();
      setCurrentDevice(data);
      return data;
    } catch (err: any) {
      showNotification('error', `Failed to detect host device: ${err.message}`);
      return null;
    } finally {
      setLoadingDevice(false);
    }
  }, [authHeaders]);

  // 2. Fetch Apps for Device
  const fetchApps = useCallback(async (deviceId: string) => {
    setLoadingApps(true);
    try {
      const res = await fetch(`${API_BASE}/devices/${deviceId}/apps`, { headers: authHeaders });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: DiscoveredAppItem[] = await res.json();
      setApps(data);
    } catch (err: any) {
      showNotification('error', `Failed to load apps: ${err.message}`);
    } finally {
      setLoadingApps(false);
    }
  }, [authHeaders]);

  // 3. Scan System Apps
  const handleScanApps = async () => {
    if (!currentDevice) return;
    setScanningApps(true);
    try {
      const res = await fetch(`${API_BASE}/devices/${currentDevice.id}/apps/scan`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: DiscoveredAppItem[] = await res.json();
      setApps(data);
      showNotification('success', `Discovered ${data.length} applications on host.`);
    } catch (err: any) {
      showNotification('error', `App scan failed: ${err.message}`);
    } finally {
      setScanningApps(false);
    }
  };

  // 4. Launch Application
  const handleLaunchApp = async (app: DiscoveredAppItem) => {
    if (!currentDevice) return;
    setActingAppId(app.id);
    try {
      const res = await fetch(`${API_BASE}/devices/${currentDevice.id}/apps/launch`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ app_name_or_path: app.id }),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'failed') {
        throw new Error(data.error || 'Launch failed');
      }
      showNotification('success', `Launched ${app.app_name}${data.process_id ? ` (PID: ${data.process_id})` : ''}`);
      // Refresh apps to reflect running state
      await fetchApps(currentDevice.id);
    } catch (err: any) {
      showNotification('error', `Failed to launch ${app.app_name}: ${err.message}`);
    } finally {
      setActingAppId(null);
    }
  };

  // 5. Close/Terminate Application
  const handleCloseApp = async (app: DiscoveredAppItem, force: boolean = false) => {
    if (!currentDevice) return;
    setActingAppId(app.id);
    try {
      const res = await fetch(`${API_BASE}/devices/${currentDevice.id}/apps/close`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          app_name_or_pid: app.process_id || app.app_name,
          force,
        }),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'failed') {
        throw new Error(data.error || 'Close failed');
      }
      showNotification('info', `Closed ${app.app_name}`);
      await fetchApps(currentDevice.id);
    } catch (err: any) {
      showNotification('error', `Failed to close ${app.app_name}: ${err.message}`);
    } finally {
      setActingAppId(null);
    }
  };

  // 6. Focus Application Window
  const handleFocusApp = async (app: DiscoveredAppItem) => {
    if (!currentDevice) return;
    setActingAppId(app.id);
    try {
      const res = await fetch(`${API_BASE}/devices/${currentDevice.id}/apps/focus`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ app_name: app.app_name }),
      });
      const data = await res.json();
      if (!res.ok || data.status === 'failed') {
        throw new Error(data.error || 'Focus failed');
      }
      showNotification('success', `Brought ${app.app_name} to foreground`);
    } catch (err: any) {
      showNotification('error', `Could not focus ${app.app_name}: ${err.message}`);
    } finally {
      setActingAppId(null);
    }
  };

  // 7. Capture Screen
  const handleCaptureScreen = async () => {
    if (!currentDevice) return;
    setCapturingScreen(true);
    try {
      const res = await fetch(`${API_BASE}/devices/${currentDevice.id}/screenshot`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ScreenCaptureData = await res.json();
      setLatestScreen(data);
      showNotification('success', `Captured display screenshot (${data.width}x${data.height})`);
    } catch (err: any) {
      showNotification('error', `Screenshot failed: ${err.message}`);
    } finally {
      setCapturingScreen(false);
    }
  };

  // 8. Fetch Action Logs
  const fetchActionLogs = useCallback(async (deviceId: string) => {
    try {
      const res = await fetch(`${API_BASE}/devices/${deviceId}/actions`, { headers: authHeaders });
      if (!res.ok) return;
      const data: ActionLogItem[] = await res.json();
      setActionLogs(data);
    } catch {
      // Ignore
    }
  }, [authHeaders]);

  // Initial Load
  useEffect(() => {
    fetchCurrentDevice().then((dev) => {
      if (dev) {
        fetchApps(dev.id);
        fetchActionLogs(dev.id);
      }
    });
  }, [fetchCurrentDevice, fetchApps, fetchActionLogs]);

  // Tab switch auto-refresh
  useEffect(() => {
    if (activeTab === 'logs' && currentDevice) {
      fetchActionLogs(currentDevice.id);
    }
  }, [activeTab, currentDevice, fetchActionLogs]);

  // Filtered Apps
  const filteredApps = useMemo(() => {
    return apps.filter((app) => {
      const matchesSearch =
        searchQuery === '' ||
        app.app_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        app.executable_path.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCat =
        selectedCategory === 'all' ||
        app.category.toLowerCase() === selectedCategory.toLowerCase();

      const matchesRunning = !runningOnly || app.is_running;

      return matchesSearch && matchesCat && matchesRunning;
    });
  }, [apps, searchQuery, selectedCategory, runningOnly]);

  const categories = ['all', 'browser', 'development', 'productivity', 'media', 'utilities', 'system'];

  const telemetry = currentDevice?.telemetry || {};

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
              <span>Device & App Control</span>
            </h1>
            <p className="device-hub__subtitle">
              Native host discovery, local process lifecycle management & visual OS automation
            </p>
          </div>
        </div>

        <div className="device-hub__header-actions">
          <button
            type="button"
            className="device-hub__action-btn"
            onClick={() => {
              if (currentDevice) {
                fetchCurrentDevice();
                fetchApps(currentDevice.id);
              }
            }}
            disabled={loadingDevice || loadingApps}
            title="Refresh Host Status & Apps"
          >
            <RefreshCw size={15} className={loadingDevice ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
          {onSendToChat && (
            <button
              type="button"
              className="device-hub__action-btn device-hub__action-btn--primary"
              onClick={() => onSendToChat('Scan my device and tell me what apps are installed and running')}
              title="Ask ROXY to inspect device"
            >
              <Sparkles size={15} />
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

      {/* 2. Host Overview Banner */}
      <div className="device-hub__device-card">
        <div className="device-hub__device-info">
          <div className="device-hub__device-avatar">
            <Monitor size={26} />
            <span className={`device-hub__status-dot device-hub__status-dot--${currentDevice?.status || 'online'}`} />
          </div>
          <div className="device-hub__device-meta">
            <div className="device-hub__device-title-row">
              <span className="device-hub__device-name">
                {currentDevice?.device_name || 'Local Host Machine'}
              </span>
              <span className="device-hub__badge device-hub__badge--host">Primary Host</span>
              <span className="device-hub__badge device-hub__badge--os">
                {currentDevice?.os_platform.toUpperCase()} ({currentDevice?.architecture})
              </span>
            </div>
            <div className="device-hub__device-details-row">
              <span>IP: {currentDevice?.ip_address || '127.0.0.1'}</span>
              <span>•</span>
              <span>Host: {currentDevice?.hostname}</span>
              <span>•</span>
              <span>Capabilities: {currentDevice?.capabilities?.join(', ')}</span>
            </div>
          </div>
        </div>

        {/* Real-time Telemetry Widgets */}
        <div className="device-hub__telemetry-grid">
          <div className="device-hub__telemetry-item">
            <div className="device-hub__telemetry-label">
              <Cpu size={14} />
              <span>CPU Usage</span>
            </div>
            <div className="device-hub__telemetry-value">
              {telemetry.cpu_percent !== undefined ? `${telemetry.cpu_percent}%` : '12%'}
            </div>
            <div className="device-hub__progress-bar">
              <div
                className="device-hub__progress-fill device-hub__progress-fill--cpu"
                style={{ width: `${Math.min(100, telemetry.cpu_percent || 12)}%` }}
              />
            </div>
          </div>

          <div className="device-hub__telemetry-item">
            <div className="device-hub__telemetry-label">
              <Activity size={14} />
              <span>Memory (RAM)</span>
            </div>
            <div className="device-hub__telemetry-value">
              {telemetry.memory_percent !== undefined ? `${telemetry.memory_percent}%` : '42%'}
            </div>
            <div className="device-hub__progress-bar">
              <div
                className="device-hub__progress-fill device-hub__progress-fill--ram"
                style={{ width: `${Math.min(100, telemetry.memory_percent || 42)}%` }}
              />
            </div>
          </div>

          <div className="device-hub__telemetry-item">
            <div className="device-hub__telemetry-label">
              <HardDrive size={14} />
              <span>Free Storage</span>
            </div>
            <div className="device-hub__telemetry-value">
              {telemetry.disk_free_gb !== undefined ? `${telemetry.disk_free_gb} GB` : '48.5 GB'}
            </div>
            <span className="device-hub__telemetry-sub">System Drive</span>
          </div>
        </div>
      </div>

      {/* 3. Navigation Tabs */}
      <div className="device-hub__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'apps'}
          className={`device-hub__tab ${activeTab === 'apps' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('apps')}
        >
          <Layers size={16} />
          <span>Discovered Applications</span>
          <span className="device-hub__tab-count">{apps.length}</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'screen'}
          className={`device-hub__tab ${activeTab === 'screen' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('screen')}
        >
          <Camera size={16} />
          <span>Screen Capture</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'logs'}
          className={`device-hub__tab ${activeTab === 'logs' ? 'device-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('logs')}
        >
          <Terminal size={16} />
          <span>Action Logs</span>
          <span className="device-hub__tab-count">{actionLogs.length}</span>
        </button>
      </div>

      {/* 4. Tab Content: Discovered Applications */}
      {activeTab === 'apps' && (
        <div className="device-hub__pane">
          {/* Controls Bar */}
          <div className="device-hub__controls-bar">
            <div className="device-hub__search-box">
              <Search size={15} className="device-hub__search-icon" />
              <input
                type="text"
                className="device-hub__search-input"
                placeholder="Search installed apps or commands..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <div className="device-hub__filter-group">
              <label className="device-hub__toggle-label">
                <input
                  type="checkbox"
                  checked={runningOnly}
                  onChange={(e) => setRunningOnly(e.target.checked)}
                />
                <span>Running Only</span>
              </label>

              <button
                type="button"
                className="device-hub__scan-btn"
                onClick={handleScanApps}
                disabled={scanningApps}
              >
                <RefreshCw size={14} className={scanningApps ? 'spin' : ''} />
                <span>{scanningApps ? 'Scanning OS...' : 'Scan Host Apps'}</span>
              </button>
            </div>
          </div>

          {/* Category Chips */}
          <div className="device-hub__categories">
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                className={`device-hub__cat-chip ${selectedCategory === cat ? 'device-hub__cat-chip--active' : ''}`}
                onClick={() => setSelectedCategory(cat)}
              >
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
              </button>
            ))}
          </div>

          {/* Applications Grid */}
          {loadingApps ? (
            <div className="device-hub__loading-box">
              <RefreshCw size={24} className="spin" />
              <span>Scanning applications and process table...</span>
            </div>
          ) : filteredApps.length === 0 ? (
            <div className="device-hub__empty-box">
              <Layers size={36} />
              <h3>No Applications Found</h3>
              <p>Try clearing your search query or click "Scan Host Apps" to discover installed programs.</p>
              <button type="button" className="device-hub__scan-btn" onClick={handleScanApps}>
                Scan Host Apps Now
              </button>
            </div>
          ) : (
            <div className="device-hub__apps-grid">
              {filteredApps.map((app) => (
                <div
                  key={app.id}
                  className={`device-hub__app-card ${app.is_running ? 'device-hub__app-card--running' : ''}`}
                >
                  <div className="device-hub__app-header">
                    <div className="device-hub__app-icon-wrap">
                      {app.icon_url ? (
                        <img src={app.icon_url} alt={app.app_name} className="device-hub__app-icon-img" />
                      ) : (
                        <Terminal size={20} className="device-hub__app-fallback-icon" />
                      )}
                    </div>
                    <div className="device-hub__app-title-area">
                      <div className="device-hub__app-title-row">
                        <span className="device-hub__app-name">{app.app_name}</span>
                        {app.is_running && (
                          <span className="device-hub__badge device-hub__badge--running">Running</span>
                        )}
                      </div>
                      <span className="device-hub__badge device-hub__badge--cat">{app.category}</span>
                    </div>
                  </div>

                  <div className="device-hub__app-body">
                    <p className="device-hub__app-path" title={app.executable_path}>
                      {app.executable_path}
                    </p>
                    <div className="device-hub__app-stats">
                      <span>Launches: {app.launch_count}</span>
                      {app.process_id && <span>PID: {app.process_id}</span>}
                    </div>
                  </div>

                  <div className="device-hub__app-footer">
                    {app.is_running ? (
                      <>
                        <button
                          type="button"
                          className="device-hub__btn device-hub__btn--focus"
                          onClick={() => handleFocusApp(app)}
                          disabled={actingAppId === app.id}
                          title="Bring to foreground"
                        >
                          <Maximize2 size={13} />
                          <span>Focus</span>
                        </button>
                        <button
                          type="button"
                          className="device-hub__btn device-hub__btn--terminate"
                          onClick={() => handleCloseApp(app, false)}
                          disabled={actingAppId === app.id}
                          title="Terminate application process"
                        >
                          <Square size={13} />
                          <span>Close</span>
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="device-hub__btn device-hub__btn--launch"
                        onClick={() => handleLaunchApp(app)}
                        disabled={actingAppId === app.id}
                        title="Launch application on host"
                      >
                        <Play size={13} />
                        <span>Launch</span>
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 5. Tab Content: Screen Capture */}
      {activeTab === 'screen' && (
        <div className="device-hub__pane device-hub__screen-pane">
          <div className="device-hub__screen-toolbar">
            <div className="device-hub__screen-toolbar-left">
              <h2>Desktop Screen Grabber</h2>
              <p>Capture real-time snapshots of your desktop for visual AI verification and automation.</p>
            </div>
            <button
              type="button"
              className="device-hub__action-btn device-hub__action-btn--primary"
              onClick={handleCaptureScreen}
              disabled={capturingScreen}
            >
              <Camera size={15} className={capturingScreen ? 'spin' : ''} />
              <span>{capturingScreen ? 'Capturing...' : 'Capture Screenshot'}</span>
            </button>
          </div>

          <div className="device-hub__screen-viewer">
            {latestScreen ? (
              <div className="device-hub__screenshot-container">
                <div className="device-hub__screenshot-meta">
                  <span>Resolution: {latestScreen.width} × {latestScreen.height}</span>
                  <span>•</span>
                  <span>Captured: {new Date(latestScreen.captured_at).toLocaleTimeString()}</span>
                  <div className="device-hub__screenshot-actions">
                    <a
                      href={latestScreen.image_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="device-hub__icon-btn"
                      title="Open full image"
                    >
                      <Download size={14} />
                    </a>
                    <button
                      type="button"
                      className="device-hub__icon-btn"
                      onClick={() => {
                        navigator.clipboard.writeText(window.location.origin + latestScreen.image_url);
                        showNotification('info', 'Image URL copied to clipboard');
                      }}
                      title="Copy URL"
                    >
                      <Copy size={14} />
                    </button>
                  </div>
                </div>
                <div className="device-hub__screenshot-preview-wrap">
                  <img
                    src={latestScreen.image_url}
                    alt="Desktop Screen Capture"
                    className="device-hub__screenshot-img"
                  />
                </div>
              </div>
            ) : (
              <div className="device-hub__screen-empty">
                <Camera size={48} />
                <h3>No Recent Screenshot</h3>
                <p>Click "Capture Screenshot" above to grab a live view of your primary display.</p>
                <button
                  type="button"
                  className="device-hub__scan-btn"
                  onClick={handleCaptureScreen}
                  disabled={capturingScreen}
                >
                  Capture Now
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 6. Tab Content: Action Audit Logs */}
      {activeTab === 'logs' && (
        <div className="device-hub__pane">
          <div className="device-hub__logs-header">
            <h2>Device Operation Audit Log</h2>
            <button
              type="button"
              className="device-hub__action-btn"
              onClick={() => currentDevice && fetchActionLogs(currentDevice.id)}
            >
              <RefreshCw size={13} />
              <span>Refresh Logs</span>
            </button>
          </div>

          {actionLogs.length === 0 ? (
            <div className="device-hub__empty-box">
              <Terminal size={36} />
              <h3>No Actions Recorded Yet</h3>
              <p>Actions performed via the UI or by ROXY AI Agent will appear here with full execution audit trails.</p>
            </div>
          ) : (
            <div className="device-hub__table-wrap">
              <table className="device-hub__table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Status</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {actionLogs.map((log) => (
                    <tr key={log.id}>
                      <td className="device-hub__table-time">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : 'Just now'}
                      </td>
                      <td>
                        <span className="device-hub__badge device-hub__badge--action">
                          {log.action_type.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td className="device-hub__table-target">
                        <code>{log.target}</code>
                      </td>
                      <td>
                        <span
                          className={`device-hub__badge device-hub__badge--${
                            log.status === 'success' ? 'success' : 'error'
                          }`}
                        >
                          {log.status}
                        </span>
                      </td>
                      <td className="device-hub__table-details">
                        {log.error_message ? (
                          <span className="device-hub__text-danger">{log.error_message}</span>
                        ) : log.result?.pid ? (
                          <span>PID: {log.result.pid}</span>
                        ) : (
                          <span>Executed OK</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DeviceHub;
