import React, { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Lock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Trash2,
  Sparkles,
  Info,
  Terminal,
  Eye,
  MousePointer,
  Globe,
  Key,
} from 'lucide-react';
import type { DeviceInfo, PermissionGrant } from './DeviceHub';

export interface PermissionItemConfig {
  permission: string;
  name: string;
  category: 'system' | 'visual' | 'input' | 'network' | 'vault';
  risk: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  icon: React.ReactNode;
}

export interface PermissionsMatrixPanelProps {
  device: DeviceInfo | null;
  activeGrants: PermissionGrant[];
  loadingGrants: boolean;
  onUpdatePermission: (
    permission: string,
    policy: 'allow_automatically' | 'always_ask' | 'never_allow',
    scope: 'global' | 'device' | 'app',
    targetApp?: string
  ) => Promise<void>;
  onRevokeGrant: (grantId: string) => Promise<void>;
  onRefreshGrants: () => Promise<void>;
}

export const PermissionsMatrixPanel: React.FC<PermissionsMatrixPanelProps> = ({
  device,
  activeGrants,
  loadingGrants,
  onUpdatePermission,
  onRevokeGrant,
  onRefreshGrants,
}) => {
  const [selectedScope, setSelectedScope] = useState<'global' | 'device' | 'app'>('device');
  const [targetApp, setTargetApp] = useState<string>('Google Chrome');
  const [updatingPerm, setUpdatingPerm] = useState<string | null>(null);

  const permissionDefinitions: PermissionItemConfig[] = [
    {
      permission: 'device:read',
      name: 'System Discovery & Telemetry',
      category: 'system',
      risk: 'low',
      description: 'Read CPU/RAM usage, storage metrics, active window title, and installed process list.',
      icon: <Info size={16} />,
    },
    {
      permission: 'device:execute',
      name: 'App Process Control & Launch',
      category: 'system',
      risk: 'high',
      description: 'Launch application binaries, focus windows, and gracefully terminate background processes.',
      icon: <Terminal size={16} />,
    },
    {
      permission: 'screen:capture',
      name: 'Visual Screen Inspection & OCR',
      category: 'visual',
      risk: 'high',
      description: 'Capture display frames, inspect window geometries, and read rendered screen text via OCR.',
      icon: <Eye size={16} />,
    },
    {
      permission: 'input:simulate',
      name: 'Synthetic Input & Hotkeys',
      category: 'input',
      risk: 'critical',
      description: 'Simulate hardware mouse clicks, cursor moves, keyboard typing, and shortcut key combos.',
      icon: <MousePointer size={16} />,
    },
    {
      permission: 'network:read',
      name: 'DOM Inspection & API Query',
      category: 'network',
      risk: 'low',
      description: 'Inspect live browser DOM elements, read web page content, and poll read-only APIs.',
      icon: <Globe size={16} />,
    },
    {
      permission: 'network:write',
      name: 'Remote API Dispatch & Mutate',
      category: 'network',
      risk: 'high',
      description: 'Trigger authenticated webhooks, submit web forms, and mutate remote cloud resources.',
      icon: <Globe size={16} />,
    },
    {
      permission: 'vault:access',
      name: 'Secure Credential Injection',
      category: 'vault',
      risk: 'critical',
      description: 'Decrypt and inject application tokens, passwords, and API credentials from the Roxy Vault.',
      icon: <Key size={16} />,
    },
  ];

  // Map existing grants to resolve policy for current scope
  const getPolicyForPermission = (perm: string): 'allow_automatically' | 'always_ask' | 'never_allow' => {
    const grant = activeGrants.find((g) => {
      if (g.permission !== perm) return false;
      if (selectedScope === 'global') return g.scope === 'global';
      if (selectedScope === 'device') return g.scope === 'device' && (!g.device_id || g.device_id === device?.id);
      if (selectedScope === 'app') return g.scope === 'app' && g.target_app === targetApp;
      return false;
    });

    if (!grant) {
      // Sensible zero-trust defaults
      if (perm === 'device:read' || perm === 'network:read') return 'allow_automatically';
      if (perm === 'input:simulate' || perm === 'vault:access') return 'always_ask';
      return 'always_ask';
    }

    if (grant.policy === 'allow_automatically') return 'allow_automatically';
    if (grant.policy === 'never_allow' || grant.policy === 'revoked') return 'never_allow';
    return 'always_ask';
  };

  const handlePolicyChange = async (
    permission: string,
    newPolicy: 'allow_automatically' | 'always_ask' | 'never_allow'
  ) => {
    setUpdatingPerm(permission);
    try {
      await onUpdatePermission(
        permission,
        newPolicy,
        selectedScope,
        selectedScope === 'app' ? targetApp : undefined
      );
    } finally {
      setUpdatingPerm(null);
    }
  };

  const applyPreset = async (preset: 'zero_trust' | 'autonomous' | 'dev_sandbox') => {
    if (preset === 'zero_trust') {
      for (const p of permissionDefinitions) {
        if (p.permission === 'device:read') {
          await onUpdatePermission(p.permission, 'allow_automatically', selectedScope, selectedScope === 'app' ? targetApp : undefined);
        } else {
          await onUpdatePermission(p.permission, 'always_ask', selectedScope, selectedScope === 'app' ? targetApp : undefined);
        }
      }
    } else if (preset === 'autonomous') {
      for (const p of permissionDefinitions) {
        if (p.risk === 'critical') {
          await onUpdatePermission(p.permission, 'always_ask', selectedScope, selectedScope === 'app' ? targetApp : undefined);
        } else {
          await onUpdatePermission(p.permission, 'allow_automatically', selectedScope, selectedScope === 'app' ? targetApp : undefined);
        }
      }
    } else if (preset === 'dev_sandbox') {
      await onUpdatePermission('device:read', 'allow_automatically', selectedScope, selectedScope === 'app' ? targetApp : undefined);
      await onUpdatePermission('device:execute', 'allow_automatically', selectedScope, selectedScope === 'app' ? targetApp : undefined);
      await onUpdatePermission('screen:capture', 'allow_automatically', selectedScope, selectedScope === 'app' ? targetApp : undefined);
      await onUpdatePermission('network:write', 'always_ask', selectedScope, selectedScope === 'app' ? targetApp : undefined);
      await onUpdatePermission('vault:access', 'always_ask', selectedScope, selectedScope === 'app' ? targetApp : undefined);
    }
  };

  return (
    <div className="permissions-matrix">
      {/* 1. Scope & Preset Navigation Bar */}
      <div className="permissions-matrix__toolbar">
        <div className="permissions-matrix__scope-selector">
          <label className="permissions-matrix__scope-label">Policy Scope Target:</label>
          <div className="permissions-matrix__scope-tabs">
            <button
              type="button"
              className={`permissions-matrix__scope-btn ${
                selectedScope === 'device' ? 'permissions-matrix__scope-btn--active' : ''
              }`}
              onClick={() => setSelectedScope('device')}
            >
              Device Scope ({device?.device_name || 'Host'})
            </button>
            <button
              type="button"
              className={`permissions-matrix__scope-btn ${
                selectedScope === 'global' ? 'permissions-matrix__scope-btn--active' : ''
              }`}
              onClick={() => setSelectedScope('global')}
            >
              Global (All Devices)
            </button>
            <button
              type="button"
              className={`permissions-matrix__scope-btn ${
                selectedScope === 'app' ? 'permissions-matrix__scope-btn--active' : ''
              }`}
              onClick={() => setSelectedScope('app')}
            >
              App-Specific Policy
            </button>
          </div>
        </div>

        {selectedScope === 'app' && (
          <div className="permissions-matrix__app-picker">
            <label className="permissions-matrix__scope-label">Target App:</label>
            <select
              value={targetApp}
              onChange={(e) => setTargetApp(e.target.value)}
              className="permissions-matrix__app-select"
            >
              <option value="Google Chrome">Google Chrome</option>
              <option value="Visual Studio Code">Visual Studio Code</option>
              <option value="Spotify">Spotify</option>
              <option value="Windows Terminal">Windows Terminal</option>
              <option value="Slack">Slack</option>
              <option value="Calculator">Calculator</option>
            </select>
          </div>
        )}

        <div className="permissions-matrix__presets-group">
          <span className="permissions-matrix__presets-label">Security Presets:</span>
          <button
            type="button"
            className="permissions-matrix__preset-btn"
            onClick={() => applyPreset('zero_trust')}
            title="Require confirmation for all actions except telemetry"
          >
            <ShieldAlert size={13} />
            <span>Strict Zero-Trust</span>
          </button>
          <button
            type="button"
            className="permissions-matrix__preset-btn"
            onClick={() => applyPreset('autonomous')}
            title="Auto-authorize safe and medium-risk tasks"
          >
            <Sparkles size={13} />
            <span>Autonomous Operator</span>
          </button>
        </div>
      </div>

      {/* 2. Interactive Permissions Table */}
      <div className="permissions-matrix__table-wrap">
        <table className="permissions-matrix__table">
          <thead>
            <tr>
              <th style={{ width: '35%' }}>Permission Capability</th>
              <th style={{ width: '15%' }}>Risk Tier</th>
              <th style={{ width: '50%' }}>Policy Enforcement</th>
            </tr>
          </thead>
          <tbody>
            {permissionDefinitions.map((item) => {
              const currentPolicy = getPolicyForPermission(item.permission);
              const isUpdating = updatingPerm === item.permission;

              return (
                <tr key={item.permission} className="permissions-matrix__row">
                  {/* Name & Description */}
                  <td>
                    <div className="permissions-matrix__item-cell">
                      <div className={`permissions-matrix__item-icon permissions-matrix__item-icon--${item.category}`}>
                        {item.icon}
                      </div>
                      <div className="permissions-matrix__item-text">
                        <div className="permissions-matrix__item-name-row">
                          <span className="permissions-matrix__item-name">{item.name}</span>
                          <code className="permissions-matrix__item-code">{item.permission}</code>
                        </div>
                        <p className="permissions-matrix__item-desc">{item.description}</p>
                      </div>
                    </div>
                  </td>

                  {/* Risk Badge */}
                  <td>
                    <span
                      className={`permissions-matrix__risk-badge permissions-matrix__risk-badge--${item.risk}`}
                    >
                      {item.risk.toUpperCase()}
                    </span>
                  </td>

                  {/* 3-Way Segmented Policy Switch */}
                  <td>
                    <div className="permissions-matrix__policy-switch">
                      <button
                        type="button"
                        className={`permissions-matrix__policy-btn permissions-matrix__policy-btn--allow ${
                          currentPolicy === 'allow_automatically'
                            ? 'permissions-matrix__policy-btn--active'
                            : ''
                        }`}
                        onClick={() => handlePolicyChange(item.permission, 'allow_automatically')}
                        disabled={isUpdating}
                        title="Authorize without asking user"
                      >
                        <CheckCircle2 size={13} />
                        <span>Allow Automatically</span>
                      </button>

                      <button
                        type="button"
                        className={`permissions-matrix__policy-btn permissions-matrix__policy-btn--ask ${
                          currentPolicy === 'always_ask'
                            ? 'permissions-matrix__policy-btn--active'
                            : ''
                        }`}
                        onClick={() => handlePolicyChange(item.permission, 'always_ask')}
                        disabled={isUpdating}
                        title="Require user approval prompt before execution"
                      >
                        <AlertTriangle size={13} />
                        <span>Always Ask</span>
                      </button>

                      <button
                        type="button"
                        className={`permissions-matrix__policy-btn permissions-matrix__policy-btn--never ${
                          currentPolicy === 'never_allow'
                            ? 'permissions-matrix__policy-btn--active'
                            : ''
                        }`}
                        onClick={() => handlePolicyChange(item.permission, 'never_allow')}
                        disabled={isUpdating}
                        title="Completely deny access to this capability"
                      >
                        <XCircle size={13} />
                        <span>Never Allow</span>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 3. Active Grants Inspector */}
      <div className="permissions-matrix__grants-card">
        <div className="permissions-matrix__grants-header">
          <div className="permissions-matrix__grants-title">
            <Lock size={16} />
            <span>Active Target-Scoped Grants ({activeGrants.length})</span>
          </div>
          <button
            type="button"
            className="permissions-matrix__refresh-btn"
            onClick={onRefreshGrants}
            disabled={loadingGrants}
          >
            <RefreshCw size={13} className={loadingGrants ? 'spin' : ''} />
            <span>Refresh Grants</span>
          </button>
        </div>

        {activeGrants.length === 0 ? (
          <div className="permissions-matrix__grants-empty">
            <ShieldCheck size={28} />
            <p>No custom policy overrides stored. Default Zero-Trust security rules are enforced.</p>
          </div>
        ) : (
          <div className="permissions-matrix__grants-list">
            {activeGrants.map((grant) => (
              <div key={grant.id} className="permissions-matrix__grant-item">
                <div className="permissions-matrix__grant-info">
                  <span className="permissions-matrix__grant-perm">{grant.permission}</span>
                  <span className="permissions-matrix__grant-policy">{grant.policy}</span>
                  <span className="permissions-matrix__grant-scope">
                    Scope: {grant.scope} {grant.target_app ? `(${grant.target_app})` : ''}
                  </span>
                  {grant.expires_at && (
                    <span className="permissions-matrix__grant-exp">
                      Expires: {new Date(grant.expires_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className="permissions-matrix__grant-revoke"
                  onClick={() => onRevokeGrant(grant.id)}
                  title="Revoke and remove grant"
                >
                  <Trash2 size={13} />
                  <span>Revoke</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
