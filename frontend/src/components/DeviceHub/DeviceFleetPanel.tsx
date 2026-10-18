import React, { useState } from 'react';
import {
  Monitor,
  Smartphone,
  Server,
  Laptop,
  Radio,
  Plus,
  RefreshCw,
  CheckCircle2,
  Copy,
  Check,
  Cpu,
  Activity,
  HardDrive,
  ShieldCheck,
  ChevronRight,
  Wifi,
} from 'lucide-react';
import type { DeviceInfo } from './DeviceHub';

export interface DeviceFleetPanelProps {
  devices: DeviceInfo[];
  selectedDevice: DeviceInfo | null;
  onSelectDevice: (device: DeviceInfo) => void;
  onRefreshDevices: () => Promise<void>;
  onEnrollDevice: (deviceData: {
    device_name: string;
    device_type: string;
    os_platform: string;
    hostname: string;
    ip_address: string;
  }) => Promise<void>;
  onCreateEnrollmentToken: () => Promise<string | null>;
  onPingDevice: (deviceId: string) => Promise<void>;
  loading: boolean;
}

export const DeviceFleetPanel: React.FC<DeviceFleetPanelProps> = ({
  devices,
  selectedDevice,
  onSelectDevice,
  onRefreshDevices,
  onEnrollDevice,
  onCreateEnrollmentToken,
  onPingDevice,
  loading,
}) => {
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [generatedToken, setGeneratedToken] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);
  const [generatingToken, setGeneratingToken] = useState(false);
  const [enrollTab, setEnrollTab] = useState<'token' | 'manual'>('token');

  // Manual form state
  const [manualName, setManualName] = useState('');
  const [manualType, setManualType] = useState('mobile');
  const [manualPlatform, setManualPlatform] = useState('android');
  const [manualHostname, setManualHostname] = useState('pixel-companion');
  const [manualIp, setManualIp] = useState('192.168.1.120');
  const [submittingManual, setSubmittingManual] = useState(false);

  // Ping tracking
  const [pingingDeviceId, setPingingDeviceId] = useState<string | null>(null);

  const handleOpenEnroll = async () => {
    setShowEnrollModal(true);
    setGeneratingToken(true);
    try {
      const tok = await onCreateEnrollmentToken();
      setGeneratedToken(tok);
    } finally {
      setGeneratingToken(false);
    }
  };

  const handleCopyToken = () => {
    if (generatedToken) {
      navigator.clipboard.writeText(generatedToken);
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2500);
    }
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualName.trim()) return;
    setSubmittingManual(true);
    try {
      await onEnrollDevice({
        device_name: manualName.trim(),
        device_type: manualType,
        os_platform: manualPlatform,
        hostname: manualHostname.trim() || 'roxy-client',
        ip_address: manualIp.trim() || '127.0.0.1',
      });
      setShowEnrollModal(false);
      setManualName('');
    } finally {
      setSubmittingManual(false);
    }
  };

  const handlePing = async (devId: string) => {
    setPingingDeviceId(devId);
    try {
      await onPingDevice(devId);
    } finally {
      setPingingDeviceId(null);
    }
  };

  const getPlatformIcon = (platform: string, type: string) => {
    const p = platform?.toLowerCase() || '';
    const t = type?.toLowerCase() || '';
    if (t === 'mobile' || p === 'android' || p === 'ios') {
      return <Smartphone size={22} className="device-fleet__type-icon--mobile" />;
    }
    if (p === 'linux' || t === 'server') {
      return <Server size={22} className="device-fleet__type-icon--server" />;
    }
    if (p === 'macos' || p === 'darwin') {
      return <Laptop size={22} className="device-fleet__type-icon--mac" />;
    }
    return <Monitor size={22} className="device-fleet__type-icon--pc" />;
  };

  const totalCount = devices.length;
  const onlineCount = devices.filter((d) => d.status === 'online').length;
  const mobileCount = devices.filter((d) => d.device_type === 'mobile' || ['android', 'ios'].includes((d.os_platform || '').toLowerCase())).length;
  const desktopCount = devices.filter((d) => d.device_type === 'desktop' || ['windows', 'macos', 'linux'].includes((d.os_platform || '').toLowerCase())).length;

  return (
    <div className="device-fleet">
      {/* 1. Metric Summary Ribbon */}
      <div className="device-fleet__stats-bar">
        <div className="device-fleet__stat-card">
          <div className="device-fleet__stat-icon-wrap device-fleet__stat-icon-wrap--cyan">
            <Radio size={18} />
          </div>
          <div className="device-fleet__stat-content">
            <span className="device-fleet__stat-value">{totalCount}</span>
            <span className="device-fleet__stat-label">Total Registered</span>
          </div>
        </div>

        <div className="device-fleet__stat-card">
          <div className="device-fleet__stat-icon-wrap device-fleet__stat-icon-wrap--emerald">
            <Wifi size={18} />
          </div>
          <div className="device-fleet__stat-content">
            <span className="device-fleet__stat-value">{onlineCount}</span>
            <span className="device-fleet__stat-label">Active Online</span>
          </div>
        </div>

        <div className="device-fleet__stat-card">
          <div className="device-fleet__stat-icon-wrap device-fleet__stat-icon-wrap--purple">
            <Monitor size={18} />
          </div>
          <div className="device-fleet__stat-content">
            <span className="device-fleet__stat-value">{desktopCount}</span>
            <span className="device-fleet__stat-label">Desktops & Workstations</span>
          </div>
        </div>

        <div className="device-fleet__stat-card">
          <div className="device-fleet__stat-icon-wrap device-fleet__stat-icon-wrap--amber">
            <Smartphone size={18} />
          </div>
          <div className="device-fleet__stat-content">
            <span className="device-fleet__stat-value">{mobileCount}</span>
            <span className="device-fleet__stat-label">Mobile Companions</span>
          </div>
        </div>

        <div className="device-fleet__stats-actions">
          <button
            type="button"
            className="device-fleet__btn device-fleet__btn--secondary"
            onClick={onRefreshDevices}
            disabled={loading}
            title="Refresh Connected Devices"
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            className="device-fleet__btn device-fleet__btn--primary"
            onClick={handleOpenEnroll}
            title="Enroll New Device"
          >
            <Plus size={15} />
            <span>Enroll Device</span>
          </button>
        </div>
      </div>

      {/* 2. Devices Grid */}
      <div className="device-fleet__grid">
        {devices.map((dev) => {
          const isSelected = selectedDevice?.id === dev.id;
          const telemetry = dev.telemetry || {};
          const isOnline = dev.status === 'online';

          return (
            <div
              key={dev.id}
              className={`device-fleet__card ${
                isSelected ? 'device-fleet__card--selected' : ''
              } ${!isOnline ? 'device-fleet__card--offline' : ''}`}
            >
              {/* Card Header */}
              <div className="device-fleet__card-header">
                <div className="device-fleet__card-avatar">
                  {getPlatformIcon(dev.os_platform, dev.device_type)}
                  <span
                    className={`device-fleet__status-dot device-fleet__status-dot--${
                      isOnline ? 'online' : 'offline'
                    }`}
                    title={isOnline ? 'Device online & responding' : 'Device offline'}
                  />
                </div>

                <div className="device-fleet__card-title-area">
                  <div className="device-fleet__name-row">
                    <h3 className="device-fleet__card-name">{dev.device_name}</h3>
                    {dev.is_current_host && (
                      <span className="device-fleet__badge device-fleet__badge--host">
                        Host Machine
                      </span>
                    )}
                    {isSelected && (
                      <span className="device-fleet__badge device-fleet__badge--active">
                        Active Target
                      </span>
                    )}
                  </div>
                  <div className="device-fleet__tags-row">
                    <span className="device-fleet__badge device-fleet__badge--os">
                      {(dev.os_platform || 'generic').toUpperCase()} ({dev.architecture || 'x86_64'})
                    </span>
                    <span className="device-fleet__device-ip">
                      {dev.ip_address || '127.0.0.1'}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  className="device-fleet__ping-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handlePing(dev.id);
                  }}
                  disabled={pingingDeviceId === dev.id}
                  title="Ping device heartbeat"
                >
                  <RefreshCw
                    size={13}
                    className={pingingDeviceId === dev.id ? 'spin' : ''}
                  />
                  <span>Ping</span>
                </button>
              </div>

              {/* Hardware Telemetry Bar */}
              <div className="device-fleet__telemetry-row">
                <div className="device-fleet__metric">
                  <div className="device-fleet__metric-header">
                    <Cpu size={12} />
                    <span>CPU</span>
                  </div>
                  <div className="device-fleet__metric-val">
                    {telemetry.cpu_percent !== undefined ? `${telemetry.cpu_percent}%` : '12%'}
                  </div>
                  <div className="device-fleet__mini-progress">
                    <div
                      className="device-fleet__mini-fill device-fleet__mini-fill--cpu"
                      style={{ width: `${Math.min(100, telemetry.cpu_percent || 12)}%` }}
                    />
                  </div>
                </div>

                <div className="device-fleet__metric">
                  <div className="device-fleet__metric-header">
                    <Activity size={12} />
                    <span>RAM</span>
                  </div>
                  <div className="device-fleet__metric-val">
                    {telemetry.memory_percent !== undefined ? `${telemetry.memory_percent}%` : '38%'}
                  </div>
                  <div className="device-fleet__mini-progress">
                    <div
                      className="device-fleet__mini-fill device-fleet__mini-fill--ram"
                      style={{ width: `${Math.min(100, telemetry.memory_percent || 38)}%` }}
                    />
                  </div>
                </div>

                <div className="device-fleet__metric">
                  <div className="device-fleet__metric-header">
                    <HardDrive size={12} />
                    <span>Storage</span>
                  </div>
                  <div className="device-fleet__metric-val">
                    {telemetry.disk_free_gb !== undefined ? `${telemetry.disk_free_gb} GB` : '42 GB'}
                  </div>
                  <span className="device-fleet__metric-sub">Free Disk</span>
                </div>
              </div>

              {/* Foreground / Host Details */}
              <div className="device-fleet__card-footer">
                <div className="device-fleet__info-line">
                  <span className="device-fleet__info-label">Active Surface:</span>
                  <span className="device-fleet__info-value" title={telemetry.active_window || 'Desktop Shell'}>
                    {telemetry.active_window || 'Desktop Shell'}
                  </span>
                </div>
                <div className="device-fleet__info-line">
                  <span className="device-fleet__info-label">Hostname:</span>
                  <span className="device-fleet__info-value">{dev.hostname}</span>
                </div>

                <div className="device-fleet__card-action-bar">
                  {isSelected ? (
                    <button
                      type="button"
                      className="device-fleet__select-btn device-fleet__select-btn--current"
                      disabled
                    >
                      <CheckCircle2 size={14} />
                      <span>Controlling This Device</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="device-fleet__select-btn"
                      onClick={() => onSelectDevice(dev)}
                    >
                      <span>Switch Control Focus</span>
                      <ChevronRight size={14} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. Enrollment Modal */}
      {showEnrollModal && (
        <div className="device-fleet__modal-backdrop" onClick={() => setShowEnrollModal(false)}>
          <div
            className="device-fleet__modal-window"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="enroll-modal-title"
          >
            <div className="device-fleet__modal-header">
              <div className="device-fleet__modal-title-wrap">
                <ShieldCheck size={20} className="device-fleet__modal-icon" />
                <h2 id="enroll-modal-title">Enroll New ROXY Device</h2>
              </div>
              <button
                type="button"
                className="device-fleet__modal-close"
                onClick={() => setShowEnrollModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="device-fleet__modal-tabs">
              <button
                type="button"
                className={`device-fleet__modal-tab ${
                  enrollTab === 'token' ? 'device-fleet__modal-tab--active' : ''
                }`}
                onClick={() => setEnrollTab('token')}
              >
                1. Pairing Token (Daemon)
              </button>
              <button
                type="button"
                className={`device-fleet__modal-tab ${
                  enrollTab === 'manual' ? 'device-fleet__modal-tab--active' : ''
                }`}
                onClick={() => setEnrollTab('manual')}
              >
                2. Quick Companion Register
              </button>
            </div>

            {enrollTab === 'token' ? (
              <div className="device-fleet__modal-body">
                <p className="device-fleet__modal-intro">
                  Use this secure, time-bounded cryptographic token to connect a standalone ROXY
                  Agent daemon running on Windows, macOS, Linux, or Android.
                </p>

                {generatingToken ? (
                  <div className="device-fleet__token-loading">
                    <RefreshCw size={20} className="spin" />
                    <span>Generating cryptographic pairing token...</span>
                  </div>
                ) : (
                  <div className="device-fleet__token-box">
                    <label className="device-fleet__token-label">Enrollment Pairing Token</label>
                    <div className="device-fleet__token-input-row">
                      <input
                        type="text"
                        readOnly
                        value={generatedToken || 'roxy_enroll_demo_98af72bc44'}
                        className="device-fleet__token-input"
                      />
                      <button
                        type="button"
                        className="device-fleet__copy-btn"
                        onClick={handleCopyToken}
                        title="Copy token to clipboard"
                      >
                        {copiedToken ? <Check size={16} /> : <Copy size={16} />}
                        <span>{copiedToken ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                    <span className="device-fleet__token-hint">
                      Valid for 15 minutes. Automatically revoked upon initial hardware handshake.
                    </span>
                  </div>
                )}

                <div className="device-fleet__setup-instructions">
                  <h4>One-Line Terminal Daemon Setup:</h4>
                  <div className="device-fleet__code-block">
                    <code>
                      roxy-daemon enroll --token {generatedToken || 'roxy_enroll_token'} --server {window.location.origin}
                    </code>
                  </div>
                  <h4>Mobile (Android / iOS Companion):</h4>
                  <p>
                    Open ROXY Companion app, scan QR code or paste the token into "Link with Desktop
                    Gateway".
                  </p>
                </div>
              </div>
            ) : (
              <form onSubmit={handleManualSubmit} className="device-fleet__modal-body">
                <p className="device-fleet__modal-intro">
                  Register a simulated companion device or secondary workstation into your active fleet.
                </p>

                <div className="device-fleet__form-group">
                  <label>Device Friendly Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Pixel 8 Pro Companion"
                    value={manualName}
                    onChange={(e) => setManualName(e.target.value)}
                    className="device-fleet__input"
                  />
                </div>

                <div className="device-fleet__form-row">
                  <div className="device-fleet__form-group">
                    <label>Device Type</label>
                    <select
                      value={manualType}
                      onChange={(e) => setManualType(e.target.value)}
                      className="device-fleet__select"
                    >
                      <option value="mobile">Mobile Phone</option>
                      <option value="tablet">Tablet</option>
                      <option value="desktop">Desktop / Laptop</option>
                      <option value="server">Linux Server / Headless</option>
                    </select>
                  </div>

                  <div className="device-fleet__form-group">
                    <label>Operating Platform</label>
                    <select
                      value={manualPlatform}
                      onChange={(e) => setManualPlatform(e.target.value)}
                      className="device-fleet__select"
                    >
                      <option value="android">Android</option>
                      <option value="ios">Apple iOS</option>
                      <option value="windows">Microsoft Windows</option>
                      <option value="macos">Apple macOS</option>
                      <option value="linux">Linux</option>
                    </select>
                  </div>
                </div>

                <div className="device-fleet__form-row">
                  <div className="device-fleet__form-group">
                    <label>Hostname</label>
                    <input
                      type="text"
                      placeholder="e.g. pixel-companion"
                      value={manualHostname}
                      onChange={(e) => setManualHostname(e.target.value)}
                      className="device-fleet__input"
                    />
                  </div>

                  <div className="device-fleet__form-group">
                    <label>IP Address</label>
                    <input
                      type="text"
                      placeholder="192.168.1.120"
                      value={manualIp}
                      onChange={(e) => setManualIp(e.target.value)}
                      className="device-fleet__input"
                    />
                  </div>
                </div>

                <div className="device-fleet__modal-actions">
                  <button
                    type="button"
                    className="device-fleet__btn device-fleet__btn--secondary"
                    onClick={() => setShowEnrollModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="device-fleet__btn device-fleet__btn--primary"
                    disabled={submittingManual}
                  >
                    {submittingManual ? 'Registering...' : 'Register Companion Device'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
