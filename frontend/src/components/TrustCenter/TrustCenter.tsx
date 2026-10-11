import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  Filter,
  Activity,
  FileLock2,
  Layers,
  Award,
  Key,
  Ban,
  Pause,
  Play,
  Square,
  Lock,
} from 'lucide-react';
import { useAuth } from '../../auth';
import { RiskMatrixPanel } from './RiskMatrixPanel';
import { DLPScannerPanel } from './DLPScannerPanel';
import { ConfirmationGatePanel } from './ConfirmationGatePanel';
import { AdversarialSecurityPanel } from './AdversarialSecurityPanel';
import { ProductionExitGatePanel } from './ProductionExitGatePanel';
import type {
  TrustEvent,
  RecoveryJob,
  TrustDimensions,
  ConfirmationChallenge,
  PermissionGrantItem,
} from './types';
import './TrustCenter.css';

export interface TrustCenterProps {
  accessToken?: string | null;
  onBack?: () => void;
}

export type TrustCenterTab = 'matrix' | 'dlp' | 'confirmations' | 'permissions' | 'history' | 'recovery' | 'security' | 'readiness';

export const TrustCenter: React.FC<TrustCenterProps> = ({ accessToken: propToken, onBack }) => {
  const { accessToken: contextToken } = useAuth();
  const accessToken = propToken || contextToken;
  const [activeTab, setActiveTab] = useState<TrustCenterTab>('matrix');
  const [events, setEvents] = useState<TrustEvent[]>([]);
  const [permissions, setPermissions] = useState<PermissionGrantItem[]>([]);
  const [recoveryJobs, setRecoveryJobs] = useState<RecoveryJob[]>([]);
  const [pendingConfirmations, setPendingConfirmations] = useState<ConfirmationChallenge[]>([]);
  const [dimensions, setDimensions] = useState<TrustDimensions | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [historyViewMode, setHistoryViewMode] = useState<'cards' | 'table'>('cards');

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const fetchData = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${accessToken}` };

      // Fetch dimensions
      const dimRes = await fetch('/api/v1/trust/dimensions', { headers });
      if (dimRes.ok) setDimensions(await dimRes.json());

      // Fetch events
      const filterQuery = statusFilter !== 'all' ? `?status=${statusFilter}` : '';
      const evRes = await fetch(`/api/v1/trust/events${filterQuery}`, { headers });
      if (evRes.ok) {
        const evData = await evRes.json();
        setEvents(evData.items || []);
      }

      // Fetch recovery jobs
      const recRes = await fetch('/api/v1/trust/recovery-jobs', { headers });
      if (recRes.ok) setRecoveryJobs(await recRes.json());

      // Fetch pending confirmations
      const confRes = await fetch('/api/v1/trust/confirmations/pending', { headers });
      if (confRes.ok) setPendingConfirmations(await confRes.json());

      // Fetch permission grants (Phase C)
      const permRes = await fetch('/api/v1/trust/permissions', { headers });
      if (permRes.ok) setPermissions(await permRes.json());
    } catch (err) {
      console.error('Failed to load trust center data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [accessToken, statusFilter]);

  const handleUpdatePolicy = async (grantId: string, policy: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`/api/v1/trust/permissions/${grantId}`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ policy }),
      });
      if (res.ok) {
        showToast(`Permission policy updated to "${policy.replace(/_/g, ' ')}".`);
        fetchData();
      } else {
        alert('Failed to update permission policy.');
      }
    } catch {
      alert('Network error updating policy.');
    }
  };

  const handleRevokePermission = async (grantId: string) => {
    if (!accessToken) return;
    const ok = window.confirm('Are you sure you want to revoke this permission immediately?');
    if (!ok) return;
    try {
      const res = await fetch(`/api/v1/trust/permissions/${grantId}/revoke`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        showToast('Permission revoked with immediate backend enforcement.');
        fetchData();
      } else {
        alert('Failed to revoke permission.');
      }
    } catch {
      alert('Network error revoking permission.');
    }
  };

  const handleResetPermissions = async () => {
    if (!accessToken) return;
    const ok = window.confirm('Reset all permissions to strict "Always Ask" defaults?');
    if (!ok) return;
    try {
      const res = await fetch('/api/v1/trust/permissions/reset', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        showToast('All permissions reset to Always Ask.');
        fetchData();
      } else {
        alert('Failed to reset permissions.');
      }
    } catch {
      alert('Network error resetting permissions.');
    }
  };

  const handleActionControl = async (actionId: string, action: 'cancel' | 'pause' | 'resume' | 'retry') => {
    if (!accessToken) return;
    try {
      const res = await fetch(`/api/v1/trust/actions/${actionId}/${action}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        showToast(`Action ${action} dispatched successfully.`);
        fetchData();
      } else {
        alert(`Failed to ${action} action.`);
      }
    } catch {
      alert(`Network error dispatching ${action}.`);
    }
  };

  const handleRollback = async (event: TrustEvent) => {
    if (!accessToken) return;
    if (!event.rollback_supported) {
      alert(`Cannot undo: This action (${event.action_type}) is technically irreversible once accepted by remote external services.`);
      return;
    }
    const confirmed = window.confirm(`Are you sure you want to rollback "${event.action_name}"?`);
    if (!confirmed) return;

    try {
      const res = await fetch(`/api/v1/trust/events/${event.id}/rollback`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || 'Action rolled back successfully.');
        fetchData();
      } else {
        alert(data.reason || 'Rollback failed.');
      }
    } catch (err) {
      alert('Error triggering rollback.');
    }
  };

  const handleRetryJob = async (jobId: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`/api/v1/trust/recovery-jobs/${jobId}/retry`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || 'Job recovered.');
        fetchData();
      } else {
        alert(data.message || 'Retry failed.');
      }
    } catch (err) {
      alert('Error retrying job.');
    }
  };

  return (
    <div className="trust-center" role="region" aria-label="Trust and Safety Center">
      {toastMessage && <div className="trust-toast">{toastMessage}</div>}

      <div className="trust-header">
        <div className="trust-header__title-row">
          {onBack && (
            <button className="trust-back-btn" onClick={onBack} title="Back to Chat">
              ← Back
            </button>
          )}
          <div className="trust-header__icon">
            <ShieldCheck size={28} />
          </div>
          <div>
            <h1>Trust & Safety Command Center</h1>
            <p className="trust-subtitle">
              Backend-enforced Risk Matrix, Data Loss Prevention (DLP), human-in-the-loop confirmation gates, and cryptographic audit proofs.
            </p>
          </div>
        </div>

        <button className="trust-refresh-btn" onClick={fetchData} title="Refresh data">
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </div>

      {/* Multi-Dimensional Evidence Metrics */}
      {dimensions && (
        <div className="trust-dimensions-grid">
          <div className="dimension-card">
            <div className="dim-head">
              <span className="dim-title">Action Verification</span>
              <span className="dim-value">{dimensions.action_verification.rate}%</span>
            </div>
            <div className="dim-progress">
              <div className="dim-bar" style={{ width: `${dimensions.action_verification.rate}%` }} />
            </div>
            <p className="dim-desc">{dimensions.action_verification.status}</p>
          </div>

          <div className="dimension-card">
            <div className="dim-head">
              <span className="dim-title">Tool Reliability</span>
              <span className="dim-value">{dimensions.tool_reliability.success_rate}%</span>
            </div>
            <div className="dim-progress">
              <div className="dim-bar accent" style={{ width: `${dimensions.tool_reliability.success_rate}%` }} />
            </div>
            <p className="dim-desc">{dimensions.tool_reliability.successful_executions} successful executions</p>
          </div>

          <div className="dimension-card">
            <div className="dim-head">
              <span className="dim-title">Provider Availability</span>
              <span className="dim-value">{dimensions.provider_availability.uptime_rate}%</span>
            </div>
            <div className="dim-progress">
              <div className="dim-bar success" style={{ width: `${dimensions.provider_availability.uptime_rate}%` }} />
            </div>
            <p className="dim-desc">{dimensions.provider_availability.status}</p>
          </div>

          <div className="dimension-card">
            <div className="dim-head">
              <span className="dim-title">Permission Compliance</span>
              <span className="dim-value">{dimensions.permission_compliance.compliance_rate}%</span>
            </div>
            <div className="dim-progress">
              <div className="dim-bar" style={{ width: `${dimensions.permission_compliance.compliance_rate}%` }} />
            </div>
            <p className="dim-desc">{dimensions.permission_compliance.status}</p>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="trust-tabs">
        <button
          className={`trust-tab-btn ${activeTab === 'matrix' ? 'active' : ''}`}
          onClick={() => setActiveTab('matrix')}
        >
          <Layers size={16} />
          Risk Matrix & Posture
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'dlp' ? 'active' : ''}`}
          onClick={() => setActiveTab('dlp')}
        >
          <FileLock2 size={16} />
          DLP Protections & Scanner
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'confirmations' ? 'active' : ''}`}
          onClick={() => setActiveTab('confirmations')}
        >
          <ShieldAlert size={16} />
          Confirmations Gate
          {pendingConfirmations.length > 0 && (
            <span className="tab-pending-badge">{pendingConfirmations.length}</span>
          )}
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'permissions' ? 'active' : ''}`}
          onClick={() => setActiveTab('permissions')}
        >
          <Key size={16} />
          Permissions Transparency ({permissions.length})
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          <Activity size={16} />
          Action History ({events.length})
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'recovery' ? 'active' : ''}`}
          onClick={() => setActiveTab('recovery')}
        >
          <RotateCcw size={16} />
          Recovery Queue ({recoveryJobs.length})
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
          onClick={() => setActiveTab('security')}
        >
          <ShieldAlert size={16} />
          Adversarial Defense
        </button>

        <button
          className={`trust-tab-btn ${activeTab === 'readiness' ? 'active' : ''}`}
          onClick={() => setActiveTab('readiness')}
        >
          <Award size={16} />
          Exit Gate &amp; Readiness
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'matrix' && (
        <RiskMatrixPanel accessToken={accessToken} />
      )}

      {activeTab === 'dlp' && (
        <DLPScannerPanel accessToken={accessToken} />
      )}

      {activeTab === 'confirmations' && (
        <ConfirmationGatePanel accessToken={accessToken} onShowToast={showToast} />
      )}

      {activeTab === 'permissions' && (
        <div className="trust-section">
          <div className="trust-section-bar">
            <div>
              <h2>Permission Transparency & Granular Policy Controls</h2>
              <p className="section-subtitle">
                Inspect and control every app, device, and connector access grant. Backend-enforced confirmation policies: Always Ask, Ask Once, Allow Automatically, or Never Allow.
              </p>
            </div>
            <button className="reset-perms-btn" onClick={handleResetPermissions}>
              <RotateCcw size={14} />
              Reset All to "Always Ask"
            </button>
          </div>

          {permissions.length === 0 ? (
            <div className="empty-state">
              <Key size={48} className="empty-icon" />
              <h3>No External Permissions Granted</h3>
              <p>When Roxy accesses devices, apps, or financial rails, explicit authorization grants appear here.</p>
            </div>
          ) : (
            <div className="permissions-grid">
              {permissions.map((p) => (
                <div key={p.id} className={`permission-card ${p.status === 'revoked' ? 'perm-revoked' : ''}`}>
                  <div className="perm-card-head">
                    <div className="perm-app-tag">
                      <Lock size={13} />
                      <span>{p.application}</span>
                    </div>
                    <span className={`perm-status-badge status-${p.status}`}>{p.status.toUpperCase()}</span>
                  </div>
                  <h3 className="perm-capability">{p.capability}</h3>
                  <div className="perm-target"><strong>Target:</strong> {p.target}</div>
                  <div className="perm-why"><strong>Why Needed:</strong> {p.why_needed}</div>

                  <div className="perm-meta-row">
                    <div><span>Granted By:</span> {p.granted_by}</div>
                    <div><span>Scope:</span> {p.scope}</div>
                    <div><span>Duration:</span> {p.duration}</div>
                  </div>

                  <div className="perm-policy-control">
                    <label>Confirmation Policy:</label>
                    <select
                      value={p.confirmation_policy}
                      disabled={p.status === 'revoked'}
                      onChange={(e) => handleUpdatePolicy(p.id, e.target.value)}
                      className="perm-policy-select"
                    >
                      <option value="always_ask">Always Ask (Strict Confirmation)</option>
                      <option value="ask_once">Ask Once (Session Scope)</option>
                      <option value="allow_automatically">Allow Automatically (Trusted)</option>
                      <option value="never_allow">Never Allow (Blocked)</option>
                    </select>
                  </div>

                  <div className="perm-actions">
                    {p.status !== 'revoked' && p.can_revoke && (
                      <button className="revoke-btn" onClick={() => handleRevokePermission(p.id)}>
                        <Ban size={13} />
                        Revoke Access
                      </button>
                    )}
                    {p.status === 'revoked' && (
                      <span className="revoked-notice">Access permanently revoked</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="trust-section">
          <div className="trust-section-bar">
            <div>
              <h2>Immutable Action Audit Feed</h2>
              <p className="section-subtitle">
                Understandable explanations for every action Roxy requested, verified, or executed. Never claims success without verified proof.
              </p>
            </div>
            <div className="history-controls-row">
              <div className="view-toggle-btns">
                <button
                  className={`view-toggle-btn ${historyViewMode === 'cards' ? 'active' : ''}`}
                  onClick={() => setHistoryViewMode('cards')}
                >
                  Cards View
                </button>
                <button
                  className={`view-toggle-btn ${historyViewMode === 'table' ? 'active' : ''}`}
                  onClick={() => setHistoryViewMode('table')}
                >
                  Audit Table
                </button>
              </div>
              <div className="filter-group">
                <Filter size={15} />
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="trust-select"
                >
                  <option value="all">All Statuses</option>
                  <option value="succeeded">Succeeded</option>
                  <option value="failed">Failed</option>
                  <option value="partial">Partial Execution</option>
                  <option value="queued">Queued</option>
                  <option value="running">In Progress / Running</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
            </div>
          </div>

          {events.length === 0 ? (
            <div className="empty-state">
              <ShieldCheck size={48} className="empty-icon" />
              <h3>No Action Events Recorded Yet</h3>
              <p>Actions performed by Roxy, connectors, and tools will appear here with verification proofs.</p>
            </div>
          ) : historyViewMode === 'cards' ? (
            <div className="action-cards-grid">
              {events.map((ev) => {
                const appName = ev.external_service || ev.tool_id || 'Roxy Assistant';
                const requestedTime = new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const isRunning = ev.execution_status === 'running' || ev.execution_status === 'in_progress';
                const isQueued = ev.execution_status === 'queued';
                const isPaused = ev.execution_status === 'paused';

                return (
                  <div key={ev.id} className="action-proof-card">
                    <div className="action-proof-head">
                      <div className="action-app-badge">{appName}</div>
                      <div className="action-time-badge">{requestedTime}</div>
                    </div>

                    <h3 className="action-proof-title">{ev.action_name}</h3>
                    <div className="action-proof-type">{ev.action_type}</div>

                    <div className="action-proof-fields">
                      <div className="proof-field">
                        <span className="field-label">App:</span>
                        <span className="field-val">{appName}</span>
                      </div>
                      <div className="proof-field">
                        <span className="field-label">Action:</span>
                        <span className="field-val">{ev.action_name}</span>
                      </div>
                      <div className="proof-field">
                        <span className="field-label">Requested:</span>
                        <span className="field-val">{requestedTime}</span>
                      </div>
                      <div className="proof-field">
                        <span className="field-label">Permission:</span>
                        <span className={`field-val perm-${ev.permission_status || 'approved'}`}>
                          {ev.permission_status ? ev.permission_status.toUpperCase() : (ev.permission_required ? 'Approved' : 'Implicit / Allowed')}
                        </span>
                      </div>
                      <div className="proof-field">
                        <span className="field-label">Execution:</span>
                        <span className={`status-badge status-${ev.execution_status}`}>
                          {ev.execution_status.toUpperCase()}
                        </span>
                      </div>
                      <div className="proof-field">
                        <span className="field-label">Verification:</span>
                        <span className={`verify-badge verify-${ev.verification_status}`}>
                          {ev.verification_status === 'verified' && <CheckCircle2 size={12} />}
                          {ev.verification_status === 'failed' && <XCircle size={12} />}
                          {ev.verification_status === 'unverified' && <Clock size={12} />}
                          {ev.verification_status.toUpperCase()}
                        </span>
                      </div>
                      <div className="proof-field">
                        <span className="field-label">Undo:</span>
                        <span className="field-val">
                          {ev.rollback_supported ? (
                            ev.rollback_status === 'rolled_back' ? (
                              <span className="undo-undone">Rolled Back</span>
                            ) : (
                              <button className="card-undo-btn" onClick={() => handleRollback(ev)}>
                                <RotateCcw size={11} />
                                Undo Action
                              </button>
                            )
                          ) : (
                            <span className="undo-unavailable" title="External side-effects or irreversible changes cannot be simulated as undone.">
                              Undo Unavailable
                            </span>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* Action Explanation (Action-level only, no hidden chain-of-thought) */}
                    <div className="action-explanation">
                      <span className="expl-label">Explanation:</span>
                      <p className="expl-text">
                        {ev.metadata?.explanation ||
                         ev.failure_reason ||
                         (ev.execution_status === 'succeeded'
                           ? `Successfully completed ${ev.action_name} on ${ev.target || appName}.`
                           : `Action state is ${ev.execution_status}.`)}
                      </p>
                    </div>

                    {/* Interactive Action Controls (Stop/Cancel/Pause/Resume/Retry) */}
                    {(isRunning || isQueued || isPaused || ev.execution_status === 'failed') && (
                      <div className="card-controls-row">
                        {isRunning && (
                          <>
                            <button className="ctrl-btn pause" onClick={() => handleActionControl(ev.id, 'pause')}>
                              <Pause size={12} /> Pause
                            </button>
                            <button className="ctrl-btn cancel" onClick={() => handleActionControl(ev.id, 'cancel')}>
                              <Square size={12} /> Stop / Cancel
                            </button>
                          </>
                        )}
                        {isPaused && (
                          <>
                            <button className="ctrl-btn resume" onClick={() => handleActionControl(ev.id, 'resume')}>
                              <Play size={12} /> Resume
                            </button>
                            <button className="ctrl-btn cancel" onClick={() => handleActionControl(ev.id, 'cancel')}>
                              <Square size={12} /> Cancel
                            </button>
                          </>
                        )}
                        {isQueued && (
                          <button className="ctrl-btn cancel" onClick={() => handleActionControl(ev.id, 'cancel')}>
                            <Square size={12} /> Cancel Queued
                          </button>
                        )}
                        {ev.execution_status === 'failed' && (
                          <button className="ctrl-btn retry" onClick={() => handleActionControl(ev.id, 'retry')}>
                            <RefreshCw size={12} /> Retry Action
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="events-table-wrapper">
              <table className="events-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Tool</th>
                    <th>Risk</th>
                    <th>Status</th>
                    <th>Verification</th>
                    <th>Rollback</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.id}>
                      <td className="ts-cell">
                        {new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="action-cell">
                        <strong>{ev.action_name}</strong>
                        <div className="action-sub">{ev.action_type}</div>
                      </td>
                      <td>{ev.tool_id || 'System'}</td>
                      <td>
                        <span className={`risk-badge risk-${ev.risk_level}`}>{ev.risk_level}</span>
                      </td>
                      <td>
                        <span className={`status-badge status-${ev.execution_status}`}>
                          {ev.execution_status}
                        </span>
                      </td>
                      <td>
                        <span className={`verify-badge verify-${ev.verification_status}`}>
                          {ev.verification_status === 'verified' && <CheckCircle2 size={13} />}
                          {ev.verification_status === 'failed' && <XCircle size={13} />}
                          {ev.verification_status === 'unverified' && <Clock size={13} />}
                          {ev.verification_status}
                        </span>
                      </td>
                      <td>
                        {ev.rollback_supported ? (
                          <button
                            className="rollback-btn"
                            disabled={ev.rollback_status === 'rolled_back'}
                            onClick={() => handleRollback(ev)}
                          >
                            <RotateCcw size={12} />
                            {ev.rollback_status === 'rolled_back' ? 'Undone' : 'Undo'}
                          </button>
                        ) : (
                          <span className="non-reversible">Irreversible</span>
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

      {activeTab === 'recovery' && (
        <div className="trust-section">
          <h2>Resilient Failure Recovery & Idempotent Retries</h2>
          <p className="section-subtitle">
            Failed connector or network operations are safely isolated with idempotency keys. High-impact operations (payments, external sends) are never auto-retried.
          </p>

          {recoveryJobs.length === 0 ? (
            <div className="empty-state">
              <CheckCircle2 size={48} className="empty-icon-success" />
              <h3>All Systems Clear</h3>
              <p>Zero queued failures. All operations are operating cleanly.</p>
            </div>
          ) : (
            <div className="recovery-grid">
              {recoveryJobs.map((job) => (
                <div key={job.id} className="recovery-card">
                  <div className="recovery-card-head">
                    <span className="rec-action">{job.action_type}</span>
                    <span className={`rec-status status-${job.status}`}>{job.status}</span>
                  </div>
                  <div className="rec-category">Category: {job.failure_category}</div>
                  <div className="rec-retries">
                    Retries: {job.retry_count} / {job.max_retries}
                  </div>
                  {job.last_error && <div className="rec-error">{job.last_error}</div>}
                  <div className="rec-actions">
                    <button
                      className="retry-btn"
                      disabled={job.status === 'recovered' || job.status === 'cancelled'}
                      onClick={() => handleRetryJob(job.id)}
                    >
                      <RefreshCw size={13} />
                      Retry Now
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'security' && (
        <AdversarialSecurityPanel accessToken={accessToken} />
      )}

      {activeTab === 'readiness' && (
        <ProductionExitGatePanel accessToken={accessToken} />
      )}
    </div>
  );
};
