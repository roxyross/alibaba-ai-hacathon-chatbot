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
  Sliders,
  ChevronDown,
  ChevronUp,
  FileCode,
  Lock,
  Activity,
  Layers,
  Check,
  Copy,
  Terminal,
  Eye,
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

// Phase 22 Observability Types
export interface AuditRecord {
  sequence_number: number;
  record_id: string;
  timestamp: string;
  correlation_id: string;
  trace_id: string;
  actor_id: string;
  client_ip: string;
  action_type: string;
  category: string;
  status: string;
  risk_tier: string;
  risk_score: number;
  confirmation_id?: string | null;
  payload_summary: Record<string, unknown>;
  duration_ms: number;
  previous_hash: string;
  record_hash: string;
}

export interface HashChainVerification {
  is_valid: boolean;
  total_records: number;
  genesis_hash: string;
  head_hash: string;
  tampered_record_id?: string | null;
  tampered_sequence?: number | null;
  reason: string;
  verified_at: string;
}

export interface TraceSummary {
  trace_id: string;
  correlation_id: string;
  root_span_name: string;
  duration_ms: number;
  status: string;
  span_count: number;
  created_at: string;
}

export interface SpanDetail {
  span_id: string;
  parent_span_id?: string | null;
  name: string;
  offset_ms: number;
  duration_ms: number;
  status: string;
  attributes: Record<string, unknown>;
  error_message?: string | null;
}

export interface TraceDetail {
  trace_id: string;
  correlation_id: string;
  root_span_name: string;
  duration_ms: number;
  status: string;
  attributes: Record<string, unknown>;
  created_at: string;
  spans: SpanDetail[];
}

export interface ObservabilityMetrics {
  total_audit_events: number;
  ledger_head_hash: string;
  hash_chain_valid: boolean;
  active_traces_in_memory: number;
  zero_leakage_redactions: Record<string, number>;
  actions_by_status: Record<string, number>;
  actions_by_tier: Record<string, number>;
  avg_action_latency_ms: number;
}

export interface AuditStudioProps {
  onBack?: () => void;
  accessToken?: string | null;
}

