import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ShieldCheck,
  ArrowLeft,
  Search,
  RefreshCw,
  Download,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Sliders,
  ChevronDown,
  ChevronUp,
  FileCode,
  Lock,
  Activity,
} from 'lucide-react';
import './AuditStudio.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export type ApprovalTier = 'T1' | 'T2' | 'T3';
export type AuditStatusCode = 'ok' | 'caution' | 'blocked' | 'error';
export type RiskVerdict = 'clear' | 'caution' | 'block';

export interface AuditLogItem {
  id: string;
  user_id: string;
  trace_id: string;
  agent_slug: string;
  action: string;
  skill_slug?: string | null;
  approval_tier: string;
  approved_by: string;
  model_used?: string | null;
  provider?: string | null;
  request_query?: string | null;
  response_summary?: string | null;
  decision: string;
  latency_ms: number;
  status_code: string;
  details: Record<string, unknown>;
  created_at?: string | null;
}

export interface AuditStats {
  total_events: number;
  today_events: number;
  by_agent: Record<string, number>;
  by_status: Record<string, number>;
  by_tier: Record<string, number>;
  avg_latency_ms: number;
  retention_days: number;
  last_event_at?: string | null;
}

export interface RiskCheckResponse {
  action: string;
  risk_verdict: RiskVerdict;
  approval_tier: ApprovalTier;
  reason: string;
  warning_to_user: string;
  narrower_alternative?: string | null;
  blast_radius: string;
  is_reversible: boolean;
  blocking: boolean;
}

export interface AuditStudioProps {
  onBack?: () => void;
  accessToken?: string | null;
}

