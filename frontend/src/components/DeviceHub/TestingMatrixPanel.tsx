import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  Play,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Monitor,
  Smartphone,
  Cloud,
  Cpu,
  Layers,
  Clock,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Terminal,
  Activity,
} from 'lucide-react';

export interface MatrixTestResult {
  test_id: string;
  name: string;
  pillar: 'desktop' | 'mobile' | 'cloud' | 'mcp';
  target_platform: string;
  status: 'passed' | 'failed' | 'skipped' | 'running';
  duration_ms: number;
  assertions_passed: number;
  assertions_failed: number;
  details: Record<string, unknown>;
  error_message?: string | null;
  trace_id?: string | null;
  correlation_id?: string | null;
}

export interface PillarSummary {
  pillar: 'desktop' | 'mobile' | 'cloud' | 'mcp';
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  health_score: number;
  avg_latency_ms: number;
  tests: MatrixTestResult[];
}

export interface ScenarioStep {
  step_index: number;
  name: string;
  platform: 'desktop' | 'mobile' | 'cloud' | 'mcp';
  target: string;
  action: string;
  status: 'passed' | 'failed' | 'skipped' | 'running';
  duration_ms: number;
  payload_summary: Record<string, unknown>;
  verification_hash?: string | null;
  error_message?: string | null;
}

export interface ScenarioExecutionResult {
  scenario_id: string;
  name: string;
  success: boolean;
  total_duration_ms: number;
  steps: ScenarioStep[];
  trace_id: string;
  correlation_id: string;
  audit_block_hash: string;
}

export interface TestingMatrixReport {
  run_id: string;
  timestamp: string;
  overall_verdict: 'healthy' | 'degraded' | 'failing';
  total_tests: number;
  total_passed: number;
  total_failed: number;
  pillars: Record<string, PillarSummary>;
  scenarios: ScenarioExecutionResult[];
  audit_record_id: string;
  cryptographic_audit_hash: string;
}

export interface CrossPlatformScenarioMeta {
  scenario_id: string;
  name: string;
  description: string;
  pillars_involved: string[];
  step_count: number;
}

export interface TestingMatrixPanelProps {
  authHeaders: Record<string, string>;
  apiBase: string;
}