export const AuditStudio: React.FC<AuditStudioProps> = ({ onBack, accessToken }) => {
  const [activeTab, setActiveTab] = useState<
    'timeline' | 'immutable_ledger' | 'distributed_traces' | 'zero_leakage' | 'risk_gate' | 'compliance'
  >('timeline');

  // Timeline State
  const [events, setEvents] = useState<AuditLogItem[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters for Timeline
  const [searchQuery, setSearchQuery] = useState('');
  const [agentFilter, setAgentFilter] = useState('all');
  const [tierFilter, setTierFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Phase 22: Immutable Ledger State
  const [ledgerRecords, setLedgerRecords] = useState<AuditRecord[]>([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [verification, setVerification] = useState<HashChainVerification | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [ledgerFilterAction, setLedgerFilterAction] = useState('');
  const [ledgerFilterStatus, setLedgerFilterStatus] = useState('all');
  const [expandedRecordSeq, setExpandedRecordSeq] = useState<number | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Phase 22: Distributed Traces State
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [tracesLoading, setTracesLoading] = useState(false);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedTraceDetail, setSelectedTraceDetail] = useState<TraceDetail | null>(null);
  const [traceDetailLoading, setTraceDetailLoading] = useState(false);

  // Phase 22: Zero Leakage & Metrics State
  const [obsMetrics, setObsMetrics] = useState<ObservabilityMetrics | null>(null);
  const [leakProbeText, setLeakProbeText] = useState(
    'Payment card 4532-0150-1234-5671 and OpenAI sk-proj-1234567890abcdef1234567890abcdef1234567890'
  );
  const [leakProbePayloadJson, setLeakProbePayloadJson] = useState(
    '{\n  "db_uri": "postgresql://admin:super_secret_pw@db.internal:5432/main",\n  "api_key": "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P67"\n}'
  );
  const [leakProbeResult, setLeakProbeResult] = useState<{
    sanitized_text: string | null;
    sanitized_payload: Record<string, unknown>;
    recorded_audit_id: string;
    secrets_intercepted: number;
  } | null>(null);
  const [probeLoading, setProbeLoading] = useState(false);

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

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(id);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Fetch Stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/audit/stats`, { headers: authHeaders });
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
      const params = new URLSearchParams({ limit: '100' });
      if (agentFilter !== 'all') params.append('agent_slug', agentFilter);
      if (tierFilter !== 'all') params.append('approval_tier', tierFilter);
      if (statusFilter !== 'all') params.append('status_code', statusFilter);
      if (searchQuery.trim()) params.append('query', searchQuery.trim());

      const res = await fetch(`${API_BASE}/audit/events?${params.toString()}`, {
        headers: authHeaders,
      });

      if (!res.ok) {
        throw new Error(`Failed to load audit events (${res.status})`);
      }

      const data = await res.json();
      setEvents(data.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error fetching audit logs');
    } finally {
      setLoading(false);
    }
  }, [authHeaders, agentFilter, tierFilter, statusFilter, searchQuery]);

  // Phase 22: Fetch Immutable Ledger
  const fetchLedger = useCallback(async () => {
    setLedgerLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (ledgerFilterAction.trim()) params.append('action_type', ledgerFilterAction.trim());
      if (ledgerFilterStatus !== 'all') params.append('status', ledgerFilterStatus);

      const res = await fetch(`${API_BASE}/observability/audit/ledger?${params.toString()}`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as AuditRecord[];
        setLedgerRecords(data);
      }
    } catch {
      // background error
    } finally {
      setLedgerLoading(false);
    }
  }, [authHeaders, ledgerFilterAction, ledgerFilterStatus]);

  // Phase 22: Cryptographically Verify Hash Chain
  const verifyHashChain = useCallback(async () => {
    setVerifying(true);
    try {
      const res = await fetch(`${API_BASE}/observability/audit/verify`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as HashChainVerification;
        setVerification(data);
      }
    } catch {
      // ignore
    } finally {
      setVerifying(false);
    }
  }, [authHeaders]);

  // Phase 22: Fetch Traces
  const fetchTraces = useCallback(async () => {
    setTracesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/observability/traces?limit=30`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as TraceSummary[];
        setTraces(data);
        if (data.length > 0 && !selectedTraceId) {
          setSelectedTraceId(data[0].trace_id);
        }
      }
    } catch {
      // ignore
    } finally {
      setTracesLoading(false);
    }
  }, [authHeaders, selectedTraceId]);

  // Phase 22: Fetch Specific Trace Details
  const fetchTraceDetail = useCallback(async (traceId: string) => {
    setTraceDetailLoading(true);
    try {
      const res = await fetch(`${API_BASE}/observability/traces/${traceId}`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as TraceDetail;
        setSelectedTraceDetail(data);
      }
    } catch {
      // ignore
    } finally {
      setTraceDetailLoading(false);
    }
  }, [authHeaders]);

  // Phase 22: Fetch Observability Metrics
  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/observability/metrics`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as ObservabilityMetrics;
        setObsMetrics(data);
      }
    } catch {
      // ignore
    }
  }, [authHeaders]);

  // Execute Security Leak Probe
  const handleExecuteLeakProbe = async () => {
    setProbeLoading(true);
    try {
      let parsedPayload = {};
      try {
        parsedPayload = JSON.parse(leakProbePayloadJson);
      } catch {
        parsedPayload = { raw_payload: leakProbePayloadJson };
      }

      const res = await fetch(`${API_BASE}/observability/test-leak-probe`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          test_text: leakProbeText,
          test_payload: parsedPayload,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setLeakProbeResult(data);
        void fetchMetrics();
        void fetchLedger();
      }
    } catch {
      // ignore
    } finally {
      setProbeLoading(false);
    }
  };

  // Export Ledger (JSON or CSV)
  const handleExportLedger = async (format: 'json' | 'csv') => {
    try {
      const res = await fetch(`${API_BASE}/observability/audit/export`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ format }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `roxy_immutable_ledger_${Date.now()}.${format}`);
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch {
      // ignore
    }
  };

  // Initial Load & Tab Shifts
  useEffect(() => {
    void fetchStats();
    void fetchEvents();
    void fetchLedger();
    void verifyHashChain();
    void fetchMetrics();
  }, [fetchStats, fetchEvents, fetchLedger, verifyHashChain, fetchMetrics]);

  useEffect(() => {
    if (activeTab === 'distributed_traces') {
      void fetchTraces();
    } else if (activeTab === 'immutable_ledger') {
      void fetchLedger();
      void verifyHashChain();
    } else if (activeTab === 'zero_leakage') {
      void fetchMetrics();
    }
  }, [activeTab, fetchTraces, fetchLedger, verifyHashChain, fetchMetrics]);

  useEffect(() => {
    if (selectedTraceId) {
      void fetchTraceDetail(selectedTraceId);
    }
  }, [selectedTraceId, fetchTraceDetail]);

  // Risk Simulator
  const handleEvaluateRisk = async () => {
    setRiskLoading(true);
    setRiskError(null);
    setRiskVerdict(null);
    try {
      let paramsObj: Record<string, unknown> = {};
      try {
        paramsObj = JSON.parse(riskParamsJson);
      } catch {
        paramsObj = { raw: riskParamsJson };
      }

      const res = await fetch(`${API_BASE}/audit/risk-check`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          action: riskAction,
          target_resource: riskTarget,
          payload_summary: paramsObj,
          user_prompt: riskPrompt,
        }),
      });

      if (!res.ok) throw new Error(`Risk evaluation failed (${res.status})`);
      const verdict = (await res.json()) as RiskCheckResponse;
      setRiskVerdict(verdict);
    } catch (err) {
      setRiskError(err instanceof Error ? err.message : 'Error during risk analysis');
    } finally {
      setRiskLoading(false);
    }
  };

  // Compliance Export
  const handleExportAuditArchive = async () => {
    setExporting(true);
    setExportSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/audit/export`, { headers: authHeaders });
      if (!res.ok) throw new Error(`Export request failed (${res.status})`);
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
            Audit, Security &amp; Observability Studio
          </h1>
          <p className="audit-studio__desc">
            Enterprise observability with Correlation IDs, cryptographically chained immutable ledger
            (SHA-256), and guaranteed Zero Credential Leakage across logs and telemetry.
          </p>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="audit-studio__stats-bar">
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Ledger Blocks</span>
          <span className="audit-studio__stat-chip-val highlight">
            {obsMetrics?.total_audit_events ?? stats?.total_events ?? ledgerRecords.length}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Cryptographic Integrity</span>
          <span className={`audit-studio__stat-chip-val ${verification?.is_valid ? 'success' : 'danger'}`}>
            {verification?.is_valid ? '✓ Verified (SHA-256)' : '⚠️ Compromised'}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Secrets Masked</span>
          <span className="audit-studio__stat-chip-val highlight">
            {obsMetrics?.zero_leakage_redactions?.total ?? 0}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Active Traces</span>
          <span className="audit-studio__stat-chip-val">
            {obsMetrics?.active_traces_in_memory ?? traces.length}
          </span>
        </div>
        <div className="audit-studio__stat-chip">
          <span className="audit-studio__stat-chip-label">Avg Execution</span>
          <span className="audit-studio__stat-chip-val">
            {obsMetrics?.avg_action_latency_ms ? `${obsMetrics.avg_action_latency_ms} ms` : '0 ms'}
          </span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="audit-studio__tabs">
        <button
          className={`audit-studio__tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
          onClick={() => setActiveTab('timeline')}
        >
          <Activity size={16} /> Activity Timeline
        </button>
        <button
          className={`audit-studio__tab-btn ${activeTab === 'immutable_ledger' ? 'active' : ''}`}
          onClick={() => setActiveTab('immutable_ledger')}
        >
          <Layers size={16} /> Immutable Ledger (SHA-256)
        </button>
        <button
          className={`audit-studio__tab-btn ${activeTab === 'distributed_traces' ? 'active' : ''}`}
          onClick={() => setActiveTab('distributed_traces')}
        >
          <Clock size={16} /> Distributed Traces
        </button>
        <button
          className={`audit-studio__tab-btn ${activeTab === 'zero_leakage' ? 'active' : ''}`}
          onClick={() => setActiveTab('zero_leakage')}
        >
          <Lock size={16} /> Zero Credential Leakage
        </button>
        <button
          className={`audit-studio__tab-btn ${activeTab === 'risk_gate' ? 'active' : ''}`}
          onClick={() => setActiveTab('risk_gate')}
        >
          <Sliders size={16} /> Risk Gate Simulator
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
                const isExpanded = expandedId === evt.id;
                return (
                  <div key={evt.id} className="audit-card">
                    <div className="audit-card__header">
                      <div className="audit-card__badges">
                        <span className={`tier-badge tier-badge--${evt.approval_tier.toLowerCase()}`}>
                          {evt.approval_tier}
                        </span>
                        <span className={`status-badge status-badge--${evt.status_code.toLowerCase()}`}>
                          {evt.status_code}
                        </span>
                        <span className="audit-card__action">{evt.action}</span>
                      </div>
                      <div className="audit-card__meta">
                        <span>{evt.agent_slug}</span>
                        <span>{evt.latency_ms}ms</span>
                        <span>{evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : ''}</span>
                        <button
                          className="audit-card__expand-btn"
                          onClick={() => setExpandedId(isExpanded ? null : evt.id)}
                        >
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="audit-card__details">
                        <div className="audit-card__detail-row">
                          <strong>Trace ID:</strong> <code>{evt.trace_id}</code>
                        </div>
                        {evt.request_query && (
                          <div className="audit-card__detail-row">
                            <strong>Query:</strong> {evt.request_query}
                          </div>
                        )}
                        {evt.response_summary && (
                          <div className="audit-card__detail-row">
                            <strong>Summary:</strong> {evt.response_summary}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </>
      )}

      {/* TAB 2: Immutable Ledger (SHA-256 Cryptographic Hash Chain) */}
      {activeTab === 'immutable_ledger' && (
        <div className="audit-ledger-container">
          {/* Cryptographic Verification Banner */}
          <div className="audit-verification-card">
            <div className="audit-verification-card__status">
              {verification?.is_valid ? (
                <div className="audit-verification-card__badge valid">
                  <CheckCircle2 size={24} color="#10b981" />
                  <div>
                    <h4>Cryptographic Hash Chain: VERIFIED</h4>
                    <p>{verification?.reason || 'Continuous SHA-256 merkle links intact.'}</p>
                  </div>
                </div>
              ) : (
                <div className="audit-verification-card__badge invalid">
                  <AlertTriangle size={24} color="#ef4444" />
                  <div>
                    <h4>Hash Chain Integrity: COMPROMISED</h4>
                    <p>{verification?.reason || 'Tampering detected in sequential hash chain.'}</p>
                  </div>
                </div>
              )}

              <div className="audit-verification-card__actions">
                <button
                  className="audit-studio__btn"
                  onClick={() => void verifyHashChain()}
                  disabled={verifying}
                >
                  <RefreshCw size={14} className={verifying ? 'spin' : ''} />
                  {verifying ? 'Recalculating Proof...' : 'Verify Hash Chain'}
                </button>
                <button
                  className="audit-studio__btn"
                  onClick={() => void handleExportLedger('json')}
                >
                  <Download size={14} /> Export JSON
                </button>
                <button
                  className="audit-studio__btn"
                  onClick={() => void handleExportLedger('csv')}
                >
                  <Download size={14} /> Export CSV
                </button>
              </div>
            </div>

            <div className="audit-verification-card__hashes">
              <div className="hash-box">
                <span className="hash-label">Chain Head Hash</span>
                <code className="hash-value">
                  {verification?.head_hash || 'Calculating...'}
                </code>
                <button
                  className="hash-copy-btn"
                  onClick={() => copyToClipboard(verification?.head_hash || '', 'head')}
                >
                  {copiedHash === 'head' ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                </button>
              </div>
            </div>
          </div>

          {/* Ledger Filters */}
          <div className="audit-studio__controls" style={{ marginBottom: '1rem' }}>
            <div className="audit-studio__search">
              <Search size={16} />
              <input
                type="text"
                placeholder="Filter by action type (e.g. tool_call, auth_login)..."
                value={ledgerFilterAction}
                onChange={(e) => setLedgerFilterAction(e.target.value)}
                className="audit-studio__input"
              />
            </div>
            <div className="audit-studio__filters">
              <select
                value={ledgerFilterStatus}
                onChange={(e) => setLedgerFilterStatus(e.target.value)}
                className="audit-studio__select"
              >
                <option value="all">All Statuses</option>
                <option value="success">Success</option>
                <option value="error">Error</option>
                <option value="blocked">Blocked</option>
                <option value="denied">Denied</option>
              </select>
              <button
                className="audit-studio__btn"
                onClick={() => void fetchLedger()}
                disabled={ledgerLoading}
              >
                <RefreshCw size={14} className={ledgerLoading ? 'spin' : ''} /> Filter
              </button>
            </div>
          </div>

          {/* Ledger Table */}
          <div className="audit-ledger-table-wrap">
            <table className="audit-ledger-table">
              <thead>
                <tr>
                  <th>Seq #</th>
                  <th>Timestamp</th>
                  <th>Action Type</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Risk Tier</th>
                  <th>Correlation ID</th>
                  <th>Block SHA-256 Hash</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {ledgerRecords.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '2rem', color: '#9ca3af' }}>
                      {ledgerLoading ? 'Loading ledger blocks...' : 'No ledger blocks found.'}
                    </td>
                  </tr>
                ) : (
                  ledgerRecords.map((r) => {
                    const isExpanded = expandedRecordSeq === r.sequence_number;
                    return (
                      <React.Fragment key={r.record_id}>
                        <tr className="audit-ledger-row">
                          <td>
                            <span className="seq-badge">#{String(r.sequence_number).padStart(4, '0')}</span>
                          </td>
                          <td style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
                            {new Date(r.timestamp).toLocaleTimeString()}
                          </td>
                          <td>
                            <strong>{r.action_type}</strong>
                          </td>
                          <td>
                            <span className="category-tag">{r.category}</span>
                          </td>
                          <td>
                            <span className={`status-pill ${r.status}`}>
                              {r.status}
                            </span>
                          </td>
                          <td>
                            <span className={`tier-badge tier-badge--${r.risk_tier.toLowerCase()}`}>
                              {r.risk_tier.toUpperCase()} ({r.risk_score})
                            </span>
                          </td>
                          <td>
                            <code className="corr-id">{r.correlation_id.slice(0, 14)}...</code>
                          </td>
                          <td>
                            <code className="hash-pill" title={r.record_hash}>
                              {r.record_hash.slice(0, 10)}...{r.record_hash.slice(-6)}
                            </code>
                          </td>
                          <td>
                            <button
                              className="inspect-btn"
                              onClick={() => setExpandedRecordSeq(isExpanded ? null : r.sequence_number)}
                            >
                              <Eye size={14} />
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="audit-ledger-details-row">
                            <td colSpan={9}>
                              <div className="ledger-expanded-box">
                                <div className="ledger-expanded-grid">
                                  <div>
                                    <strong>Previous Hash:</strong>
                                    <code>{r.previous_hash}</code>
                                  </div>
                                  <div>
                                    <strong>Record Hash:</strong>
                                    <code>{r.record_hash}</code>
                                  </div>
                                  <div>
                                    <strong>Trace ID:</strong>
                                    <code>{r.trace_id}</code>
                                  </div>
                                  <div>
                                    <strong>Actor ID:</strong>
                                    <code>{r.actor_id}</code>
                                  </div>
                                </div>
                                <div className="payload-box">
                                  <strong>Sanitized Payload Summary (Zero Leakage Enforced):</strong>
                                  <pre>{JSON.stringify(r.payload_summary, null, 2)}</pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: Distributed Traces (Waterfall Inspector) */}
      {activeTab === 'distributed_traces' && (
        <div className="traces-layout">
          {/* Traces Sidebar */}
          <div className="traces-sidebar">
            <div className="traces-sidebar__header">
              <h3>Recent Traces</h3>
              <button
                className="audit-studio__btn"
                onClick={() => void fetchTraces()}
                disabled={tracesLoading}
              >
                <RefreshCw size={14} className={tracesLoading ? 'spin' : ''} />
              </button>
            </div>
            <div className="traces-list">
              {traces.length === 0 ? (
                <div style={{ padding: '1rem', color: '#9ca3af', textAlign: 'center' }}>
                  No traces recorded in active window.
                </div>
              ) : (
                traces.map((t) => (
                  <div
                    key={t.trace_id}
                    className={`trace-card ${selectedTraceId === t.trace_id ? 'active' : ''}`}
                    onClick={() => setSelectedTraceId(t.trace_id)}
                  >
                    <div className="trace-card__top">
                      <span className="trace-card__name">{t.root_span_name}</span>
                      <span className={`status-pill ${t.status}`}>{t.status}</span>
                    </div>
                    <div className="trace-card__bottom">
                      <span>{t.duration_ms} ms</span>
                      <span>{t.span_count} spans</span>
                      <span>{new Date(t.created_at).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Trace Detail & Waterfall */}
          <div className="trace-detail-panel">
            {traceDetailLoading ? (
              <div style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>
                Loading trace waterfall...
              </div>
            ) : selectedTraceDetail ? (
              <div>
                <div className="trace-detail-header">
                  <div>
                    <h2>{selectedTraceDetail.root_span_name}</h2>
                    <div className="trace-meta-ids">
                      <span>Trace ID: <code>{selectedTraceDetail.trace_id}</code></span>
                      <span>Correlation ID: <code>{selectedTraceDetail.correlation_id}</code></span>
                      <span>Total: <strong>{selectedTraceDetail.duration_ms} ms</strong></span>
                    </div>
                  </div>
                </div>

                {/* Waterfall Visualizer */}
                <div className="waterfall-container">
                  <h4>Waterfall Span Breakdown</h4>
                  <div className="waterfall-chart">
                    {selectedTraceDetail.spans.map((s) => {
                      const totalTraceMs = Math.max(selectedTraceDetail.duration_ms, 1.0);
                      const leftPercent = Math.min(100, (s.offset_ms / totalTraceMs) * 100);
                      const widthPercent = Math.max(3, Math.min(100 - leftPercent, (s.duration_ms / totalTraceMs) * 100));

                      return (
                        <div key={s.span_id} className="waterfall-row">
                          <div className="waterfall-label">
                            <span className="span-name">{s.name}</span>
                            <span className="span-duration">{s.duration_ms} ms</span>
                          </div>
                          <div className="waterfall-timeline">
                            <div
                              className={`waterfall-bar ${s.status}`}
                              style={{
                                left: `${leftPercent}%`,
                                width: `${widthPercent}%`,
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ padding: '3rem', textAlign: 'center', color: '#9ca3af' }}>
                Select a trace on the left to inspect waterfall spans.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: Zero Credential Leakage & Probe */}
      {activeTab === 'zero_leakage' && (
        <div className="zero-leakage-container">
          <div className="leak-metrics-grid">
            <div className="leak-metric-card">
              <span className="metric-title">Total Secrets Scrubbed</span>
              <span className="metric-value gradient">
                {obsMetrics?.zero_leakage_redactions?.total ?? 0}
              </span>
              <span className="metric-sub">100% Intercepted before storage</span>
            </div>
            <div className="leak-metric-card">
              <span className="metric-title">API Keys Scrubbed</span>
              <span className="metric-value">
                {obsMetrics?.zero_leakage_redactions?.api_keys ?? 0}
              </span>
              <span className="metric-sub">OpenAI, Gemini, Anthropic, Stripe</span>
            </div>
            <div className="leak-metric-card">
              <span className="metric-title">Cards &amp; Accounts</span>
              <span className="metric-value">
                {obsMetrics?.zero_leakage_redactions?.cards ?? 0}
              </span>
              <span className="metric-sub">ISO Luhn &amp; IBAN checksum validated</span>
            </div>
            <div className="leak-metric-card">
              <span className="metric-title">Passwords &amp; DB URIs</span>
              <span className="metric-value">
                {obsMetrics?.zero_leakage_redactions?.passwords ?? 0}
              </span>
              <span className="metric-sub">Database strings &amp; Auth Tokens</span>
            </div>
          </div>

          {/* Interactive Security Probe */}
          <div className="security-probe-card">
            <div className="security-probe-header">
              <h3>
                <Lock size={20} color="#10b981" />
                Live Security Leak Probe Simulator
              </h3>
              <p>
                Inject raw credentials or sensitive cards to verify that Roxy's Zero Leakage engine
                redacts values before recording in the immutable SHA-256 audit ledger.
              </p>
            </div>

            <div className="probe-inputs">
              <div className="probe-input-group">
                <label>Test Log / Query String:</label>
                <textarea
                  value={leakProbeText}
                  onChange={(e) => setLeakProbeText(e.target.value)}
                  rows={3}
                  className="probe-textarea"
                />
              </div>

              <div className="probe-input-group">
                <label>Test JSON Payload:</label>
                <textarea
                  value={leakProbePayloadJson}
                  onChange={(e) => setLeakProbePayloadJson(e.target.value)}
                  rows={4}
                  className="probe-textarea code"
                />
              </div>

              <button
                className="audit-studio__btn audit-studio__btn--primary"
                onClick={() => void handleExecuteLeakProbe()}
                disabled={probeLoading}
              >
                <Terminal size={14} /> {probeLoading ? 'Analyzing & Sanitizing...' : 'Execute Security Probe'}
              </button>
            </div>

            {leakProbeResult && (
              <div className="probe-result-box">
                <div className="probe-result-header">
                  <CheckCircle2 size={18} color="#10b981" />
                  <strong>Zero Leakage Verified: {leakProbeResult.secrets_intercepted} Secrets Intercepted</strong>
                  <span className="audit-id-chip">Ledger ID: {leakProbeResult.recorded_audit_id}</span>
                </div>
                <div className="probe-result-body">
                  <div>
                    <strong>Sanitized String:</strong>
                    <pre>{leakProbeResult.sanitized_text}</pre>
                  </div>
                  <div>
                    <strong>Sanitized JSON Output:</strong>
                    <pre>{JSON.stringify(leakProbeResult.sanitized_payload, null, 2)}</pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 5: Risk Gate Simulator */}
      {activeTab === 'risk_gate' && (
        <div className="audit-risk-gate">
          <div className="audit-risk-gate__form">
            <h3 style={{ fontSize: '1.1rem', color: '#f3f4f6', marginBottom: '1rem' }}>
              Simulate Action Risk Evaluation
            </h3>

            <div className="audit-form-group">
              <label>Action Type</label>
              <select
                value={riskAction}
                onChange={(e) => setRiskAction(e.target.value)}
                className="audit-studio__select"
              >
                <option value="send_email">send_email (External Comms)</option>
                <option value="financial_transfer">financial_transfer (High Impact)</option>
                <option value="file_write">file_write (System Modification)</option>
                <option value="code_execution">code_execution (Execution Sandbox)</option>
                <option value="read_profile">read_profile (Read-Only Safe)</option>
              </select>
            </div>

            <div className="audit-form-group">
              <label>Target Resource / Recipient</label>
              <input
                type="text"
                value={riskTarget}
                onChange={(e) => setRiskTarget(e.target.value)}
                className="audit-studio__input"
              />
            </div>

            <div className="audit-form-group">
              <label>User Prompt Context</label>
              <textarea
                value={riskPrompt}
                onChange={(e) => setRiskPrompt(e.target.value)}
                className="audit-studio__textarea"
                rows={2}
              />
            </div>

            <div className="audit-form-group">
              <label>Action Parameters (JSON)</label>
              <textarea
                value={riskParamsJson}
                onChange={(e) => setRiskParamsJson(e.target.value)}
                className="audit-studio__textarea"
                rows={3}
              />
            </div>

            <button
              onClick={handleEvaluateRisk}
              className="audit-studio__btn audit-studio__btn--primary"
              disabled={riskLoading}
            >
              <Lock size={16} /> {riskLoading ? 'Analyzing...' : 'Evaluate Pre-Execution Risk'}
            </button>
          </div>

          <div className="audit-risk-gate__result">
            {riskError && (
              <div className="audit-error-banner" style={{ margin: '1rem', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <AlertTriangle size={18} /> {riskError}
              </div>
            )}
            {riskVerdict ? (
              <div className="risk-verdict-card">
                <div className={`risk-verdict-card__verdict risk-verdict--${riskVerdict.risk_verdict}`}>
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

      {/* TAB 6: Compliance & Export */}
      {activeTab === 'compliance' && (
        <div className="audit-compliance">
          <div className="audit-policy-banner">
            <ShieldCheck size={28} className="audit-policy-banner__icon" />
            <div>
              <h4 className="audit-policy-banner__title">Immutable 1-Year Retention Guarantee (§10.12)</h4>
              <p className="audit-policy-banner__text">
                Under the ROXY Architecture Constitution (§3.6 &amp; §10.12), every autonomous action,
                skill execution, and tool invocation is recorded append-only with cryptographic SHA-256
                hash chaining. Audit logs are preserved for 365 days and fully portable under GDPR Article 20
                and CCPA guidelines.
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