export const AuditStudio: React.FC<AuditStudioProps> = ({ onBack, accessToken }) => {
  const [activeTab, setActiveTab] = useState<'timeline' | 'risk_gate' | 'compliance'>('timeline');

  // Timeline State
  const [events, setEvents] = useState<AuditLogItem[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [agentFilter, setAgentFilter] = useState('all');
  const [tierFilter, setTierFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Risk Gate Simulator State
  const [riskAction, setRiskAction] = useState('send_email');
  const [riskTarget, setRiskTarget] = useState('client@example.com');
  const [riskPrompt, setRiskPrompt] = useState('Send the proposal email with confidential pricing.');
  const [riskParamsJson, setRiskParamsJson] = useState('{\n  "recipient": "client@example.com",\n  "subject": "Q3 Proposal"\n}');
  const [riskVerdict, setRiskVerdict] = useState<RiskCheckResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);

  // Compliance Export State
  const [exporting, setExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState<string | null>(null);

  const effectiveToken = useMemo(() => {
    if (accessToken) return accessToken;
    if (typeof window !== 'undefined') {
      return localStorage.getItem('access_token') || localStorage.getItem('auth_token');
    }
    return null;
  }, [accessToken]);

  const authHeaders = useMemo(() => {
    return {
      'Content-Type': 'application/json',
      ...(effectiveToken ? { Authorization: `Bearer ${effectiveToken}` } : {}),
    };
  }, [effectiveToken]);

  // Fetch Stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/audit/stats`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as AuditStats;
        setStats(data);
      }
    } catch {
      // Ignore background failure
    }
  }, [authHeaders]);

  // Fetch Events
  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (agentFilter !== 'all') params.append('agent_slug', agentFilter);
      if (tierFilter !== 'all') params.append('approval_tier', tierFilter);
      if (statusFilter !== 'all') params.append('status_code', statusFilter);
      if (searchQuery.trim()) params.append('search', searchQuery.trim());
      params.append('limit', '50');

      const res = await fetch(`${API_BASE}/audit?${params.toString()}`, {
        headers: authHeaders,
      });
      if (!res.ok) {
        throw new Error(`Failed to load audit trail (${res.status})`);
      }
      const data = await res.json();
      setEvents(data.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error fetching audit logs');
    } finally {
      setLoading(false);
    }
  }, [agentFilter, tierFilter, statusFilter, searchQuery, authHeaders]);

  useEffect(() => {
    void fetchEvents();
    void fetchStats();
  }, [fetchEvents, fetchStats]);

  // Run Risk Gate Check
  const handleEvaluateRisk = async (e: React.FormEvent) => {
    e.preventDefault();
    setRiskLoading(true);
    setRiskError(null);
    setRiskVerdict(null);

    let parsedParams: Record<string, unknown> = {};
    try {
      if (riskParamsJson.trim()) {
        parsedParams = JSON.parse(riskParamsJson);
      }
    } catch {
      setRiskError('Invalid JSON parameters format');
      setRiskLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/audit/risk-check`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          action_type: riskAction.trim(),
          target: riskTarget.trim() || undefined,
          params: parsedParams,
          user_prompt: riskPrompt.trim() || undefined,
        }),
      });

      if (!res.ok) {
        throw new Error(`Risk evaluation failed (${res.status})`);
      }

      const verdict = (await res.json()) as RiskCheckResponse;
      setRiskVerdict(verdict);
    } catch (err) {
      setRiskError(err instanceof Error ? err.message : 'Error during risk analysis');
    } finally {
      setRiskLoading(false);
    }
  };

  // Trigger GDPR / Compliance Export
  const handleExportAuditArchive = async () => {
    setExporting(true);
    setExportSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/audit/export`, {
        headers: authHeaders,
      });
      if (!res.ok) {
        throw new Error(`Export request failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `roxy_audit_archive_${new Date().toISOString().slice(0, 10)}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setExportSuccess('Audit archive exported successfully (GDPR & CCPA Compliant).');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="audit-studio">
      {/* Header */}
      <div className="audit-studio__header">
        <div className="audit-studio__header-left">
          {onBack && (
            <button className="audit-studio__back-btn" onClick={onBack}>
              <ArrowLeft size={16} /> Back to Chat
            </button>
          )}
          <h1 className="audit-studio__title">
            <ShieldCheck size={28} color="#10b981" />
            Audit, Security & Autonomous Activity Studio
          </h1>
          <p className="audit-studio__desc">
            Immutable 1-year append-only audit trail (§10.12), pre-execution risk gate verification
            (Security &amp; Privacy Agent), and real-time visibility into all autonomous actions.
          </p>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="audit-studio__stats-bar">
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Total Actions</span>
          <span className="audit-studio__stat-chip-val highlight">
            {stats?.total_events ?? events.length}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Actions Today</span>
          <span className="audit-studio__stat-chip-val">
            {stats?.today_events ?? 0}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">T3 High-Stakes</span>
          <span className="audit-studio__stat-chip-val danger">
            {stats?.by_tier?.T3 ?? 0}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Avg Latency</span>
          <span className="audit-studio__stat-chip-val">
            {stats?.avg_latency_ms ? `${stats.avg_latency_ms} ms` : '0 ms'}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Retention Policy</span>
          <span className="audit-studio__stat-chip-val highlight">
            365 Days
          </span>
        </div>
      </div>

      {!effectiveToken && (
        <div className="audit-studio__auth-banner" role="status">
          <span>ℹ️ You are viewing Audit Studio in guest mode. Autonomous security audits are logged ephemerally. Sign in with a verified account for 1-year immutable compliance retention.</span>
        </div>
      )}

      {error && (
        <div className="audit-studio__error-banner" role="alert">
          <span>⚠️ {error}</span>
          <button
            type="button"
            className="audit-studio__retry-btn"
            onClick={() => {
              void fetchEvents();
              void fetchStats();
            }}
          >
            ↻ Retry Connection
          </button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="audit-studio__tabs">
        <button
          className={`audit-studio__tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
          onClick={() => setActiveTab('timeline')}
        >
          <Activity size={16} /> Activity Timeline
        </button>
        <button
          className={`audit-studio__tab-btn ${activeTab === 'risk_gate' ? 'active' : ''}`}
          onClick={() => setActiveTab('risk_gate')}
        >
          <Lock size={16} /> Risk Gate Simulator
        </button>
        <button
          className={`audit-studio__tab-btn ${activeTab === 'compliance' ? 'active' : ''}`}
          onClick={() => setActiveTab('compliance')}
        >
          <Download size={16} /> Compliance &amp; Export
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#f87171', padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1.25rem' }}>
          {error}
        </div>
      )}

      {/* TAB 1: Activity Timeline */}
      {activeTab === 'timeline' && (
        <>
          <div className="audit-studio__filter-bar">
            <div className="audit-studio__search-box">
              <Search className="audit-studio__search-icon" size={16} />
              <input
                type="text"
                placeholder="Search action or query text..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="audit-studio__search-input"
              />
            </div>

            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="audit-studio__select"
            >
              <option value="all">All Agents</option>
              <option value="coordinator">Coordinator</option>
              <option value="coding">Coding Agent</option>
              <option value="browser">Browser Agent</option>
              <option value="finance">Finance Agent</option>
              <option value="memory">Memory Curator</option>
              <option value="email">Email Agent</option>
              <option value="automation">Automation Agent</option>
              <option value="study">Study Agent</option>
            </select>

            <select
              value={tierFilter}
              onChange={(e) => setTierFilter(e.target.value)}
              className="audit-studio__select"
            >
              <option value="all">All Tiers (T1/T2/T3)</option>
              <option value="T1">T1 (Auto-Run Safe)</option>
              <option value="T2">T2 (User Confirm)</option>
              <option value="T3">T3 (High-Stakes Block)</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="audit-studio__select"
            >
              <option value="all">All Statuses</option>
              <option value="ok">OK / Executed</option>
              <option value="caution">Caution</option>
              <option value="blocked">Blocked</option>
              <option value="error">Error</option>
            </select>

            <button
              className="audit-studio__btn"
              onClick={() => {
                void fetchEvents();
                void fetchStats();
              }}
              disabled={loading}
            >
              <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
            </button>
          </div>

          <div className="audit-studio__feed">
            {events.length === 0 ? (
              <div className="audit-studio__empty">
                <ShieldCheck size={48} className="audit-studio__empty-icon" />
                <h3>No Audit Events Found</h3>
                <p>No actions matching the active filters have been recorded yet.</p>
              </div>
            ) : (
              events.map((evt) => {
                const tierClass =
                  evt.approval_tier === 'T3'
                    ? 'tier-badge--t3'
                    : evt.approval_tier === 'T2'
                    ? 'tier-badge--t2'
                    : 'tier-badge--t1';

                const statusClass =
                  evt.status_code === 'error'
                    ? 'status-badge--error'
                    : evt.status_code === 'blocked'
                    ? 'status-badge--blocked'
                    : evt.status_code === 'caution'
                    ? 'status-badge--caution'
                    : 'status-badge--ok';

                const isExpanded = expandedId === evt.id;

                return (
                  <div key={evt.id} className="audit-card">
                    <div className="audit-card__header">
                      <div className="audit-card__badges">
                        <span className={`tier-badge ${tierClass}`}>
                          {evt.approval_tier}
                        </span>
                        <span className={`status-badge ${statusClass}`}>
                          {evt.status_code}
                        </span>
                        <span className="agent-badge">
                          {evt.agent_slug}
                        </span>
                        {evt.skill_slug && (
                          <span style={{ fontSize: '0.72rem', color: '#9ca3af', background: 'rgba(255,255,255,0.05)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>
                            {evt.skill_slug}
                          </span>
                        )}
                      </div>

                      <div className="audit-card__meta">
                        <span title="Execution Latency">
                          <Zap size={12} style={{ display: 'inline', marginRight: 3 }} />
                          {evt.latency_ms}ms
                        </span>
                        <span>
                          <Clock size={12} style={{ display: 'inline', marginRight: 3 }} />
                          {evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : 'Recent'}
                        </span>
                      </div>
                    </div>

                    <div className="audit-card__action-title">
                      {evt.action}
                    </div>

                    {evt.request_query && (
                      <div className="audit-card__query">
                        <strong>Query:</strong> {evt.request_query}
                      </div>
                    )}

                    {evt.response_summary && (
                      <div className="audit-card__summary">
                        {evt.response_summary}
                      </div>
                    )}

                    <button
                      className="audit-card__details-toggle"
                      onClick={() => setExpandedId(isExpanded ? null : evt.id)}
                    >
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      {isExpanded ? 'Hide Raw Details' : 'View Payload & Telemetry'}
                    </button>

                    {isExpanded && (
                      <pre className="audit-card__json">
                        {JSON.stringify(
                          {
                            id: evt.id,
                            trace_id: evt.trace_id,
                            approved_by: evt.approved_by,
                            model_used: evt.model_used,
                            provider: evt.provider,
                            decision: evt.decision,
                            details: evt.details,
                          },
                          null,
                          2
                        )}
                      </pre>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </>
      )}

      {/* TAB 2: Risk Gate & Policy Simulator */}
      {activeTab === 'risk_gate' && (
        <div className="audit-risk-gate">
          <div className="audit-risk-panel">
            <h3 className="audit-risk-panel__title">
              <Sliders size={18} color="#10b981" /> Pre-Execution Risk Evaluator
            </h3>
            <p className="audit-risk-panel__desc">
              Test how the Security &amp; Privacy Agent evaluates action requests against Approval Tiers
              (T1 Auto-run, T2 Confirm-tap, T3 PIN/Biometric/Block).
            </p>

            <form onSubmit={handleEvaluateRisk}>
              <div className="audit-form-group">
                <label className="audit-form-label">Action Name / Command</label>
                <input
                  type="text"
                  className="audit-form-input"
                  value={riskAction}
                  onChange={(e) => setRiskAction(e.target.value)}
                  placeholder="e.g. send_email, DROP TABLE users, web_search"
                  required
                />
              </div>

              <div className="audit-form-group">
                <label className="audit-form-label">Target Resource / Recipient</label>
                <input
                  type="text"
                  className="audit-form-input"
                  value={riskTarget}
                  onChange={(e) => setRiskTarget(e.target.value)}
                  placeholder="e.g. database_production, user@example.com"
                />
              </div>

              <div className="audit-form-group">
                <label className="audit-form-label">Stated User Prompt</label>
                <input
                  type="text"
                  className="audit-form-input"
                  value={riskPrompt}
                  onChange={(e) => setRiskPrompt(e.target.value)}
                  placeholder="User intent prompt"
                />
              </div>

              <div className="audit-form-group">
                <label className="audit-form-label">Action Parameters (JSON)</label>
                <textarea
                  className="audit-form-textarea"
                  value={riskParamsJson}
                  onChange={(e) => setRiskParamsJson(e.target.value)}
                />
              </div>

              {riskError && (
                <div style={{ color: '#f87171', fontSize: '0.85rem', marginBottom: '1rem' }}>
                  {riskError}
                </div>
              )}

              <button
                type="submit"
                className="audit-studio__btn audit-studio__btn--primary"
                disabled={riskLoading}
              >
                {riskLoading ? 'Evaluating Policy...' : 'Evaluate Pre-Execution Risk'}
              </button>
            </form>
          </div>

          <div className="audit-risk-panel">
            <h3 className="audit-risk-panel__title">
              <ShieldCheck size={18} color="#06b6d4" /> Risk Assessment Verdict
            </h3>
            <p className="audit-risk-panel__desc">
              Structured decision and approval gating generated by the policy analyzer.
            </p>

            {riskVerdict ? (
              <div
                className={`verdict-box ${
                  riskVerdict.risk_verdict === 'block'
                    ? 'verdict-box--block'
                    : riskVerdict.risk_verdict === 'caution'
                    ? 'verdict-box--caution'
                    : 'verdict-box--clear'
                }`}
              >
                <div
                  className={`verdict-title ${
                    riskVerdict.risk_verdict === 'block'
                      ? 'verdict-title--block'
                      : riskVerdict.risk_verdict === 'caution'
                      ? 'verdict-title--caution'
                      : 'verdict-title--clear'
                  }`}
                >
                  {riskVerdict.risk_verdict === 'block' && <XCircle size={20} />}
                  {riskVerdict.risk_verdict === 'caution' && <AlertTriangle size={20} />}
                  {riskVerdict.risk_verdict === 'clear' && <CheckCircle2 size={20} />}
                  Verdict: {riskVerdict.risk_verdict.toUpperCase()} (Required Tier: {riskVerdict.approval_tier})
                </div>

                <div style={{ fontSize: '0.9rem', color: '#e5e7eb' }}>
                  <strong>Policy Reason:</strong> {riskVerdict.reason}
                </div>

                <div style={{ fontSize: '0.85rem', color: '#d1d5db', background: 'rgba(0,0,0,0.2)', padding: '0.5rem', borderRadius: '6px' }}>
                  <strong>User Advisory:</strong> {riskVerdict.warning_to_user}
                </div>

                {riskVerdict.narrower_alternative && (
                  <div style={{ fontSize: '0.85rem', color: '#38bdf8' }}>
                    <strong>Safer Alternative:</strong> {riskVerdict.narrower_alternative}
                  </div>
                )}

                <div style={{ display: 'flex', gap: '1rem', fontSize: '0.78rem', color: '#9ca3af', marginTop: '0.5rem' }}>
                  <span>Blast Radius: <code>{riskVerdict.blast_radius}</code></span>
                  <span>Reversible: <code>{riskVerdict.is_reversible ? 'Yes' : 'No'}</code></span>
                  <span>Execution Gated: <code>{riskVerdict.blocking ? 'Blocked' : 'Allowed'}</code></span>
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '3rem 1rem', color: '#6b7280' }}>
                <Lock size={36} style={{ marginBottom: '0.75rem', opacity: 0.5 }} />
                <p>Enter action details on the left and click Evaluate to see the security decision.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: Compliance & Export */}
      {activeTab === 'compliance' && (
        <div className="audit-compliance">
          <div className="audit-policy-banner">
            <ShieldCheck size={28} className="audit-policy-banner__icon" />
            <div>
              <h4 className="audit-policy-banner__title">Immutable 1-Year Retention Guarantee (§10.12)</h4>
              <p className="audit-policy-banner__text">
                Under the ROXY Architecture Constitution (§3.6 &amp; §10.12), every autonomous action,
                skill execution, and tool invocation is recorded append-only. Modification and deletion
                endpoints are strictly prohibited by architecture. Audit logs are preserved for 365 days
                and fully portable under GDPR Article 20 and CCPA guidelines.
              </p>
            </div>
          </div>

          <div style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1.15rem', color: '#f3f4f6', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileCode size={18} color="#3b82f6" /> Portable Data Export
            </h3>
            <p style={{ fontSize: '0.88rem', color: '#9ca3af', marginBottom: '1.25rem' }}>
              Download a complete, machine-readable JSON export bundle containing all autonomous action
              records, latency benchmarks, and approval tier decisions associated with your account.
            </p>

            {exportSuccess && (
              <div style={{ color: '#34d399', fontSize: '0.9rem', marginBottom: '1rem' }}>
                ✓ {exportSuccess}
              </div>
            )}

            <button
              onClick={handleExportAuditArchive}
              className="audit-studio__btn audit-studio__btn--primary"
              disabled={exporting}
            >
              <Download size={16} /> {exporting ? 'Generating Export...' : 'Export Audit Trail (JSON)'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AuditStudio;
