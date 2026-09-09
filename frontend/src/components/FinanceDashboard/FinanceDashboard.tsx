import React, { useState } from 'react';
import { usePlaidLink } from 'react-plaid-link';
import { useFinance } from '../../hooks/useFinance';
import type { Budget, SpendingAlert, Transaction } from '../../hooks/useFinance';
import { VoiceInputControl } from '../common/VoiceInputControl';
import './FinanceDashboard.css';


const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

// ─── Helpers ────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(n);
}

function fmtDate(d: string): string {
  try {
    return new Date(d).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return d;
  }
}

function budgetBarClass(pct: number): string {
  if (pct >= 100) return 'budget-bar__fill--danger';
  if (pct >= 80) return 'budget-bar__fill--warning';
  return 'budget-bar__fill--ok';
}

function budgetPctClass(pct: number): string {
  if (pct >= 100) return 'budget-item__pct--danger';
  if (pct >= 80) return 'budget-item__pct--warning';
  return 'budget-item__pct--ok';
}

const ALERT_ICONS: Record<string, string> = {
  over_budget: '⚠️',
  unusual_charge: '🔔',
  bill_reminder: '📅',
};

const ALERT_LABELS: Record<string, string> = {
  over_budget: 'Over Budget',
  unusual_charge: 'Unusual Charge',
  bill_reminder: 'Bill Reminder',
};

// ─── Bank connection card ───────────────────────────────────────

interface BankConnectionCardProps {
  accounts: { connection_id: string; institution: string | null; account_id: string; name: string; type: string; mask: string | null; balance: number | null }[];
  totalBalance: number;
  loading: boolean;
  accessToken: string | null;
  onConnected: () => void;
}

