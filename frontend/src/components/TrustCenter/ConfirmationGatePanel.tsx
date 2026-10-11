import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  KeyRound,
  ShieldAlert,
  Send,
  PlusCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type {
  ConfirmationChallenge,
  ConfirmationResolution,
  RiskTier,
} from './types';

interface ConfirmationGatePanelProps {
  accessToken?: string | null;
  onShowToast?: (msg: string) => void;
  initialChallenges?: ConfirmationChallenge[];
  initialResolutions?: ConfirmationResolution[];
}

const DEMO_SCENARIOS = [
  {
    title: 'Wire Transfer $25,000 to Foreign Subsidiary',
    action_type: 'stripe.charge',
    summary: 'Transfer funds from Primary Treasury to German Logistics GmbH.',
    details: {
      amount: 25000,
      currency: 'USD',
      recipient_bic: 'DEUTDEDDFXX',
      purpose: 'Q4 Freight Settlement',
    },
    risk_tier: 'critical' as RiskTier,
    risk_score: 92,
    requires_2fa: true,
  },
  {
    title: 'Truncate Audit Log Records in Production',
    action_type: 'db.execute',
    summary: 'Execution of destructive SQL purge on production database.',
    details: {
      query: 'TRUNCATE TABLE audit_events CASCADE;',
      target_env: 'production',
      affected_rows: '~450,000',
    },
    risk_tier: 'critical' as RiskTier,
    risk_score: 95,
    requires_2fa: true,
  },
  {
    title: 'Update Global DNS Records via Cloudflare',
    action_type: 'network.dns_update',
    summary: 'Re-routing apex domain A records to migration load balancer.',
    details: {
      zone_id: 'zn_cloudflare_092',
      records: [{ type: 'A', name: '@', content: '198.51.100.42' }],
    },
    risk_tier: 'high' as RiskTier,
    risk_score: 72,
    requires_2fa: false,
  },
];

