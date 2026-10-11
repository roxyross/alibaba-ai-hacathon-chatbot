import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Play,
  CheckCircle,
  KeyRound,
  UserCheck,
  Zap,
} from 'lucide-react';
import type {
  RiskMatrixConfig,
  RiskEvaluationResult,
  RiskTier,
} from './types';

interface RiskMatrixPanelProps {
  accessToken?: string | null;
  onSelectActionForConfirmation?: (evalResult: RiskEvaluationResult, payload: any) => void;
  initialConfig?: RiskMatrixConfig;
  initialEvaluation?: RiskEvaluationResult;
}

const DEFAULT_PRESETS = [
  {
    name: 'Drop Users Table (Critical)',
    action_type: 'db.execute',
    tool_name: 'postgres_tool',
    payload: { query: 'DROP TABLE users CASCADE;', target_database: 'production_core' },
    context: { environment: 'production', user_role: 'admin' },
  },
  {
    name: 'Wire Transfer $12,500 (High)',
    action_type: 'stripe.charge',
    tool_name: 'stripe_connector',
    payload: { amount: 12500, currency: 'USD', destination_account: 'acct_intl_982' },
    context: { environment: 'production' },
  },
  {
    name: 'Delete Root Filesystem (Critical)',
    action_type: 'shell.exec',
    tool_name: 'system_terminal',
    payload: { command: 'rm -rf /' },
    context: { elevation: 'root' },
  },
  {
    name: 'Query Weather Forecast (Low)',
    action_type: 'weather.get_forecast',
    tool_name: 'open_meteo',
    payload: { city: 'San Francisco', days: 5 },
    context: { environment: 'public' },
  },
];