const BankConnectionCard: React.FC<BankConnectionCardProps> = ({
  accounts,
  totalBalance,
  loading,
  accessToken,
  onConnected,
}) => {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [plaidError, setPlaidError] = useState<string | null>(null);

  // Fetch link token from backend
  const handleConnect = async () => {
    if (!accessToken) return;
    setConnecting(true);
    setPlaidError(null);
    try {
      const res = await fetch(`${API_BASE}/bank/link-token`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to get link token' }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setLinkToken(data.link_token);
    } catch (e) {
      setPlaidError((e as Error).message);
      setConnecting(false);
    }
  };

  // Connect instant demo bank (Chase checking + savings)
  const handleDemoConnect = async () => {
    if (!accessToken) return;
    setConnecting(true);
    setPlaidError(null);
    try {
      const res = await fetch(`${API_BASE}/bank/demo-connect`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to connect demo bank' }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      onConnected();
    } catch (e) {
      setPlaidError((e as Error).message);
    } finally {
      setConnecting(false);
    }
  };

  // Plaid Link handler — fires after user completes Plaid Link
  const onPlaidSuccess = async (publicToken: string, metadata: { institution?: { name?: string } | null }) => {
    if (!accessToken) return;
    try {
      const institution = metadata.institution?.name ?? null;
      const res = await fetch(`${API_BASE}/bank/exchange-token`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'me', // backend stamps user from JWT
          access_token: publicToken,
          item_id: `item_${Date.now()}`, // backend gets real item_id from Plaid response
          institution,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? 'Token exchange failed');
      }
      onConnected();
    } catch (e) {
      setPlaidError((e as Error).message);
    } finally {
      setConnecting(false);
      setLinkToken(null);
    }
  };

  // react-plaid-link hook — activates when linkToken is set
  const { open, ready } = usePlaidLink({
    token: linkToken ?? null,
    onSuccess: (publicToken, metadata) => {
      void onPlaidSuccess(publicToken, metadata);
    },
    onExit: (err) => {
      if (err) setPlaidError(err.display_message ?? 'Plaid Link exited with an error');
      setConnecting(false);
      setLinkToken(null);
    },
  });

  // Auto-open Plaid Link once ready and token is available (called once per token)
  const openedRef = React.useRef(false);
  React.useEffect(() => {
    if (linkToken && ready && !openedRef.current) {
      openedRef.current = true;
      open();
    }
    if (!linkToken) {
      openedRef.current = false;
    }
  }, [linkToken, ready, open]);

  if (loading) {
    return (
      <div className="finance-card">
        <p className="finance-card__title">Accounts</p>
        <div className="finance-loading">Loading accounts…</div>
      </div>
    );
  }

  return (
    <div className="finance-card">
      <p className="finance-card__title">Accounts</p>

      {accounts.length === 0 ? (
        <div className="finance-empty">
          <span className="finance-empty__icon">🏦</span>
          <p>No bank accounts connected yet.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%', maxWidth: '280px' }}>
            <button
              className="connect-bank-btn"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? 'Connecting…' : '🔗 Connect Bank (Plaid OAuth)'}
            </button>
            <button
              className="connect-bank-btn"
              onClick={handleDemoConnect}
              disabled={connecting}
              style={{ background: 'linear-gradient(135deg, #a6e3a1 0%, #94e2d5 100%)', color: '#11111b', fontWeight: 600 }}
            >
              {connecting ? 'Connecting…' : '⚡ Connect Demo Bank (Instant)'}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="finance-balance">
            <span className="finance-balance__label">Total Balance</span>
            <p className="finance-balance__amount">{fmt(totalBalance)}</p>
            <p className="finance-balance__accounts">
              {accounts.length} account{accounts.length !== 1 ? 's' : ''} across{' '}
              {new Set(accounts.map((a) => a.institution).filter(Boolean)).size} institution
              {new Set(accounts.map((a) => a.institution).filter(Boolean)).size !== 1 ? 's' : ''}
            </p>
          </div>

          <div className="finance-scroll">
            <div className="account-list">
              {accounts.map((a) => (
                <div key={a.account_id} className="account-item">
                  <div>
                    <p className="account-item__name">{a.name}</p>
                    <p className="account-item__inst">
                      {a.institution ?? 'Unknown'} · {a.type}
                    </p>
                  </div>
                  <div className="account-item__right">
                    <span className="account-item__balance">{fmt(a.balance)}</span>
                    {a.mask && <span className="account-item__mask">····{a.mask}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
            <button className="connect-bank-btn" onClick={handleConnect} style={{ flex: 1 }}>
              + Plaid Account
            </button>
            <button
              className="connect-bank-btn"
              onClick={handleDemoConnect}
              style={{ flex: 1, background: 'linear-gradient(135deg, #a6e3a1 0%, #94e2d5 100%)', color: '#11111b', fontWeight: 600 }}
            >
              ⚡ Demo Bank
            </button>
          </div>

          {/* Disconnect */}
          <button
            className="connect-bank-btn"
            onClick={async () => {
              if (!confirm('Disconnect all bank accounts?')) return;
              if (!accessToken) return;
              await fetch(`${API_BASE}/bank/connect`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${accessToken}` },
              });
              onConnected();
            }}
            style={{ background: 'none', border: '1px solid var(--color-border)', color: 'var(--color-muted)', marginTop: '0.25rem' }}
          >
            Disconnect
          </button>
        </>
      )}

      {/* Plaid error */}
      {plaidError && (
        <p role="alert" style={{ color: 'var(--color-error)', fontSize: '0.8125rem', margin: 0 }}>
          {plaidError}
        </p>
      )}
    </div>
  );
};

// ─── Transaction list ────────────────────────────────────────────

interface TransactionListCardProps {
  transactions: Transaction[];
  loading: boolean;
  onLoadMore: () => void;
}

const TransactionListCard: React.FC<TransactionListCardProps> = ({
  transactions,
  loading,
  onLoadMore,
}) => {
  if (loading) {
    return (
      <div className="finance-card">
        <p className="finance-card__title">Recent Transactions</p>
        <div className="finance-loading">Loading transactions…</div>
      </div>
    );
  }

  return (
    <div className="finance-card">
      <p className="finance-card__title">Recent Transactions</p>
      {transactions.length === 0 ? (
        <div className="finance-empty">
          <span className="finance-empty__icon">📋</span>
          <p>No transactions found.</p>
        </div>
      ) : (
        <div className="txn-list">
          {transactions.map((t, i) => (
            <div key={i} className="txn-item">
              <div className="txn-item__desc">
                <span className="txn-item__name">{t.description}</span>
                <div className="txn-item__meta">
                  <span>{fmtDate(t.date)}</span>
                  <span>{t.category || 'Uncategorized'}</span>
                  {t.pending && <span style={{ color: '#f9e2af' }}>Pending</span>}
                </div>
              </div>
              <span
                className={`txn-item__amount ${
                  t.amount < 0 ? 'txn-item__amount--debit' : 'txn-item__amount--credit'
                }`}
              >
                {t.amount < 0 ? '' : '+'}
                {fmt(Math.abs(t.amount))}
              </span>
            </div>
          ))}
        </div>
      )}
      {transactions.length > 0 && (
        <button
          className="connect-bank-btn"
          onClick={onLoadMore}
          style={{ marginTop: '0.5rem', alignSelf: 'flex-start' }}
        >
          Load more
        </button>
      )}
    </div>
  );
};

// ─── Budget overview ─────────────────────────────────────────────

interface BudgetOverviewCardProps {
  budgets: Budget[];
  loading: boolean;
  onCreate: (category: string, monthlyLimit: number) => void;
  onDelete: (id: string) => void;
}

const BudgetOverviewCard: React.FC<BudgetOverviewCardProps> = ({
  budgets,
  loading,
  onCreate,
  onDelete,
}) => {
  const [category, setCategory] = useState('');
  const [limit, setLimit] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!category.trim() || !limit) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await onCreate(category.trim(), parseFloat(limit));
      setCategory('');
      setLimit('');
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="finance-card">
        <p className="finance-card__title">Budgets</p>
        <div className="finance-loading">Loading budgets…</div>
      </div>
    );
  }

  return (
    <div className="finance-card">
      <p className="finance-card__title">Budgets</p>
      {budgets.length === 0 ? (
        <div className="finance-empty">
          <span className="finance-empty__icon">📊</span>
          <p>No budgets set. Add one below.</p>
        </div>
      ) : (
        <div className="budget-list">
          {budgets.map((b) => (
            <div key={b.id} className="budget-item">
              <div className="budget-item__header">
                <span className="budget-item__name">{b.category}</span>
                <span className={`budget-item__pct ${budgetPctClass(b.pct_used)}`}>
                  {b.pct_used.toFixed(0)}%
                </span>
              </div>
              <div className="budget-bar">
                <div
                  className={`budget-bar__fill ${budgetBarClass(b.pct_used)}`}
                  style={{ width: `${Math.min(b.pct_used, 100)}%` }}
                />
              </div>
              <div className="budget-item__footer">
                <span>
                  {fmt(b.current_spent)} spent of {fmt(b.monthly_limit)}
                </span>
                <button
                  onClick={() => onDelete(b.id)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-error)',
                    cursor: 'pointer',
                    fontSize: '0.75rem',
                    padding: 0,
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add budget form */}
      <form className="add-budget-form" onSubmit={handleSubmit}>
        <div className="add-budget-form__row">
          <input
            type="text"
            placeholder="Category (e.g. dining)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            maxLength={100}
          />
          <input
            type="number"
            placeholder="Monthly limit $"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            min="0.01"
            step="0.01"
          />
        </div>
        {formError && (
          <p role="alert" style={{ color: 'var(--color-error)', fontSize: '0.8125rem', margin: '0.25rem 0' }}>
            {formError}
          </p>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            type="submit"
            className="add-budget-form__submit"
            disabled={submitting || !category.trim() || !limit}
          >
            {submitting ? 'Adding…' : '+ Add Budget'}
          </button>
          <VoiceInputControl
            size="sm"
            showReadAloud={false}
            onTranscript={(t) => {
              const words = t.split(/\s+/);
              const num = words.find((w) => /^\d+(\.\d+)?$/.test(w));
              if (num) {
                setLimit(num);
                setCategory(words.filter((w) => w !== num).join(' '));
              } else {
                setCategory(t);
              }
            }}
            label="Speak budget (e.g. Groceries 400)"
          />
        </div>
      </form>

    </div>
  );
};

// ─── Spending alerts ─────────────────────────────────────────────

interface SpendingAlertsCardProps {
  alerts: SpendingAlert[];
  loading: boolean;
  onCreate: (alert: Omit<SpendingAlert, 'id' | 'last_triggered_at' | 'created_at'>) => void;
  onDelete: (id: string) => void;
}

const SpendingAlertsCard: React.FC<SpendingAlertsCardProps> = ({
  alerts,
  loading,
  onCreate,
  onDelete,
}) => {
  const [name, setName] = useState('');
  const [alertType, setAlertType] = useState<'over_budget' | 'unusual_charge' | 'bill_reminder'>('over_budget');
  const [threshold, setThreshold] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await onCreate({
        name: name.trim(),
        alert_type: alertType,
        threshold_amount: threshold ? parseFloat(threshold) : null,
        category: null,
        institution: null,
        enabled: true,
      });
      setName('');
      setThreshold('');
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="finance-card">
        <p className="finance-card__title">Spending Alerts</p>
        <div className="finance-loading">Loading alerts…</div>
      </div>
    );
  }

  return (
    <div className="finance-card">
      <p className="finance-card__title">Spending Alerts</p>
      {alerts.length === 0 ? (
        <div className="finance-empty">
          <span className="finance-empty__icon">🔔</span>
          <p>No alerts configured.</p>
        </div>
      ) : (
        <div className="alert-list">
          {alerts.map((a) => (
            <div key={a.id} className={`alert-item alert-item--${a.alert_type}`}>
              <span className="alert-item__icon">{ALERT_ICONS[a.alert_type] ?? '🔔'}</span>
              <div className="alert-item__body">
                <p className="alert-item__name">{a.name}</p>
                <p className="alert-item__type">
                  {ALERT_LABELS[a.alert_type] ?? a.alert_type}
                  {a.threshold_amount != null && ` · above ${fmt(a.threshold_amount)}`}
                </p>
              </div>
              <div className="alert-item__actions">
                <button
                  className="alert-item__toggle"
                  onClick={() => onDelete(a.id)}
                  title="Delete alert"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add alert form */}
      <form className="add-budget-form" onSubmit={handleSubmit}>
        <div className="add-budget-form__row">
          <input
            type="text"
            placeholder="Alert name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            style={{ flex: 2 }}
          />
          <select
            value={alertType}
            onChange={(e) => setAlertType(e.target.value as typeof alertType)}
            style={{
              background: 'var(--color-input-bg)',
              border: '1.5px solid var(--color-border)',
              borderRadius: '0.5rem',
              color: 'var(--color-text)',
              font: 'inherit',
              fontSize: '0.875rem',
              padding: '0.375rem 0.5rem',
              outline: 'none',
            }}
          >
            <option value="over_budget">Over Budget</option>
            <option value="unusual_charge">Unusual Charge</option>
            <option value="bill_reminder">Bill Reminder</option>
          </select>
        </div>
        <div className="add-budget-form__row">
          <input
            type="number"
            placeholder="Threshold amount (optional) $"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            min="0.01"
            step="0.01"
          />
          <button
            type="submit"
            className="add-budget-form__submit"
            disabled={submitting || !name.trim()}
          >
            {submitting ? 'Adding…' : '+ Add Alert'}
          </button>
        </div>
        {formError && (
          <p role="alert" style={{ color: 'var(--color-error)', fontSize: '0.8125rem', margin: '0.25rem 0' }}>
            {formError}
          </p>
        )}
      </form>
    </div>
  );
};

// ─── Month spending summary ───────────────────────────────────────

interface MonthSpendingCardProps {
  monthSpending: number;
  budgets: Budget[];
}

const MonthSpendingCard: React.FC<MonthSpendingCardProps> = ({
  monthSpending,
  budgets,
}) => {
  const totalBudget = budgets.reduce((s, b) => s + b.monthly_limit, 0);
  const pct = totalBudget > 0 ? (monthSpending / totalBudget) * 100 : 0;

  return (
    <div className="finance-card">
      <p className="finance-card__title">This Month</p>
      <div className="finance-balance">
        <span className="finance-balance__label">Total Spent</span>
        <p className="finance-balance__amount">{fmt(monthSpending)}</p>
        {totalBudget > 0 && (
          <p className="finance-balance__accounts">
            {pct.toFixed(0)}% of combined budget ({fmt(totalBudget)})
          </p>
        )}
      </div>
    </div>
  );
};

// ─── Main FinanceDashboard ───────────────────────────────────────

interface FinanceDashboardProps {
  accessToken?: string | null;
  onBack?: () => void;
}

export const FinanceDashboard: React.FC<FinanceDashboardProps> = ({ accessToken, onBack }) => {
  const {
    summary,
    transactions,
    loading,
    error,
    fetchSummary,
    fetchTransactions,
    createBudget,
    deleteBudget,
    createAlert,
    deleteAlert,
  } = useFinance({ accessToken });

  const handleLoadTransactions = () => {
    void fetchTransactions();
  };

  if (error) {
    return (
      <div className="finance">
        {onBack && (
          <button type="button" className="view-back-btn" onClick={onBack} style={{ marginBottom: '1rem' }}>
            ← Back to Chat
          </button>
        )}
        <div className="finance-card" style={{ borderColor: 'var(--color-error)' }}>
          <p className="finance-card__title" style={{ color: 'var(--color-error)' }}>
            Error
          </p>
          <p style={{ color: 'var(--color-error)', margin: 0, fontSize: '0.875rem' }}>
            {error}
          </p>
          <button
            className="connect-bank-btn"
            onClick={() => void fetchSummary()}
            style={{ marginTop: '0.75rem' }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="finance">
      <div className="finance__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {onBack && (
            <button type="button" className="view-back-btn" onClick={onBack} title="Back to Chat">
              ← Back to Chat
            </button>
          )}
          <h2 className="finance__title">
            💰 <span>Finance</span>
          </h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <VoiceInputControl
            size="sm"
            showLangPicker={true}
            showReadAloud={Boolean(summary)}
            readAloudText={
              summary
                ? `Financial overview: Total bank balance is ${fmt(summary.total_balance)}. Total spending this month is ${fmt(summary.month_spending)}. You have ${summary.budgets.length} budgets configured and ${summary.alerts.length} active spending alerts.`
                : 'Finance data is currently loading.'

            }
            onTranscript={(t) => {
              alert(`Spoken finance query: "${t}"`);
            }}
            label="Voice Finance Assistant"
          />
          <button
            onClick={() => void fetchSummary()}
            title="Refresh"
            style={{
              background: 'none',
              border: '1px solid var(--color-border)',
              borderRadius: '0.4rem',
              color: 'var(--color-muted)',
              cursor: 'pointer',
              fontSize: '0.8rem',
              padding: '0.25rem 0.5rem',
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>


      {/* Two-column grid on wider screens */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1rem',
        }}
      >
        <BankConnectionCard
          accounts={summary?.accounts ?? []}
          totalBalance={summary?.total_balance ?? 0}
          loading={loading}
          accessToken={accessToken ?? null}
          onConnected={() => void fetchSummary()}
        />
        <MonthSpendingCard
          monthSpending={summary?.month_spending ?? 0}
          budgets={summary?.budgets ?? []}
        />
        <TransactionListCard
          transactions={summary?.accounts && summary.accounts.length > 0 ? (transactions?.transactions ?? []) : []}
          loading={loading}
          onLoadMore={handleLoadTransactions}
        />
        <BudgetOverviewCard
          budgets={summary?.budgets ?? []}
          loading={loading}
          onCreate={createBudget}
          onDelete={deleteBudget}
        />
        <SpendingAlertsCard
          alerts={summary?.alerts ?? []}
          loading={loading}
          onCreate={createAlert}
          onDelete={deleteAlert}
        />
      </div>
    </div>
  );
};
