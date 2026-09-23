import React, { useState, useEffect } from 'react';
import './UsageView.css';

interface UsageViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigateBilling?: () => void;
}

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const UsageView: React.FC<UsageViewProps> = ({
  accessToken,
  onBack,
  onNavigateBilling,
}) => {
  const [topUpSuccess, setTopUpSuccess] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [stats, setStats] = useState({
    remainingCredits: 100.0,
    usedThisMonth: 0.0,
    estimatedCostUsd: 0.0,
    estimatedCostPkr: 0.0,
  });

  const [timelinePoints, setTimelinePoints] = useState<number[]>(new Array(30).fill(0));

  const [recentActivity, setRecentActivity] = useState<
    Array<{
      id: string;
      feature: string;
      model: string;
      tokens: number;
      costUsd: number;
      costPkr: number;
      time: string;
    }>
  >([]);

  const fetchUsage = React.useCallback(async () => {
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch(`${API_BASE}/usage/stats`, { headers });
      if (res.ok) {
        const data = await res.json();
        setStats({
          remainingCredits: data.remaining_credits ?? 100.0,
          usedThisMonth: data.used_this_month ?? 0.0,
          estimatedCostUsd: data.estimated_cost_usd ?? 0.0,
          estimatedCostPkr: data.estimated_cost_pkr ?? 0.0,
        });

        if (Array.isArray(data.timeline) && data.timeline.length > 0) {
          setTimelinePoints(data.timeline.map((t: any) => t.tokens || 0));
        }

        if (Array.isArray(data.recent_activity)) {
          setRecentActivity(
            data.recent_activity.map((a: any) => ({
              id: a.id,
              feature: a.feature || 'AI Inference',
              model: a.model || 'model',
              tokens: a.tokens || 0,
              costUsd: a.cost_usd || 0,
              costPkr: a.cost_pkr || 0,
              time: a.time ? (a.time.includes('T') ? new Date(a.time).toLocaleTimeString() : a.time) : 'Recently',
            }))
          );
        }
      }
    } catch {
      // Keep zeroed empty states
    }
  }, [accessToken]);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  const maxTokens = Math.max(...timelinePoints);
  const minTokens = Math.min(...timelinePoints);
  const diff = maxTokens - minTokens;
  const chartHeight = 140;
  const chartWidth = 760;

  const pointsString = timelinePoints
    .map((val, idx) => {
      const x = (idx / Math.max(1, timelinePoints.length - 1)) * chartWidth;
      const y =
        diff > 0
          ? chartHeight - ((val - minTokens) / diff) * (chartHeight - 20) - 10
          : chartHeight - 20;
      return `${x},${y}`;
    })
    .join(' ');

  const topUpPacks = [
    { id: 'pack_5', name: 'Starter Boost', usd: 5, pkr: 1400, credits: '500K tokens' },
    { id: 'pack_10', name: 'Power Surge', usd: 10, pkr: 2800, credits: '1.2M tokens' },
    { id: 'pack_20', name: 'Studio Ultra', usd: 20, pkr: 5600, credits: '2.8M tokens' },
  ];

  const handleTopUp = async (packId: string, packName: string, usd: number, pkr: number) => {
    setErrorMessage(null);
    setTopUpSuccess(null);

    if (!accessToken) {
      setErrorMessage('Please sign in with your account to purchase credit top-up packs.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/billing/topup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ pack_id: packId }),
      });
      if (res.ok) {
        await fetchUsage();
        setTopUpSuccess(`Added ${packName} ($${usd} / Rs ${pkr.toLocaleString()}) to your credit wallet.`);
        setTimeout(() => setTopUpSuccess(null), 5000);
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorMessage(errData.detail || 'Top-up transaction could not be completed.');
      }
    } catch {
      setErrorMessage('Network connection error while purchasing credit pack.');
    }
  };

  return (
    <div className="usage-view">
      <header className="usage-view__header">
        <div className="usage-view__header-left">
          <button type="button" className="usage-view__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <h1 className="usage-view__title">Token Usage & Credits</h1>
        </div>
        <button
          type="button"
          className="usage-view__billing-btn"
          onClick={onNavigateBilling}
        >
          💳 Billing & Invoices
        </button>
      </header>

      <div className="usage-view__body">
        {!accessToken && (
          <div className="usage-view__alert" role="status" style={{ background: '#f8fafc', borderColor: '#cbd5e1', color: '#475569' }}>
            <span>🔒</span>
            <span>Guest mode: Sign in to sync your token wallet and view real-time model usage.</span>
          </div>
        )}

        {errorMessage && (
          <div className="usage-view__alert" role="alert" style={{ background: '#fef2f2', borderColor: '#fca5a5', color: '#991b1b' }}>
            <span>⚠️</span>
            <span>{errorMessage}</span>
            <button
              type="button"
              onClick={() => setErrorMessage(null)}
              style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: '#991b1b', cursor: 'pointer', fontWeight: 'bold' }}
            >
              ✕
            </button>
          </div>
        )}

        {topUpSuccess && (
          <div className="usage-view__alert" role="status">
            <span>✨</span>
            <span>{topUpSuccess}</span>
          </div>
        )}

        {/* 3 Metric Cards */}
        <div className="usage-view__metrics-grid">
          <div className="usage-metric-card">
            <span className="metric-label">Remaining Credits</span>
            <div className="metric-val">
              ${stats.remainingCredits.toFixed(2)}{' '}
              <span className="metric-sub">/ Rs {(stats.remainingCredits * 300).toLocaleString()}</span>
            </div>
            <span className="metric-status">Ready for all models</span>
          </div>

          <div className="usage-metric-card">
            <span className="metric-label">Used This Month</span>
            <div className="metric-val">{stats.usedThisMonth.toFixed(1)} M Tokens</div>
            <span className="metric-status">~42% of monthly quota</span>
          </div>

          <div className="usage-metric-card">
            <span className="metric-label">Estimated Cost</span>
            <div className="metric-val">
              ${stats.estimatedCostUsd.toFixed(2)}{' '}
              <span className="metric-sub">/ Rs {stats.estimatedCostPkr.toLocaleString()}</span>
            </div>
            <span className="metric-status">Current billing cycle</span>
          </div>
        </div>

        {/* 30-Day Token Usage Line Chart */}
        <div className="usage-chart-card">
          <div className="usage-chart-card__header">
            <h2 className="usage-card-title">30-Day Token Consumption Trend</h2>
            <span className="usage-chart-legend">● Daily token volume</span>
          </div>
          <div className="usage-chart-container">
            <svg
              viewBox={`0 0 ${chartWidth} ${chartHeight}`}
              className="usage-svg-chart"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient id="usageGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0d9488" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#0d9488" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              <polygon
                points={`0,${chartHeight} ${pointsString} ${chartWidth},${chartHeight}`}
                fill="url(#usageGradient)"
              />
              <polyline
                fill="none"
                stroke="#0d9488"
                strokeWidth="2.5"
                points={pointsString}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="usage-chart-dates">
            <span>30 days ago</span>
            <span>15 days ago</span>
            <span>Today</span>
          </div>
        </div>

        {/* Quick Top-Up Packs */}
        <div className="usage-topup-section">
          <h2 className="usage-card-title">Quick Credit Top-Up</h2>
          <div className="topup-grid">
            {topUpPacks.map((pack) => (
              <div key={pack.id} className="topup-card">
                <h3 className="topup-card__name">{pack.name}</h3>
                <div className="topup-card__price">
                  ${pack.usd} <span className="topup-card__pkr">/ Rs {pack.pkr.toLocaleString()}</span>
                </div>
                <span className="topup-card__credits">{pack.credits}</span>
                <button
                  type="button"
                  className="topup-card__btn"
                  onClick={() => handleTopUp(pack.id, pack.name, pack.usd, pack.pkr)}
                >
                  Top-Up ${pack.usd}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Activity Table */}
        <div className="usage-activity-section">
          <h2 className="usage-card-title">Recent Activity</h2>
          <div className="activity-table">
            <div className="activity-table__header">
              <span>Feature & Task</span>
              <span>Model</span>
              <span>Tokens</span>
              <span>Cost ($ & Rs)</span>
              <span>Time</span>
            </div>
            {recentActivity.length === 0 ? (
              <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: 'var(--color-muted, #64748b)' }}>
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📊</div>
                <div style={{ fontWeight: 600, color: 'var(--color-text, #1e292b)', marginBottom: '0.25rem' }}>
                  No recent AI token activity
                </div>
                <div style={{ fontSize: '0.85rem' }}>
                  Start a chat session or generate media to track real-time token consumption.
                </div>
              </div>
            ) : (
              recentActivity.map((act) => (
                <div key={act.id} className="activity-table__row">
                  <span className="act-feat">{act.feature}</span>
                  <span className="act-model">{act.model}</span>
                  <span className="act-tokens">{act.tokens.toLocaleString()}</span>
                  <span className="act-cost">
                    ${act.costUsd.toFixed(3)}{' '}
                    <span className="act-pkr">/ Rs {act.costPkr.toFixed(1)}</span>
                  </span>
                  <span className="act-time">{act.time}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