export const TestingMatrixPanel: React.FC<TestingMatrixPanelProps> = ({
  authHeaders,
  apiBase,
}) => {
  const [report, setReport] = useState<TestingMatrixReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningMatrix, setRunningMatrix] = useState(false);
  const [scenarios, setScenarios] = useState<CrossPlatformScenarioMeta[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('desktop_to_mobile_handoff');
  const [runningScenario, setRunningScenario] = useState(false);
  const [activeScenarioResult, setActiveScenarioResult] = useState<ScenarioExecutionResult | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [expandedPillar, setExpandedPillar] = useState<string | null>('desktop');

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(id);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Fetch or trigger matrix report
  const fetchReport = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/testing-matrix/report`, { headers: authHeaders });
      if (res.ok) {
        const data = (await res.json()) as TestingMatrixReport;
        setReport(data);
        if (data.scenarios && data.scenarios.length > 0) {
          setActiveScenarioResult(data.scenarios[0]);
        }
      }
    } catch {
      // background error handled gracefully
    } finally {
      setLoading(false);
    }
  }, [apiBase, authHeaders]);

  // Fetch available scenarios
  const fetchScenarios = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/testing-matrix/scenarios`, { headers: authHeaders });
      if (res.ok) {
        const data = (await res.json()) as CrossPlatformScenarioMeta[];
        setScenarios(data);
      }
    } catch {
      // background error
    }
  }, [apiBase, authHeaders]);

  useEffect(() => {
    void fetchReport();
    void fetchScenarios();
  }, [fetchReport, fetchScenarios]);

  // Run entire matrix
  const handleRunMatrix = async () => {
    setRunningMatrix(true);
    try {
      const res = await fetch(`${apiBase}/testing-matrix/run`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_scenarios: true }),
      });
      if (res.ok) {
        const data = (await res.json()) as TestingMatrixReport;
        setReport(data);
        if (data.scenarios && data.scenarios.length > 0) {
          setActiveScenarioResult(data.scenarios[0]);
        }
      }
    } catch {
      // ignore
    } finally {
      setRunningMatrix(false);
    }
  };

  // Run individual scenario
  const handleRunScenario = async (scenarioId: string) => {
    setRunningScenario(true);
    try {
      const res = await fetch(`${apiBase}/testing-matrix/scenarios/${scenarioId}/execute`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (res.ok) {
        const data = (await res.json()) as ScenarioExecutionResult;
        setActiveScenarioResult(data);
      }
    } catch {
      // ignore
    } finally {
      setRunningScenario(false);
    }
  };

  const getPillarIcon = (pillar: string) => {
    switch (pillar) {
      case 'desktop':
        return <Monitor size={20} color="#3b82f6" />;
      case 'mobile':
        return <Smartphone size={20} color="#10b981" />;
      case 'cloud':
        return <Cloud size={20} color="#8b5cf6" />;
      case 'mcp':
        return <Cpu size={20} color="#f59e0b" />;
      default:
        return <Layers size={20} color="#9ca3af" />;
    }
  };

  return (
    <div className="testing-matrix-panel">
      {/* Header Banner */}
      <div className="testing-matrix-header">
        <div className="testing-matrix-header__left">
          <div className="testing-matrix-header__title-row">
            <h2 className="testing-matrix-title">
              <ShieldCheck size={26} color="#10b981" />
              Multi-Platform Testing Matrix
            </h2>
            {report && (
              <span className={`matrix-verdict-chip ${report.overall_verdict}`}>
                {report.overall_verdict === 'healthy' && <CheckCircle2 size={14} />}
                {report.overall_verdict === 'degraded' && <AlertTriangle size={14} />}
                {report.overall_verdict === 'failing' && <XCircle size={14} />}
                {report.overall_verdict.toUpperCase()}
              </span>
            )}
          </div>
          <p className="testing-matrix-desc">
            End-to-end integration validation across Desktop, Mobile (Android/iOS), Cloud Workers, and
            MCP Connectors with cryptographically chained SHA-256 audit proof.
          </p>
        </div>

        <div className="testing-matrix-header__actions">
          <button
            className="matrix-btn matrix-btn--secondary"
            onClick={() => void fetchReport()}
            disabled={loading || runningMatrix}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
          </button>
          <button
            className="matrix-btn matrix-btn--primary"
            onClick={() => void handleRunMatrix()}
            disabled={runningMatrix}
          >
            <Play size={14} className={runningMatrix ? 'spin' : ''} />
            {runningMatrix ? 'Executing Testing Matrix...' : 'Run Full Testing Matrix'}
          </button>
        </div>
      </div>

      {/* Cryptographic Ledger Anchor Chip */}
      {report && (
        <div className="matrix-audit-bar">
          <div className="matrix-audit-meta">
            <span className="audit-meta-item">
              <strong>Run ID:</strong> <code>{report.run_id}</code>
            </span>
            <span className="audit-meta-item">
              <strong>Executed:</strong> {new Date(report.timestamp).toLocaleTimeString()}
            </span>
            <span className="audit-meta-item">
              <strong>Tests:</strong> {report.total_passed} / {report.total_tests} Passed
            </span>
          </div>
          <div className="matrix-audit-hash">
            <span className="hash-label">Ledger SHA-256 Proof:</span>
            <code className="hash-value">{report.cryptographic_audit_hash}</code>
            <button
              className="matrix-copy-btn"
              onClick={() => copyToClipboard(report.cryptographic_audit_hash, 'audit_hash')}
              title="Copy Hash"
            >
              {copiedHash === 'audit_hash' ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
            </button>
          </div>
        </div>
      )}

      {/* 4 Platform Pillars Grid */}
      <div className="matrix-pillars-grid">
        {(['desktop', 'mobile', 'cloud', 'mcp'] as const).map((pillarKey) => {
          const summary = report?.pillars?.[pillarKey];
          const isExpanded = expandedPillar === pillarKey;

          return (
            <div key={pillarKey} className={`matrix-pillar-card ${summary?.failed ? 'has-failures' : ''}`}>
              <div
                className="matrix-pillar-card__header"
                onClick={() => setExpandedPillar(isExpanded ? null : pillarKey)}
              >
                <div className="pillar-header-left">
                  {getPillarIcon(pillarKey)}
                  <div>
                    <h3 className="pillar-title">{pillarKey.toUpperCase()} PILLAR</h3>
                    <span className="pillar-sub">
                      {summary ? `${summary.passed}/${summary.total_tests} Tests Passed` : 'Pending execution'}
                    </span>
                  </div>
                </div>

                <div className="pillar-header-right">
                  <div className="pillar-health-chip">
                    <span className="health-score">{summary ? `${summary.health_score}%` : '—'}</span>
                    <span className="latency-label">{summary ? `${summary.avg_latency_ms}ms` : ''}</span>
                  </div>
                  <button className="pillar-expand-toggle">
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>
              </div>

              {/* Expandable test list */}
              {isExpanded && summary && (
                <div className="matrix-pillar-card__body">
                  <div className="pillar-tests-list">
                    {summary.tests.map((t) => (
                      <div key={t.test_id} className={`pillar-test-row ${t.status}`}>
                        <div className="test-row-status">
                          {t.status === 'passed' ? (
                            <CheckCircle2 size={16} color="#10b981" />
                          ) : (
                            <XCircle size={16} color="#ef4444" />
                          )}
                        </div>
                        <div className="test-row-info">
                          <span className="test-name">{t.name}</span>
                          <span className="test-target">{t.target_platform}</span>
                        </div>
                        <div className="test-row-metrics">
                          <span className="test-duration">{t.duration_ms}ms</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Cross-Platform Multi-Hop Scenarios Section */}
      <div className="matrix-scenarios-section">
        <div className="scenarios-section-header">
          <div className="scenarios-header-left">
            <h3 className="section-title">
              <Activity size={20} color="#10b981" />
              Cross-Platform Multi-Hop E2E Scenarios
            </h3>
            <p className="section-sub">
              Live multi-platform workflows testing autonomous state handoff, credential redaction, and
              distributed synchronization under the Zero Simulation Doctrine.
            </p>
          </div>

          <div className="scenarios-controls">
            <select
              value={selectedScenarioId}
              onChange={(e) => setSelectedScenarioId(e.target.value)}
              className="scenario-select"
            >
              {scenarios.map((sc) => (
                <option key={sc.scenario_id} value={sc.scenario_id}>
                  {sc.name} ({sc.step_count} steps)
                </option>
              ))}
            </select>
            <button
              className="matrix-btn matrix-btn--primary"
              onClick={() => void handleRunScenario(selectedScenarioId)}
              disabled={runningScenario}
            >
              <Terminal size={14} />
              {runningScenario ? 'Running Scenario...' : 'Execute Scenario'}
            </button>
          </div>
        </div>

        {/* Active Scenario Flow Visualizer */}
        {activeScenarioResult && (
          <div className="scenario-visualizer-card">
            <div className="scenario-card-header">
              <div className="scenario-title-col">
                <h4>{activeScenarioResult.name}</h4>
                <div className="scenario-tags">
                  <span className={`status-badge ${activeScenarioResult.success ? 'passed' : 'failed'}`}>
                    {activeScenarioResult.success ? '✓ VERIFIED' : '✗ FAILED'}
                  </span>
                  <span className="duration-tag">
                    <Clock size={12} /> {activeScenarioResult.total_duration_ms} ms
                  </span>
                  <span className="trace-tag">Trace: {activeScenarioResult.trace_id.slice(0, 16)}...</span>
                </div>
              </div>

              <div className="scenario-hash-box">
                <span className="hash-label">Audit Block Hash:</span>
                <code className="hash-code">{activeScenarioResult.audit_block_hash.slice(0, 24)}...</code>
                <button
                  className="matrix-copy-btn"
                  onClick={() =>
                    copyToClipboard(activeScenarioResult.audit_block_hash, 'scenario_hash')
                  }
                >
                  {copiedHash === 'scenario_hash' ? (
                    <Check size={14} color="#10b981" />
                  ) : (
                    <Copy size={14} />
                  )}
                </button>
              </div>
            </div>

            {/* Stepper Flow */}
            <div className="scenario-steps-flow">
              {activeScenarioResult.steps.map((step, idx) => (
                <div key={step.step_index} className="scenario-step-item">
                  <div className="step-badge-col">
                    <span className={`step-circle ${step.status}`}>{step.step_index}</span>
                    {idx < activeScenarioResult.steps.length - 1 && <div className="step-line" />}
                  </div>

                  <div className="step-content-card">
                    <div className="step-content-header">
                      <div className="step-platform-badge">
                        {getPillarIcon(step.platform)}
                        <span>{step.platform.toUpperCase()}</span>
                      </div>
                      <span className="step-name">{step.name}</span>
                      <span className="step-target">Target: {step.target}</span>
                      <span className="step-time">{step.duration_ms}ms</span>
                    </div>

                    <div className="step-action-desc">
                      <code>{step.action}</code>
                    </div>

                    {step.verification_hash && (
                      <div className="step-verification-row">
                        <span className="v-label">Verification Hash:</span>
                        <code className="v-hash">{step.verification_hash}</code>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
