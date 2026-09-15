import React, { useState } from 'react';
import './UsageView.css';

interface UsageViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigateBilling?: () => void;
}

export const UsageView: React.FC<UsageViewProps> = ({
  accessToken: _accessToken,
  onBack,
  onNavigateBilling,
}) => {
  const [topUpSuccess, setTopUpSuccess] = useState<string | null>(null);

  const stats = {
    remainingCredits: 142.5,
    usedThisMonth: 32.4,
    estimatedCostUsd: 7.85,
    estimatedCostPkr: 2355.0,
  };

  // Mock 30-day token timeline data for SVG line chart
  const timelinePoints = [
    12000, 14500, 13800, 16200, 15000, 18400, 21000, 19500, 22400, 24000,
    21500, 26000, 28500, 27000, 31000, 33500, 32000, 36000, 38500, 37000,
    41000, 43500, 42000, 46000, 49000, 48000, 52000, 54500, 53000, 58000,
  ];

  const maxTokens = Math.max(...timelinePoints);
  const minTokens = Math.min(...timelinePoints);
  const chartHeight = 140;
  const chartWidth = 760;

  const pointsString = timelinePoints
    .map((val, idx) => {
      const x = (idx / (timelinePoints.length - 1)) * chartWidth;
      const y = chartHeight - ((val - minTokens) / (maxTokens - minTokens)) * (chartHeight - 20) - 10;
      return `${x},${y}`;
    })
    .join(' ');

  const recentActivity = [
    {
      id: 'act-1',
      feature: 'Deep Reasoning & Synthesis',
      model: 'deepseek-r1',
      tokens: 4820,
      costUsd: 0.024,
      costPkr: 7.2,
      time: '12 mins ago',
    },
    {
      id: 'act-2',
      feature: 'Image Studio (2:3 Portrait)',
      model: 'imagen-3.0',
      tokens: 1200,
      costUsd: 0.04,
      costPkr: 12.0,
      time: '1 hour ago',
    },
    {
      id: 'act-3',
      feature: 'Scheduled Market Briefing',
      model: 'gemini-2.0-flash',
      tokens: 2150,
      costUsd: 0.006,
      costPkr: 1.8,
      time: '4 hours ago',
    },
    {
      id: 'act-4',
      feature: 'Finance Reconciliation',
      model: 'gpt-4o',
      tokens: 3410,
      costUsd: 0.017,
      costPkr: 5.1,
      time: 'Yesterday',
    },
  ];

  const topUpPacks = [
    { id: 'p5', name: 'Starter Pack', usd: 5, pkr: 1400, credits: '500K tokens' },
    { id: 'p10', name: 'Power Surge', usd: 10, pkr: 2800, credits: '1.2M tokens' },
    { id: 'p20', name: 'Studio Ultra', usd: 20, pkr: 5600, credits: '2.8M tokens' },
  ];

  const handleTopUp = (packName: string, usd: number, pkr: number) => {
    setTopUpSuccess(`Added ${packName} ($${usd} / Rs ${pkr.toLocaleString()}) to your credit wallet.`);
    setTimeout(() => setTopUpSuccess(null), 5000);
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
                  onClick={() => handleTopUp(pack.name, pack.usd, pack.pkr)}
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
            {recentActivity.map((act) => (
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
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