export const RiskMatrixPanel: React.FC<RiskMatrixPanelProps> = ({
  accessToken,
  initialConfig,
  initialEvaluation,
}) => {
  const [config, setConfig] = useState<RiskMatrixConfig | null>(initialConfig || null);
  const [loadingConfig, setLoadingConfig] = useState<boolean>(!initialConfig);

  // Evaluator Sandbox State
  const [actionType, setActionType] = useState<string>('stripe.charge');
  const [toolName, setToolName] = useState<string>('stripe_connector');
  const [payloadJson, setPayloadJson] = useState<string>(
    JSON.stringify({ amount: 1500, currency: 'USD', recipient: 'acct_enterprise_88' }, null, 2)
  );
  const [environment, setEnvironment] = useState<string>('production');
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [evaluationResult, setEvaluationResult] = useState<RiskEvaluationResult | null>(
    initialEvaluation || null
  );
  const [evalError, setEvalError] = useState<string | null>(null);

  useEffect(() => {
    fetchMatrixConfig();
  }, [accessToken]);

  const fetchMatrixConfig = async () => {
    setLoadingConfig(true);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

      const res = await fetch('/api/v1/trust/risk/matrix', { headers });
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (err) {
      console.error('Failed to load risk matrix config', err);
    } finally {
      setLoadingConfig(false);
    }
  };

  const handleApplyPreset = (preset: typeof DEFAULT_PRESETS[0]) => {
    setActionType(preset.action_type);
    setToolName(preset.tool_name);
    setPayloadJson(JSON.stringify(preset.payload, null, 2));
    setEnvironment(preset.context.environment || 'production');
    setEvaluationResult(null);
    setEvalError(null);
  };

  const handleEvaluate = async () => {
    setEvalError(null);
    setEvaluating(true);

    let parsedPayload: Record<string, any> = {};
    try {
      parsedPayload = JSON.parse(payloadJson);
    } catch (err) {
      setEvalError('Invalid JSON payload. Please fix syntax errors.');
      setEvaluating(false);
      return;
    }

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

      const res = await fetch('/api/v1/trust/risk/evaluate', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          action_type: actionType,
          tool_name: toolName || undefined,
          payload: parsedPayload,
          context: { environment },
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Evaluation failed with status ${res.status}`);
      }

      const result: RiskEvaluationResult = await res.json();
      setEvaluationResult(result);
    } catch (err: any) {
      setEvalError(err.message || 'Error communicating with Risk Matrix Engine');
    } finally {
      setEvaluating(false);
    }
  };

  const getTierColor = (tier: RiskTier) => {
    switch (tier) {
      case 'critical':
        return '#ef4444';
      case 'high':
        return '#f97316';
      case 'medium':
        return '#eab308';
      case 'low':
      default:
        return '#10b981';
    }
  };

  return (
    <div className="risk-matrix-panel" role="region" aria-label="Risk Matrix Engine">
      {/* Header Info */}
      <div className="panel-subhead">
        <div>
          <h2>Dynamic Multi-Dimensional Risk Matrix</h2>
          <p className="panel-desc">
            Evaluates financial magnitude, database destructuring, shell privilege escalation, file mutations, and external API egress before any agent action is executed.
          </p>
        </div>
      </div>

      {/* Tier Breakdown Cards */}
      {loadingConfig ? (
        <div className="loading-state">Loading active Risk Matrix policies...</div>
      ) : config ? (
        <div className="risk-tiers-grid">
          {Object.entries(config.tiers).map(([tierKey, tierRule]) => {
            const color = getTierColor(tierRule.tier);
            return (
              <div
                key={tierKey}
                className={`risk-tier-card tier-${tierRule.tier}`}
                style={{ borderLeftColor: color }}
              >
                <div className="tier-card-head">
                  <span className="tier-badge" style={{ backgroundColor: `${color}20`, color }}>
                    {tierRule.tier.toUpperCase()}
                  </span>
                  <span className="tier-score-range">{tierRule.score_range}</span>
                </div>
                <p className="tier-desc">{tierRule.description}</p>
                <div className="tier-requirements">
                  <div className={`req-item ${tierRule.requires_human_confirmation ? 'req-active' : 'req-inactive'}`}>
                    <UserCheck size={14} />
                    <span>Human Approval: {tierRule.requires_human_confirmation ? 'Enforced' : 'Auto'}</span>
                  </div>
                  <div className={`req-item ${tierRule.requires_2fa ? 'req-active' : 'req-inactive'}`}>
                    <KeyRound size={14} />
                    <span>Step-Up 2FA: {tierRule.requires_2fa ? 'Required' : 'None'}</span>
                  </div>
                </div>
                <div className="tier-safeguards">
                  <span className="safeguards-label">Safeguards:</span>
                  <div className="safeguards-list">
                    {tierRule.safeguards.map((sg, i) => (
                      <span key={i} className="safeguard-tag">
                        {sg}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {/* Category Weights Row */}
      {config && config.category_weights && (
        <div className="category-weights-bar">
          <span className="weights-title">Risk Dimension Weights:</span>
          <div className="weights-pills">
            {Object.entries(config.category_weights).map(([cat, weight]) => (
              <span key={cat} className="weight-pill">
                <strong>{cat}:</strong> +{weight} pts
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Interactive Risk Evaluator Sandbox */}
      <div className="sandbox-card">
        <div className="sandbox-head">
          <div className="sandbox-head-title">
            <Zap size={18} className="zap-icon" />
            <h3>Live Action Risk Evaluator Sandbox</h3>
          </div>
          <span className="sandbox-badge">Real-Time Risk Scoring</span>
        </div>

        {/* Quick Presets */}
        <div className="presets-row">
          <span className="presets-label">Quick Scenarios:</span>
          <div className="presets-buttons">
            {DEFAULT_PRESETS.map((p, idx) => (
              <button
                key={idx}
                type="button"
                className="preset-btn"
                onClick={() => handleApplyPreset(p)}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Input Form */}
        <div className="evaluator-form-grid">
          <div className="form-group">
            <label htmlFor="eval-action-type">Action Type</label>
            <input
              id="eval-action-type"
              type="text"
              className="eval-input"
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              placeholder="e.g. stripe.charge, db.execute, shell.exec"
            />
          </div>

          <div className="form-group">
            <label htmlFor="eval-tool-name">Tool Name (Optional)</label>
            <input
              id="eval-tool-name"
              type="text"
              className="eval-input"
              value={toolName}
              onChange={(e) => setToolName(e.target.value)}
              placeholder="e.g. stripe_connector, bash_terminal"
            />
          </div>

          <div className="form-group">
            <label htmlFor="eval-environment">Environment</label>
            <select
              id="eval-environment"
              className="eval-select"
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
            >
              <option value="production">production</option>
              <option value="staging">staging</option>
              <option value="development">development</option>
            </select>
          </div>
        </div>

        <div className="form-group full-width">
          <label htmlFor="eval-payload-json">Action Payload (JSON)</label>
          <textarea
            id="eval-payload-json"
            rows={5}
            className="eval-textarea"
            value={payloadJson}
            onChange={(e) => setPayloadJson(e.target.value)}
            placeholder='{ "amount": 1000, "currency": "USD" }'
          />
        </div>

        {evalError && <div className="eval-error">{evalError}</div>}

        <div className="evaluator-actions">
          <button
            type="button"
            className="evaluate-btn"
            disabled={evaluating}
            onClick={handleEvaluate}
          >
            <Play size={16} />
            {evaluating ? 'Evaluating Matrix Policies...' : 'Evaluate Operation Risk'}
          </button>
        </div>

        {/* Dynamic Evaluation Result */}
        {evaluationResult && (
          <div
            className={`eval-result-card tier-${evaluationResult.risk_tier}`}
            style={{ borderColor: getTierColor(evaluationResult.risk_tier) }}
          >
            <div className="result-head">
              <div className="result-score-gauge">
                <span className="gauge-number" style={{ color: getTierColor(evaluationResult.risk_tier) }}>
                  {evaluationResult.risk_score}
                </span>
                <span className="gauge-denom">/ 100</span>
              </div>
              <div className="result-summary">
                <div className="result-tier-row">
                  <span
                    className="result-tier-badge"
                    style={{
                      backgroundColor: `${getTierColor(evaluationResult.risk_tier)}25`,
                      color: getTierColor(evaluationResult.risk_tier),
                    }}
                  >
                    {evaluationResult.risk_tier.toUpperCase()} RISK
                  </span>
                  <span className="result-action-label">{evaluationResult.action_type}</span>
                </div>
                <div className="result-flags">
                  {evaluationResult.requires_human_confirmation ? (
                    <span className="flag-badge flag-warn">
                      <AlertTriangle size={13} />
                      Human Confirmation Required
                    </span>
                  ) : (
                    <span className="flag-badge flag-safe">
                      <CheckCircle size={13} />
                      Auto-Execution Approved
                    </span>
                  )}

                  {evaluationResult.requires_2fa && (
                    <span className="flag-badge flag-crit">
                      <ShieldAlert size={13} />
                      Step-Up 2FA Challenge Enforced
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Reasons */}
            {evaluationResult.reasons.length > 0 && (
              <div className="result-reasons">
                <span className="reasons-title">Risk Scoring Factors:</span>
                <ul>
                  {evaluationResult.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Suggested Safeguards */}
            {evaluationResult.suggested_safeguards.length > 0 && (
              <div className="result-safeguards">
                <span className="safeguards-title">Enforced Safety Controls:</span>
                <div className="safeguards-chips">
                  {evaluationResult.suggested_safeguards.map((sg, i) => (
                    <span key={i} className="safeguard-chip">
                      <ShieldCheck size={12} />
                      {sg}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