export const ConfirmationGatePanel: React.FC<ConfirmationGatePanelProps> = ({
  accessToken,
  onShowToast,
  initialChallenges,
  initialResolutions,
}) => {
  const [pendingChallenges, setPendingChallenges] = useState<ConfirmationChallenge[]>(
    initialChallenges || []
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [pinInputs, setPinInputs] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({});
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [recentResolutions, setRecentResolutions] = useState<ConfirmationResolution[]>(
    initialResolutions || []
  );
  const [creatingDemo, setCreatingDemo] = useState<boolean>(false);
  const [selectedDemoIndex, setSelectedDemoIndex] = useState<number>(0);

  useEffect(() => {
    fetchPending();
    const interval = setInterval(fetchPending, 4000);
    return () => clearInterval(interval);
  }, [accessToken]);

  const fetchPending = async () => {
    if (!accessToken) return;
    try {
      const headers = { Authorization: `Bearer ${accessToken}` };
      const res = await fetch('/api/v1/trust/confirmations/pending', { headers });
      if (res.ok) {
        const data: ConfirmationChallenge[] = await res.json();
        setPendingChallenges(data);
      }
    } catch (err) {
      console.error('Failed to fetch pending confirmations', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDemo = async () => {
    if (!accessToken) return;
    setCreatingDemo(true);
    const demo = DEMO_SCENARIOS[selectedDemoIndex];

    try {
      const headers = {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      };
      const res = await fetch('/api/v1/trust/confirmations/create', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          action_type: demo.action_type,
          title: demo.title,
          summary: demo.summary,
          details: demo.details,
          risk_tier: demo.risk_tier,
          risk_score: demo.risk_score,
          requires_2fa: demo.requires_2fa,
          ttl_seconds: 300,
        }),
      });

      if (res.ok) {
        onShowToast?.(`Challenge created: "${demo.title}"`);
        await fetchPending();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || 'Failed to create challenge.');
      }
    } catch (err) {
      alert('Error creating demo challenge.');
    } finally {
      setCreatingDemo(false);
    }
  };

  const handleResolve = async (challenge: ConfirmationChallenge, decision: 'approved' | 'rejected') => {
    if (!accessToken) return;
    const pin = pinInputs[challenge.challenge_id] || '';
    const comment = comments[challenge.challenge_id] || undefined;

    if (decision === 'approved' && challenge.requires_2fa && !pin) {
      alert('A 6-digit numeric Step-Up 2FA PIN is required to approve this critical operation.');
      return;
    }

    setResolvingId(challenge.challenge_id);
    try {
      const headers = {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      };
      const res = await fetch(`/api/v1/trust/confirmations/${challenge.challenge_id}/resolve`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          decision,
          challenge_token: challenge.challenge_token,
          step_up_code: pin || undefined,
          comment,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        onShowToast?.(
          `Action ${decision.toUpperCase()}: ${challenge.title} (Sig: ${data.audit_signature.slice(0, 12)}...)`
        );
        setRecentResolutions((prev) => [data, ...prev.slice(0, 4)]);
        // Clean up input state
        setPinInputs((prev) => {
          const next = { ...prev };
          delete next[challenge.challenge_id];
          return next;
        });
        await fetchPending();
      } else {
        alert(data.detail || `Failed to resolve challenge: ${data.reason || 'Invalid code'}`);
      }
    } catch (err) {
      alert('Error resolving confirmation.');
    } finally {
      setResolvingId(null);
    }
  };

  const toggleDetails = (id: string) => {
    setExpandedDetails((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const getTierColor = (tier: RiskTier) => {
    switch (tier) {
      case 'critical':
        return '#ef4444';
      case 'high':
        return '#f97316';
      case 'medium':
        return '#eab308';
      default:
        return '#10b981';
    }
  };

  const calculateRemainingSeconds = (expiresAt: string) => {
    const remaining = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
    return remaining;
  };

  return (
    <div className="confirmation-gate-panel" role="region" aria-label="Human-in-the-Loop Confirmation Gate">
      {/* Subhead */}
      <div className="panel-subhead">
        <div>
          <h2>Human-in-the-Loop Confirmation Gatekeeper</h2>
          <p className="panel-desc">
            Zero simulation: High-impact financial outlays and irreversible database modifications pause for cryptographically signed human approval with optional 2FA step-up tokens.
          </p>
        </div>

        {/* Demo Simulator Creator */}
        <div className="demo-creator-bar">
          <select
            className="demo-select"
            value={selectedDemoIndex}
            onChange={(e) => setSelectedDemoIndex(Number(e.target.value))}
          >
            {DEMO_SCENARIOS.map((s, idx) => (
              <option key={idx} value={idx}>
                {s.title} ({s.risk_tier.toUpperCase()})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="demo-create-btn"
            disabled={creatingDemo}
            onClick={handleCreateDemo}
          >
            <PlusCircle size={15} />
            {creatingDemo ? 'Simulating...' : 'Simulate Challenge'}
          </button>
        </div>
      </div>

      {/* Pending Challenges Queue */}
      <div className="pending-queue-section">
        <div className="queue-section-header">
          <ShieldAlert size={18} />
          <h3>Active Pending Approval Queue ({pendingChallenges.length})</h3>
        </div>

        {loading && pendingChallenges.length === 0 ? (
          <div className="loading-state">Checking pending challenges...</div>
        ) : pendingChallenges.length === 0 ? (
          <div className="empty-state">
            <CheckCircle2 size={44} className="empty-icon-success" />
            <h3>No Pending Approval Challenges</h3>
            <p>
              When Roxy encounters high-risk financial transfers or destructive database operations, they will pause here awaiting your cryptographic confirmation.
            </p>
          </div>
        ) : (
          <div className="challenges-grid">
            {pendingChallenges.map((challenge) => {
              const color = getTierColor(challenge.risk_tier);
              const remainingSec = calculateRemainingSeconds(challenge.expires_at);
              const isExpired = remainingSec <= 0;

              return (
                <div
                  key={challenge.challenge_id}
                  className={`challenge-card tier-${challenge.risk_tier} ${isExpired ? 'expired' : ''}`}
                  style={{ borderLeftColor: color }}
                >
                  <div className="challenge-head">
                    <div className="challenge-badges">
                      <span
                        className="tier-badge"
                        style={{ backgroundColor: `${color}20`, color }}
                      >
                        {challenge.risk_tier.toUpperCase()} RISK
                      </span>
                      <span className="score-badge">Score: {challenge.risk_score}/100</span>
                      <span className="action-type-badge">{challenge.action_type}</span>
                    </div>

                    <div className={`countdown-timer ${remainingSec < 60 ? 'timer-urgent' : ''}`}>
                      <Clock size={13} />
                      <span>{isExpired ? 'EXPIRED' : `${remainingSec}s remaining`}</span>
                    </div>
                  </div>

                  <h3 className="challenge-title">{challenge.title}</h3>
                  <p className="challenge-summary">{challenge.summary}</p>

                  {/* Expandable Details */}
                  <div className="challenge-details-toggle">
                    <button
                      type="button"
                      className="details-toggle-btn"
                      onClick={() => toggleDetails(challenge.challenge_id)}
                    >
                      {expandedDetails[challenge.challenge_id] ? (
                        <>
                          <ChevronUp size={14} /> Hide Operation Details
                        </>
                      ) : (
                        <>
                          <ChevronDown size={14} /> Inspect Operation Payload & Parameters
                        </>
                      )}
                    </button>
                    {expandedDetails[challenge.challenge_id] && (
                      <pre className="challenge-details-json">
                        {JSON.stringify(challenge.details, null, 2)}
                      </pre>
                    )}
                  </div>

                  {/* Step-up 2FA PIN input if required */}
                  {challenge.requires_2fa && (
                    <div className="challenge-2fa-box">
                      <div className="box-2fa-title">
                        <KeyRound size={15} />
                        <span>Step-Up 2FA Challenge Enforced (Demo PIN: <code>849201</code>)</span>
                      </div>
                      <input
                        type="password"
                        maxLength={6}
                        className="pin-input"
                        placeholder="Enter 6-digit numeric PIN"
                        value={pinInputs[challenge.challenge_id] || ''}
                        onChange={(e) =>
                          setPinInputs((prev) => ({
                            ...prev,
                            [challenge.challenge_id]: e.target.value.replace(/\D/g, ''),
                          }))
                        }
                      />
                    </div>
                  )}

                  {/* Optional Audit Comment */}
                  <div className="comment-box">
                    <input
                      type="text"
                      className="comment-input"
                      placeholder="Optional audit log comment or approval rationale..."
                      value={comments[challenge.challenge_id] || ''}
                      onChange={(e) =>
                        setComments((prev) => ({
                          ...prev,
                          [challenge.challenge_id]: e.target.value,
                        }))
                      }
                    />
                  </div>

                  {/* Action Buttons */}
                  <div className="challenge-actions">
                    <button
                      type="button"
                      className="reject-action-btn"
                      disabled={resolvingId === challenge.challenge_id || isExpired}
                      onClick={() => handleResolve(challenge, 'rejected')}
                    >
                      <XCircle size={15} />
                      Reject & Block
                    </button>

                    <button
                      type="button"
                      className="approve-action-btn"
                      disabled={resolvingId === challenge.challenge_id || isExpired}
                      onClick={() => handleResolve(challenge, 'approved')}
                    >
                      <CheckCircle2 size={15} />
                      {resolvingId === challenge.challenge_id ? 'Authorizing...' : 'Approve & Execute'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Recent Cryptographic Resolutions Audit */}
      {recentResolutions.length > 0 && (
        <div className="recent-resolutions-section">
          <div className="resolutions-title">
            <Send size={16} />
            <h3>Recent Cryptographically Signed Confirmations</h3>
          </div>
          <div className="resolutions-list">
            {recentResolutions.map((res) => (
              <div key={res.challenge_id} className={`resolution-item res-${res.decision}`}>
                <div className="res-head">
                  <span className={`res-badge badge-${res.decision}`}>
                    {res.decision.toUpperCase()}
                  </span>
                  <span className="res-time">
                    {new Date(res.resolved_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
                <div className="res-sig">
                  <strong>HMAC Audit Signature:</strong> <code>{res.audit_signature}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
