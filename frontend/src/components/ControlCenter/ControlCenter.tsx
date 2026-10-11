import React, { useEffect, useState } from 'react';
import {
  Sliders,
  HeartPulse,
  UserCheck,
  Download,
  Trash2,
  AlertOctagon,
  Sparkles,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  XCircle,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';
import { useAuth } from '../../auth';
import type { AppView } from '../../session/SessionSidebar';
import './ControlCenter.css';

interface SubsystemHealth {
  name: string;
  category: string;
  status: string;
  description: string;
  can_retry: boolean;
  data_safe: boolean;
  explanation?: {
    what_happened: string;
    what_is_affected: string;
    what_can_i_do: string;
    is_data_safe: string;
    can_roxy_retry: string;
  };
}

interface HealthCenterResponse {
  overall_status: string;
  total_subsystems: number;
  healthy_count: number;
  degraded_count: number;
  unavailable_count: number;
  subsystems: SubsystemHealth[];
}

interface PersonalizationProposal {
  id: string;
  category: string;
  key: string;
  proposed_value: string;
  rationale: string;
  status: string;
  created_at: string;
}

export interface ControlCenterProps {
  accessToken?: string | null;
  onBack?: () => void;
  onNavigate?: (view: AppView) => void;
}

export const ControlCenter: React.FC<ControlCenterProps> = ({ accessToken: propToken, onBack, onNavigate }) => {
  const { accessToken: contextToken, signOut } = useAuth();
  const accessToken = propToken || contextToken;
  const [healthData, setHealthData] = useState<HealthCenterResponse | null>(null);
  const [selectedSubsystem, setSelectedSubsystem] = useState<SubsystemHealth | null>(null);
  const [proposals, setProposals] = useState<PersonalizationProposal[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [exporting, setExporting] = useState<boolean>(false);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [deleteConfirmationPhrase, setDeleteConfirmationPhrase] = useState<string>('');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const loadData = async () => {
    setLoading(true);
    try {
      // 1. Health
      const hRes = await fetch('/api/v1/diagnostics/health-center');
      if (hRes.ok) setHealthData(await hRes.json());

      // 2. Personalization proposals
      if (accessToken) {
        const pRes = await fetch('/api/v1/personalization/proposals?status=pending', {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (pRes.ok) setProposals(await pRes.json());
      }
    } catch (err) {
      console.error('Failed to load control center data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [accessToken]);

  const handleResolveProposal = async (id: string, approve: boolean) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`/api/v1/personalization/proposals/${id}/resolve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ approve }),
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || (approve ? 'Proposal approved' : 'Proposal declined'));
        loadData();
      }
    } catch (err) {
      alert('Error updating preference proposal.');
    }
  };

  const handleResetPersonalization = async () => {
    if (!accessToken) return;
    const ok = window.confirm('Reset all learned preferences to default settings?');
    if (!ok) return;

    try {
      const res = await fetch('/api/v1/personalization/reset', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await res.json();
      if (data.success) {
        showToast('Personalization reset to defaults.');
        loadData();
      }
    } catch (err) {
      alert('Error resetting preferences.');
    }
  };

  const handleExportData = async () => {
    if (!accessToken) return;
    setExporting(true);
    try {
      const res = await fetch('/api/v1/account/export', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await res.json();
      if (data.job_id) {
        // Download directly
        const dlRes = await fetch(`/api/v1/account/export/${data.job_id}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (dlRes.ok) {
          const exportBundle = await dlRes.json();
          const blob = new Blob([JSON.stringify(exportBundle.data, null, 2)], {
            type: 'application/json',
          });
          const url = URL.createObjectURL(blob);
          setExportUrl(url);
          showToast('Data export ready for download.');
        }
      }
    } catch (err) {
      alert('Export request failed.');
    } finally {
      setExporting(false);
    }
  };

  const handleDeleteData = async () => {
    if (!accessToken) return;
    const ok = window.confirm(
      'Are you sure you want to delete your personal chats, memories, and documents? Legal and security logs will be retained.'
    );
    if (!ok) return;

    try {
      const res = await fetch('/api/v1/account/delete-data', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await res.json();
      if (data.success) {
        showToast('Personal data successfully cleared.');
        loadData();
      }
    } catch (err) {
      alert('Failed to clear data.');
    }
  };

  const handleAccountDeletion = async () => {
    if (!accessToken) return;
    if (deleteConfirmationPhrase !== 'DELETE MY ACCOUNT') {
      alert('Please type DELETE MY ACCOUNT exactly as shown.');
      return;
    }

    try {
      const res = await fetch('/api/v1/account/delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ confirmation: deleteConfirmationPhrase }),
      });
      const data = await res.json();
      if (data.success) {
        alert('Account permanently deleted. Signing out.');
        signOut();
      } else {
        alert(data.reason || 'Account deletion failed.');
      }
    } catch (err) {
      alert('Account deletion failed.');
    }
  };

  return (
    <div className="control-center" role="region" aria-label="Roxy Control Center">
      {toastMessage && <div className="control-toast">{toastMessage}</div>}

      <div className="control-header">
        <div className="control-header__title-row">
          {onBack && (
            <button className="control-back-btn" onClick={onBack} title="Back to Chat">
              ← Back
            </button>
          )}
          <div className="control-header__icon">
            <Sliders size={28} />
          </div>
          <div>
            <h1>Roxy Control Center</h1>
            <p className="control-subtitle">
              Central operational cockpit unifying diagnostics, controlled personalization, privacy, and subsystems.
            </p>
          </div>
        </div>

        <button className="control-refresh-btn" onClick={loadData} title="Refresh status">
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </div>

      {/* 1. Roxy Health Center (15 Operational Subsystems) */}
      <section className="control-card">
        <div className="card-header-row">
          <div className="card-title-group">
            <HeartPulse size={20} className="card-icon text-emerald" />
            <h2>Roxy Health Center (15 Subsystems)</h2>
          </div>
          {healthData && (
            <span className={`overall-status-pill status-${healthData.overall_status.toLowerCase()}`}>
              System: {healthData.overall_status} ({healthData.healthy_count}/{healthData.total_subsystems} Healthy)
            </span>
          )}
        </div>

        <p className="section-help-text">
          Live telemetry matrix across all core components. Click any item for human-readable diagnostic analysis.
        </p>

        {healthData && (
          <div className="subsystems-grid">
            {healthData.subsystems.map((sub) => {
              const isHealthy = sub.status === 'Healthy';
              const isDegraded = sub.status === 'Degraded' || sub.status === 'Configuration Required';
              return (
                <div
                  key={sub.name}
                  className={`subsystem-tile ${isHealthy ? 'tile-healthy' : isDegraded ? 'tile-degraded' : 'tile-error'}`}
                  onClick={() => setSelectedSubsystem(sub)}
                >
                  <div className="subsystem-tile-top">
                    <span className="sub-name">{sub.name}</span>
                    {isHealthy && <CheckCircle size={15} className="text-emerald" />}
                    {isDegraded && <AlertTriangle size={15} className="text-amber" />}
                    {!isHealthy && !isDegraded && <XCircle size={15} className="text-red" />}
                  </div>
                  <div className="sub-status-label">{sub.status}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* Selected Subsystem Detail Modal / Drawer */}
        {selectedSubsystem && (
          <div className="diagnostic-modal-backdrop" onClick={() => setSelectedSubsystem(null)}>
            <div className="diagnostic-modal" onClick={(e) => e.stopPropagation()}>
              <div className="diag-header">
                <h3>{selectedSubsystem.name} Diagnostics</h3>
                <button className="close-btn" onClick={() => setSelectedSubsystem(null)}>
                  ✕
                </button>
              </div>

              <div className="diag-body">
                <div className="diag-meta-row">
                  <span>Current State:</span>
                  <strong className={`status-${selectedSubsystem.status.toLowerCase()}`}>
                    {selectedSubsystem.status}
                  </strong>
                </div>
                <p className="diag-desc">{selectedSubsystem.description}</p>

                {selectedSubsystem.explanation ? (
                  <div className="human-explanation-box">
                    <h4>Human-Readable Diagnostic Answers</h4>
                    <div className="q-and-a">
                      <div className="q">What happened?</div>
                      <div className="a">{selectedSubsystem.explanation.what_happened}</div>

                      <div className="q">What is affected?</div>
                      <div className="a">{selectedSubsystem.explanation.what_is_affected}</div>

                      <div className="q">What can I do?</div>
                      <div className="a">{selectedSubsystem.explanation.what_can_i_do}</div>

                      <div className="q">Is my data safe?</div>
                      <div className="a">{selectedSubsystem.explanation.is_data_safe}</div>

                      <div className="q">Can Roxy retry?</div>
                      <div className="a">{selectedSubsystem.explanation.can_roxy_retry}</div>
                    </div>
                  </div>
                ) : (
                  <div className="diag-clean-box">
                    <CheckCircle size={18} className="text-emerald" />
                    <span>Subsystem is operating nominally with zero active incidents or bottlenecks.</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* 2. Controlled Personalization Engine */}
      <section className="control-card">
        <div className="card-header-row">
          <div className="card-title-group">
            <UserCheck size={20} className="card-icon text-blue" />
            <h2>Controlled Personalization Engine</h2>
          </div>
          <button className="btn-secondary" onClick={handleResetPersonalization}>
            Reset to Defaults
          </button>
        </div>

        <p className="section-help-text">
          Roxy only learns habits with your explicit consent. No secret profiling or silent behavioral modifications.
        </p>

        {proposals.length === 0 ? (
          <div className="empty-sub-box">
            <Sparkles size={24} className="text-muted" />
            <p>No pending preference proposals. Roxy is operating on your explicitly confirmed settings.</p>
          </div>
        ) : (
          <div className="proposals-list">
            {proposals.map((prop) => (
              <div key={prop.id} className="proposal-item">
                <div className="prop-info">
                  <div className="prop-key">
                    <strong>{prop.key}</strong> &rarr; <span className="val">{prop.proposed_value}</span>
                  </div>
                  <div className="prop-rationale">{prop.rationale}</div>
                </div>
                <div className="prop-actions">
                  <button
                    className="btn-approve"
                    onClick={() => handleResolveProposal(prop.id, true)}
                  >
                    Approve
                  </button>
                  <button
                    className="btn-decline"
                    onClick={() => handleResolveProposal(prop.id, false)}
                  >
                    Decline
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 3. User Data Control, Export & Deletion */}
      <section className="control-card">
        <div className="card-header-row">
          <div className="card-title-group">
            <Download size={20} className="card-icon text-purple" />
            <h2>Data Control & Privacy Sovereignty</h2>
          </div>
        </div>

        <div className="privacy-actions-grid">
          <div className="privacy-action-card">
            <h4>Export Your Data</h4>
            <p>Download complete JSON bundle of your chats, memories, knowledge files, and settings.</p>
            <button className="btn-primary" onClick={handleExportData} disabled={exporting}>
              <Download size={14} />
              {exporting ? 'Preparing Export...' : 'Request Export Bundle'}
            </button>
            {exportUrl && (
              <a
                href={exportUrl}
                download="roxy_personal_data_export.json"
                className="download-link"
              >
                Download Export File
              </a>
            )}
          </div>

          <div className="privacy-action-card">
            <h4>Clear Personal Data</h4>
            <p>Purges messages, semantic memories, and custom documents while maintaining legal security logs.</p>
            <button className="btn-warning" onClick={handleDeleteData}>
              <Trash2 size={14} />
              Clear Personal Data
            </button>
          </div>

          <div className="privacy-action-card border-danger">
            <h4>Permanent Account Deletion</h4>
            <p>Permanently remove your account, active credentials, and all associated tenant resources.</p>
            <button className="btn-danger" onClick={() => setShowDeleteModal(true)}>
              <AlertOctagon size={14} />
              Delete Account
            </button>
          </div>
        </div>
      </section>

      {/* 4. Subsystem Quick Navigator */}
      <section className="control-card">
        <h2>Subsystem Navigation</h2>
        <p className="section-help-text">Direct access to specialized operating engines.</p>
        <div className="nav-grid">
          <button className="subsystem-nav-btn" onClick={() => onNavigate?.('trust_center')}>
            <span>Trust & Safety Center</span>
            <ArrowRight size={14} />
          </button>
          <button className="subsystem-nav-btn" onClick={() => onNavigate?.('memory')}>
            <span>Semantic Memory</span>
            <ArrowRight size={14} />
          </button>
          <button className="subsystem-nav-btn" onClick={() => onNavigate?.('knowledge_vault')}>
            <span>Knowledge Vault</span>
            <ArrowRight size={14} />
          </button>
          <button className="subsystem-nav-btn" onClick={() => onNavigate?.('connectors')}>
            <span>Connectors & MCP</span>
            <ArrowRight size={14} />
          </button>
          <button className="subsystem-nav-btn" onClick={() => onNavigate?.('device_hub')}>
            <span>Device Agent</span>
            <ArrowRight size={14} />
          </button>
          <button className="subsystem-nav-btn" onClick={() => onNavigate?.('billing')}>
            <span>Billing & Usage</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </section>

      {/* Account Deletion Confirmation Modal */}
      {showDeleteModal && (
        <div className="diagnostic-modal-backdrop" onClick={() => setShowDeleteModal(false)}>
          <div className="diagnostic-modal danger-modal" onClick={(e) => e.stopPropagation()}>
            <div className="diag-header">
              <div className="danger-title">
                <ShieldAlert size={20} className="text-red" />
                <h3>Confirm Permanent Account Deletion</h3>
              </div>
              <button className="close-btn" onClick={() => setShowDeleteModal(false)}>
                ✕
              </button>
            </div>

            <div className="diag-body">
              <p className="warning-text">
                This action is <strong>irreversible</strong>. All your active sessions, conversations, custom skills, uploaded documents, and authentication tokens will be destroyed immediately.
              </p>
              <p>To proceed, please type <strong>DELETE MY ACCOUNT</strong> below:</p>

              <input
                type="text"
                className="confirm-input"
                value={deleteConfirmationPhrase}
                onChange={(e) => setDeleteConfirmationPhrase(e.target.value)}
                placeholder="DELETE MY ACCOUNT"
              />

              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setShowDeleteModal(false)}>
                  Cancel
                </button>
                <button
                  className="btn-danger"
                  disabled={deleteConfirmationPhrase !== 'DELETE MY ACCOUNT'}
                  onClick={handleAccountDeletion}
                >
                  Permanently Delete My Account
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
