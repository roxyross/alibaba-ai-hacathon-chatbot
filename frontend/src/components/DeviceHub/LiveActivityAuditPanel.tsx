import React, { useState, useMemo } from 'react';
import {
  Terminal,
  ShieldCheck,
  Zap,
  RefreshCw,
  Search,
  AlertTriangle,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  ArrowRight,
} from 'lucide-react';
import type {
  ActionLogItem,
  VerificationRecord,
  RecoveryRecord,
  DeviceInfo,
} from './DeviceHub';

export interface LiveActivityAuditPanelProps {
  device: DeviceInfo | null;
  actionLogs: ActionLogItem[];
  verificationRecords: VerificationRecord[];
  recoveryRecords: RecoveryRecord[];
  loading: boolean;
  onRefresh: () => Promise<void>;
  onTriggerRecoverySimulation: (params: {
    goal: string;
    target_app: string;
    primary_tier: 'api' | 'browser' | 'desktop';
    simulate_failure: boolean;
  }) => Promise<void>;
  simulatingRecovery: boolean;
}

export const LiveActivityAuditPanel: React.FC<LiveActivityAuditPanelProps> = ({
  device: _device,
  actionLogs,
  verificationRecords,
  recoveryRecords,
  loading,
  onRefresh,
  onTriggerRecoverySimulation,
  simulatingRecovery,
}) => {
  const [filterType, setFilterType] = useState<'all' | 'verified' | 'recovery' | 'errors'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Simulation Drawer State
  const [showSimDrawer, setShowSimDrawer] = useState(false);
  const [simGoal, setSimGoal] = useState('Inspect latest messages and send response');
  const [simApp, setSimApp] = useState('Slack');
  const [simPrimaryTier, setSimPrimaryTier] = useState<'api' | 'browser' | 'desktop'>('api');
  const [simInjectFailure, setSimInjectFailure] = useState(true);

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2500);
  };

  const handleRunSimulation = async (e: React.FormEvent) => {
    e.preventDefault();
    await onTriggerRecoverySimulation({
      goal: simGoal,
      target_app: simApp,
      primary_tier: simPrimaryTier,
      simulate_failure: simInjectFailure,
    });
    setShowSimDrawer(false);
  };

  // Combine unified activity items
  type UnifiedItem = {
    id: string;
    kind: 'action' | 'verification' | 'recovery';
    timestamp: string;
    title: string;
    target: string;
    status: 'success' | 'recovered' | 'failed' | 'verified';
    proofHash?: string;
    details: Record<string, any>;
    raw: any;
  };

  const unifiedFeed: UnifiedItem[] = useMemo(() => {
    const items: UnifiedItem[] = [];

    // 1. Action Logs
    for (const log of actionLogs) {
      items.push({
        id: `act_${log.id}`,
        kind: 'action',
        timestamp: log.created_at || new Date().toISOString(),
        title: log.action_type.replace(/_/g, ' ').toUpperCase(),
        target: log.target,
        status: log.status === 'success' ? 'success' : 'failed',
        details: {
          parameters: log.parameters,
          result: log.result,
          error_message: log.error_message,
        },
        raw: log,
      });
    }

    // 2. Phase 17 Verification Records
    for (const v of verificationRecords) {
      items.push({
        id: `ver_${v.id}`,
        kind: 'verification',
        timestamp: v.timestamp || new Date().toISOString(),
        title: `VERIFICATION EVIDENCE [${v.evidence_type.toUpperCase()}]`,
        target: v.details?.target || v.details?.selector || v.evidence_type,
        status: v.verified ? 'verified' : 'failed',
        proofHash: v.proof_hash,
        details: {
          confidence: v.confidence,
          latency_ms: v.latency_ms,
          evidence_type: v.evidence_type,
          ...v.details,
        },
        raw: v,
      });
    }

    // 3. Phase 18 Recovery Records
    for (const r of recoveryRecords) {
      items.push({
        id: `rec_${r.id}`,
        kind: 'recovery',
        timestamp: r.timestamp || new Date().toISOString(),
        title: `MULTI-TIER RECOVERY [${r.primary_tier.toUpperCase()} -> ${r.tier_traversed.join(' -> ').toUpperCase()}]`,
        target: r.goal,
        status: r.final_status === 'recovered' || r.final_status === 'success' ? 'recovered' : 'failed',
        proofHash: r.cryptographic_proof_hash,
        details: {
          error_category: r.error_category,
          self_correction_applied: r.self_correction_applied,
          tier_traversed: r.tier_traversed,
          duration_ms: r.total_duration_ms,
        },
        raw: r,
      });
    }

    // Sort descending by timestamp
    items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    return items;
  }, [actionLogs, verificationRecords, recoveryRecords]);

  // Apply filters
  const filteredFeed = useMemo(() => {
    return unifiedFeed.filter((item) => {
      // Type filter
      if (filterType === 'verified' && item.kind !== 'verification') return false;
      if (filterType === 'recovery' && item.kind !== 'recovery') return false;
      if (filterType === 'errors' && item.status !== 'failed') return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          item.title.toLowerCase().includes(q) ||
          item.target.toLowerCase().includes(q) ||
          (item.proofHash && item.proofHash.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [unifiedFeed, filterType, searchQuery]);

  return (
    <div className="activity-audit">
      {/* 1. Header Toolbar */}
      <div className="activity-audit__controls-bar">
        <div className="activity-audit__search-box">
          <Search size={15} className="activity-audit__search-icon" />
          <input
            type="text"
            className="activity-audit__search-input"
            placeholder="Search action logs, verification proofs, or hashes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="activity-audit__filter-group">
          <button
            type="button"
            className={`activity-audit__filter-btn ${
              filterType === 'all' ? 'activity-audit__filter-btn--active' : ''
            }`}
            onClick={() => setFilterType('all')}
          >
            All Activity ({unifiedFeed.length})
          </button>
          <button
            type="button"
            className={`activity-audit__filter-btn ${
              filterType === 'verified' ? 'activity-audit__filter-btn--active' : ''
            }`}
            onClick={() => setFilterType('verified')}
          >
            <ShieldCheck size={13} />
            <span>Verified Proofs</span>
          </button>
          <button
            type="button"
            className={`activity-audit__filter-btn ${
              filterType === 'recovery' ? 'activity-audit__filter-btn--active' : ''
            }`}
            onClick={() => setFilterType('recovery')}
          >
            <Zap size={13} />
            <span>Recovery Traces</span>
          </button>
          <button
            type="button"
            className={`activity-audit__filter-btn ${
              filterType === 'errors' ? 'activity-audit__filter-btn--active' : ''
            }`}
            onClick={() => setFilterType('errors')}
          >
            <AlertTriangle size={13} />
            <span>Errors</span>
          </button>

          <button
            type="button"
            className="activity-audit__btn activity-audit__btn--sim"
            onClick={() => setShowSimDrawer(true)}
            title="Simulate Multi-Tier Recovery Fallback (Phase 18)"
          >
            <Zap size={14} />
            <span>Simulate Fallback</span>
          </button>

          <button
            type="button"
            className="activity-audit__btn activity-audit__btn--refresh"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Audit Stream Cards */}
      {filteredFeed.length === 0 ? (
        <div className="activity-audit__empty-box">
          <Terminal size={40} />
          <h3>No Recorded Activity Found</h3>
          <p>
            Actions executed by the user or autonomously by ROXY will stream here with real-time cryptographic
            verification proofs and multi-tier recovery traces.
          </p>
          <button
            type="button"
            className="activity-audit__btn activity-audit__btn--sim"
            onClick={() => setShowSimDrawer(true)}
          >
            Run Fallback Simulation Now
          </button>
        </div>
      ) : (
        <div className="activity-audit__stream">
          {filteredFeed.map((item) => {
            const isExpanded = expandedLogId === item.id;
            const isFailed = item.status === 'failed';

            return (
              <div
                key={item.id}
                className={`audit-card audit-card--${item.kind} ${
                  isFailed ? 'audit-card--failed' : ''
                }`}
              >
                {/* Header Row */}
                <div
                  className="audit-card__header"
                  onClick={() => setExpandedLogId(isExpanded ? null : item.id)}
                >
                  <div className="audit-card__header-left">
                    {item.kind === 'verification' && (
                      <span className="audit-card__kind-badge audit-card__kind-badge--verification">
                        <ShieldCheck size={12} />
                        <span>Phase 17 Verification</span>
                      </span>
                    )}
                    {item.kind === 'recovery' && (
                      <span className="audit-card__kind-badge audit-card__kind-badge--recovery">
                        <Zap size={12} />
                        <span>Phase 18 Recovery</span>
                      </span>
                    )}
                    {item.kind === 'action' && (
                      <span className="audit-card__kind-badge audit-card__kind-badge--action">
                        <Terminal size={12} />
                        <span>OS Action</span>
                      </span>
                    )}

                    <h4 className="audit-card__title">{item.title}</h4>
                    <span className="audit-card__target" title={item.target}>
                      {item.target}
                    </span>
                  </div>

                  <div className="audit-card__header-right">
                    <span
                      className={`audit-card__status-pill audit-card__status-pill--${item.status}`}
                    >
                      {item.status.toUpperCase()}
                    </span>
                    <span className="audit-card__timestamp">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </span>
                    <button
                      type="button"
                      className="audit-card__expand-btn"
                      aria-label={isExpanded ? 'Collapse' : 'Expand'}
                    >
                      {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </button>
                  </div>
                </div>

                {/* Proof Hash Badge (if available) */}
                {item.proofHash && (
                  <div className="audit-card__proof-bar">
                    <ShieldCheck size={13} className="audit-card__proof-icon" />
                    <span className="audit-card__proof-label">Cryptographic Proof (SHA-256):</span>
                    <code className="audit-card__proof-code">{item.proofHash}</code>
                    <button
                      type="button"
                      className="audit-card__copy-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopyHash(item.proofHash!);
                      }}
                      title="Copy proof hash"
                    >
                      {copiedHash === item.proofHash ? <Check size={12} /> : <Copy size={12} />}
                      <span>{copiedHash === item.proofHash ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                )}

                {/* Recovery Trajectory Ribbon (Phase 18) */}
                {item.kind === 'recovery' && item.details.tier_traversed && (
                  <div className="audit-card__trajectory-flow">
                    <span className="audit-card__flow-label">Fallback Trajectory:</span>
                    <div className="audit-card__flow-steps">
                      {item.details.tier_traversed.map((tier: string, idx: number) => {
                        const isFinal = idx === item.details.tier_traversed.length - 1;
                        return (
                          <React.Fragment key={tier}>
                            <span
                              className={`audit-card__flow-step ${
                                isFinal
                                  ? 'audit-card__flow-step--success'
                                  : 'audit-card__flow-step--fallback'
                              }`}
                            >
                              Tier {idx + 1}: {tier.toUpperCase()} ROUTE
                              {!isFinal && ' ❌'}
                              {isFinal && ' ✔️'}
                            </span>
                            {!isFinal && <ArrowRight size={12} className="audit-card__flow-arrow" />}
                          </React.Fragment>
                        );
                      })}
                    </div>
                    {item.details.self_correction_applied && (
                      <span className="audit-card__correction-chip">
                        Self-Correction: {item.details.self_correction_applied}
                      </span>
                    )}
                  </div>
                )}

                {/* Expanded Details Drawer */}
                {isExpanded && (
                  <div className="audit-card__expanded-body">
                    <h5>Evidence & Execution Payload:</h5>
                    <pre className="audit-card__json-block">
                      {JSON.stringify(item.details, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 3. Simulate Recovery Fallback Modal (Phase 18) */}
      {showSimDrawer && (
        <div className="activity-audit__modal-backdrop" onClick={() => setShowSimDrawer(false)}>
          <div
            className="activity-audit__modal-window"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="sim-modal-title"
          >
            <div className="activity-audit__modal-header">
              <div className="activity-audit__modal-title-wrap">
                <Zap size={20} className="activity-audit__modal-icon" />
                <h2 id="sim-modal-title">Live Fallback & Recovery Simulator (Phase 18)</h2>
              </div>
              <button
                type="button"
                className="activity-audit__modal-close"
                onClick={() => setShowSimDrawer(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleRunSimulation} className="activity-audit__modal-body">
              <p className="activity-audit__modal-intro">
                Inject empirical failure conditions into ROXY's multi-tier recovery pipeline (API ➔
                Browser ➔ Desktop) to observe autonomous self-correction in real-time.
              </p>

              <div className="activity-audit__form-group">
                <label>Operational Task / Goal</label>
                <input
                  type="text"
                  required
                  value={simGoal}
                  onChange={(e) => setSimGoal(e.target.value)}
                  className="activity-audit__input"
                />
              </div>

              <div className="activity-audit__form-row">
                <div className="activity-audit__form-group">
                  <label>Target Application</label>
                  <select
                    value={simApp}
                    onChange={(e) => setSimApp(e.target.value)}
                    className="activity-audit__select"
                  >
                    <option value="Slack">Slack</option>
                    <option value="Spotify">Spotify</option>
                    <option value="Google Chrome">Google Chrome</option>
                    <option value="Windows Terminal">Windows Terminal</option>
                    <option value="Calculator">Calculator</option>
                  </select>
                </div>

                <div className="activity-audit__form-group">
                  <label>Primary Attempt Tier</label>
                  <select
                    value={simPrimaryTier}
                    onChange={(e) => setSimPrimaryTier(e.target.value as any)}
                    className="activity-audit__select"
                  >
                    <option value="api">API Route (Fastest Protocol)</option>
                    <option value="browser">Browser Route (DOM Tree)</option>
                    <option value="desktop">Desktop Route (Native Process)</option>
                  </select>
                </div>
              </div>

              <div className="activity-audit__checkbox-wrap">
                <label className="activity-audit__checkbox-label">
                  <input
                    type="checkbox"
                    checked={simInjectFailure}
                    onChange={(e) => setSimInjectFailure(e.target.checked)}
                  />
                  <span>
                    Inject Transient Failure (Simulate 500 error or selector mismatch to trigger
                    fallback trajectory)
                  </span>
                </label>
              </div>

              <div className="activity-audit__modal-actions">
                <button
                  type="button"
                  className="activity-audit__btn activity-audit__btn--secondary"
                  onClick={() => setShowSimDrawer(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="activity-audit__btn activity-audit__btn--sim"
                  disabled={simulatingRecovery}
                >
                  {simulatingRecovery ? 'Executing Trajectory...' : 'Trigger Recovery Pipeline'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
