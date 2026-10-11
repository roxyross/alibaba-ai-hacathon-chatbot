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
} from './types';
import './TrustCenter.css';

export interface TrustCenterProps {
  accessToken?: string | null;
  onBack?: () => void;
}

export type TrustCenterTab = 'matrix' | 'dlp' | 'confirmations' | 'history' | 'recovery' | 'security' | 'readiness';

export const TrustCenter: React.FC<TrustCenterProps> = ({ accessToken: propToken, onBack }) => {
  const { accessToken: contextToken } = useAuth();
  const accessToken = propToken || contextToken;
  const [activeTab, setActiveTab] = useState<TrustCenterTab>('matrix');
  const [events, setEvents] = useState<TrustEvent[]>([]);
  const [recoveryJobs, setRecoveryJobs] = useState<RecoveryJob[]>([]);
  const [pendingConfirmations, setPendingConfirmations] = useState<ConfirmationChallenge[]>([]);
  const [dimensions, setDimensions] = useState<TrustDimensions | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

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
    } catch (err) {
      console.error('Failed to load trust center data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [accessToken, statusFilter]);

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

      {activeTab === 'history' && (
        <div className="trust-section">
          <div className="trust-section-bar">
            <h2>Immutable Action Audit Feed</h2>
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
                <option value="requested">Requested</option>
              </select>
            </div>
          </div>

          {events.length === 0 ? (
            <div className="empty-state">
              <ShieldCheck size={48} className="empty-icon" />
              <h3>No Action Events Recorded Yet</h3>
              <p>Actions performed by Roxy, connectors, and tools will appear here with verification proofs.</p>
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
