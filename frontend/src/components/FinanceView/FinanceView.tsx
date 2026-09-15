import React, { useState, useRef } from 'react';
import './FinanceView.css';

interface AccountItem {
  id: string;
  holder: string;
  accountNumberFull: string;
  accountNumberMasked: string;
  balanceUsd: number;
  balancePkr: number;
  budgetUsd: number;
  budgetPkr: number;
  provider: 'Plaid' | 'Raast (Deewan / PISP Mode)';
  showNumber: boolean;
  showBalance: boolean;
}

interface TransactionItem {
  id: string;
  date: string;
  time: string;
  description: string;
  reason: string;
  amountUsd: number;
  amountPkr: number;
  period: 'day' | 'week' | 'month' | 'year';
  isPinned: boolean;
}

interface AlertItem {
  id: string;
  date: string;
  time: string;
  description: string;
  status: 'Active' | 'Pause';
}

interface FinanceViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigateView?: (view: string) => void;
}

export const FinanceView: React.FC<FinanceViewProps> = ({
  accessToken: _accessToken,
  onBack,
  onNavigateView,
}) => {
  const [promptText, setPromptText] = useState('');
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [selectedModel, setSelectedModel] = useState('Google Gemini 2.0 Flash');
  const [isListening, setIsListening] = useState(false);
  const [statementPeriod, setStatementPeriod] = useState<'day' | 'week' | 'month' | 'year'>('month');
  const fileUploadRef = useRef<HTMLInputElement>(null);

  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'user' | 'assistant'; text: string }>>([
    {
      sender: 'assistant',
      text: 'Finance Agent ready. Connected with Plaid and Raast (Deewan / PISP Mode). Ask me to audit expenses, transfer via Raast, or check statement trends.',
    },
  ]);

  const [accounts, setAccounts] = useState<AccountItem[]>([
    {
      id: 'acc-1',
      holder: 'Primary Operating Account',
      accountNumberFull: 'PK89MEZN0001480102938475',
      accountNumberMasked: 'PK89••••••••8475',
      balanceUsd: 14250.0,
      balancePkr: 4275000.0,
      budgetUsd: 20000.0,
      budgetPkr: 6000000.0,
      provider: 'Raast (Deewan / PISP Mode)',
      showNumber: false,
      showBalance: true,
    },
    {
      id: 'acc-2',
      holder: 'SaaS Treasury & Stripe USD',
      accountNumberFull: 'US82CHAS0091823746192837',
      accountNumberMasked: 'US82••••••••2837',
      balanceUsd: 8940.0,
      balancePkr: 2682000.0,
      budgetUsd: 12000.0,
      budgetPkr: 3600000.0,
      provider: 'Plaid',
      showNumber: false,
      showBalance: true,
    },
  ]);

  const [transactions, setTransactions] = useState<TransactionItem[]>([
    {
      id: 'tx-1',
      date: 'Sep 15, 2026',
      time: '02:45 PM',
      description: 'GCP Cloud & Cloud Run Hosting',
      reason: 'Monthly compute and serverless container deployment infrastructure',
      amountUsd: 142.80,
      amountPkr: 42840.0,
      period: 'month',
      isPinned: false,
    },
    {
      id: 'tx-2',
      date: 'Sep 15, 2026',
      time: '11:15 AM',
      description: 'Alibaba Cloud Serverless API',
      reason: 'AI Gateway model inference credits and batch processing',
      amountUsd: 65.0,
      amountPkr: 19500.0,
      period: 'month',
      isPinned: true,
    },
    {
      id: 'tx-3',
      date: 'Sep 14, 2026',
      time: '04:20 PM',
      description: 'Raast PISP Instant Payout',
      reason: 'Contractor frontend engineering milestones disbursement',
      amountUsd: 350.0,
      amountPkr: 105000.0,
      period: 'week',
      isPinned: false,
    },
    {
      id: 'tx-4',
      date: 'Sep 12, 2026',
      time: '09:00 AM',
      description: 'Stripe SaaS Subscription Revenue',
      reason: 'Pro & Team plan billing renewals inflow',
      amountUsd: 1280.0,
      amountPkr: 384000.0,
      period: 'month',
      isPinned: false,
    },
  ]);

  const [alerts, setAlerts] = useState<AlertItem[]>([
    {
      id: 'alt-1',
      date: 'Sep 15, 2026',
      time: '01:30 PM',
      description: 'Approaching 80% of monthly cloud computing budget threshold ($160.00 / Rs 48,000)',
      status: 'Active',
    },
    {
      id: 'alt-2',
      date: 'Sep 13, 2026',
      time: '10:00 AM',
      description: 'Unusual transaction spike alert: International API gateway renewal detected',
      status: 'Active',
    },
    {
      id: 'alt-3',
      date: 'Sep 09, 2026',
      time: '08:00 AM',
      description: 'Recurring Raast payroll batch notification sent to approvals queue',
      status: 'Pause',
    },
  ]);

  // Voice input
  const toggleSpeech = () => {
    const SpeechRecognition =
      (window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser.');
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) setPromptText(transcript);
      };

      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleSend = () => {
    if (!promptText.trim()) return;
    const q = promptText.trim();
    setChatMessages((prev) => [...prev, { sender: 'user', text: q }]);
    setPromptText('');

    setTimeout(() => {
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: `📊 Financial analysis complete for: "${q}". Accounts reconciled across Plaid & Raast (Deewan Mode). Net cash flow is healthy, and budget variance is +14.2%.`,
        },
      ]);
    }, 750);
  };

  const toggleNumber = (id: string) => {
    setAccounts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, showNumber: !a.showNumber } : a))
    );
  };

  const toggleBalance = (id: string) => {
    setAccounts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, showBalance: !a.showBalance } : a))
    );
  };

  const togglePinTx = (id: string) => {
    setTransactions((prev) =>
      prev.map((t) => (t.id === id ? { ...t, isPinned: !t.isPinned } : t))
    );
  };

  const toggleAlert = (id: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: a.status === 'Active' ? 'Pause' : 'Active' } : a))
    );
  };

  const deleteAlert = (id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  const downloadStatement = () => {
    const csvContent =
      'Date,Time,Description,Reason,Amount_USD,Amount_PKR\n' +
      transactions
        .map((t) => `"${t.date}","${t.time}","${t.description}","${t.reason}",${t.amountUsd},${t.amountPkr}`)
        .join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `roxy_statement_${statementPeriod}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="fin-view">
      {/* Top Header */}
      <header className="fin-view__header">
        <div className="fin-view__header-left">
          <button type="button" className="fin-view__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <h1 className="fin-view__title">Finance</h1>
        </div>
        <span className="fin-view__status-pill">Active</span>
      </header>

      <div className="fin-view__body">
        <p className="fin-view__desc">
          Ask Roxy-AI to add accounts, set budgets, create alerts, or review statements.
        </p>

        {/* Chat Messages */}
        <div className="fin-view__chat-box">
          {chatMessages.map((m, idx) => (
            <div key={idx} className={`fin-bubble fin-bubble--${m.sender}`}>
              {m.text}
            </div>
          ))}
        </div>

        {/* Clean chat input bar */}
        <div className="fin-view__input-bar">
          <div className="fin-view__plus-wrap">
            <button
              type="button"
              className="fin-view__plus-btn"
              onClick={() => setShowPlusMenu((v) => !v)}
              title="Finance Actions"
            >
              +
            </button>

            {showPlusMenu && (
              <div className="fin-view__plus-menu">
                <div className="plus-menu__header">Finance Actions</div>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    fileUploadRef.current?.click();
                    setShowPlusMenu(false);
                  }}
                >
                  <span>📎</span> Add files (UPLOAD)
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    fileUploadRef.current?.click();
                    setShowPlusMenu(false);
                  }}
                >
                  <span>📁</span> Add folder
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    onNavigateView?.('calculator');
                    setShowPlusMenu(false);
                  }}
                >
                  <span>🧮</span> Calculator (TOOL)
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    onNavigateView?.('calendar');
                    setShowPlusMenu(false);
                  }}
                >
                  <span>📅</span> Calendar & Schedule (EVENTS)
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    setPromptText('Analyze expense anomaly in statement: ');
                    setShowPlusMenu(false);
                  }}
                >
                  <span>💻</span> Write or edit code
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    onNavigateView?.('knowledge_vault');
                    setShowPlusMenu(false);
                  }}
                >
                  <span>📚</span> Knowledge Vault
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    setPromptText('Check current USD to PKR foreign exchange rate on the web');
                    setShowPlusMenu(false);
                  }}
                >
                  <span>🌐</span> Search the web
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    setPromptText('Reconcile account balances across Plaid and Raast');
                    setShowPlusMenu(false);
                  }}
                >
                  <span>💰</span> Check finances & balances
                </button>

                <div className="plus-menu__divider" />

                <div className="plus-menu__model-picker">
                  <label>Model Picker</label>
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                  >
                    <option value="Google Gemini 2.0 Flash">Gemini 2.0 Flash</option>
                    <option value="Anthropic Claude 3.5 Sonnet">Claude 3.5 Sonnet</option>
                    <option value="OpenAI GPT-4o">GPT-4o</option>
                    <option value="DeepSeek R1">DeepSeek R1</option>
                    <option value="Grok 2">Grok 2</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          <input
            type="text"
            className="fin-view__input"
            placeholder="Ask about finances, balances, budgets, or statements..."
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSend();
            }}
          />

          <button
            type="button"
            className={`fin-view__mic-btn ${isListening ? 'listening' : ''}`}
            onClick={toggleSpeech}
            title="Voice input"
            aria-label="Voice input"
          >
            🎤
          </button>

          <button
            type="button"
            className="fin-view__send-btn"
            onClick={handleSend}
            disabled={!promptText.trim()}
            aria-label="Send finance prompt"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
        </div>
        <input type="file" ref={fileUploadRef} style={{ display: 'none' }} />

        {/* Connected Accounts Section */}
        <div className="fin-section">
          <h2 className="fin-section__title">Connected Accounts (Plaid + Raast)</h2>
          <div className="fin-accounts-list">
            {accounts.map((acc) => (
              <div key={acc.id} className="fin-account-row">
                <div className="fin-account-row__info">
                  <div className="fin-account-row__header">
                    <h3 className="fin-account-row__holder">{acc.holder}</h3>
                    <span className="fin-provider-badge">{acc.provider}</span>
                  </div>

                  <div className="fin-account-row__number-wrap">
                    <span className="fin-label">Account No:</span>
                    <span className="fin-val">
                      {acc.showNumber ? acc.accountNumberFull : acc.accountNumberMasked}
                    </span>
                    <button
                      type="button"
                      className="fin-toggle-btn"
                      onClick={() => toggleNumber(acc.id)}
                    >
                      {acc.showNumber ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                <div className="fin-account-row__balances">
                  <div className="fin-balance-block">
                    <span className="fin-label">Balance:</span>
                    <span className="fin-val-highlight">
                      {acc.showBalance
                        ? `$${acc.balanceUsd.toLocaleString()} / Rs ${acc.balancePkr.toLocaleString()}`
                        : '••••••••'}
                    </span>
                    <button
                      type="button"
                      className="fin-toggle-btn"
                      onClick={() => toggleBalance(acc.id)}
                    >
                      {acc.showBalance ? 'Hide' : 'Show'}
                    </button>
                  </div>
                  <div className="fin-budget-sub">
                    Budget Limit: ${acc.budgetUsd.toLocaleString()} / Rs {acc.budgetPkr.toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Statements Section */}
        <div className="fin-section">
          <div className="fin-statement-header">
            <h2 className="fin-section__title">Account Statements</h2>
            <div className="fin-statement-controls">
              <label className="fin-dropdown-label">Period:</label>
              <select
                className="fin-statement-select"
                value={statementPeriod}
                onChange={(e) =>
                  setStatementPeriod(e.target.value as 'day' | 'week' | 'month' | 'year')
                }
              >
                <option value="day">Per Day</option>
                <option value="week">Per Week</option>
                <option value="month">Per Month</option>
                <option value="year">Per Year</option>
              </select>
              <button
                type="button"
                className="fin-action-btn"
                onClick={downloadStatement}
                title="Download statement as CSV"
              >
                ⬇️ Download
              </button>
              <button
                type="button"
                className="fin-action-btn"
                onClick={() => alert('Statement share link copied to clipboard!')}
                title="Share statement"
              >
                🔗 Share
              </button>
            </div>
          </div>

          <div className="fin-tx-table">
            <div className="fin-tx-header">
              <span>Date & Time</span>
              <span>Description</span>
              <span>Reason</span>
              <span>Amount ($ & Rs)</span>
              <span>Actions</span>
            </div>
            {transactions.map((tx) => (
              <div key={tx.id} className="fin-tx-row">
                <div className="fin-tx-date">
                  <span>{tx.date}</span>
                  <span className="fin-tx-time">{tx.time}</span>
                </div>
                <div className="fin-tx-desc">{tx.description}</div>
                <div className="fin-tx-reason">{tx.reason}</div>
                <div className="fin-tx-amount">
                  ${tx.amountUsd.toFixed(2)}{' '}
                  <span className="fin-tx-pkr">/ Rs {tx.amountPkr.toLocaleString()}</span>
                </div>
                <div className="fin-tx-actions">
                  <button
                    type="button"
                    className={`pin-btn ${tx.isPinned ? 'pinned' : ''}`}
                    onClick={() => togglePinTx(tx.id)}
                    title={tx.isPinned ? 'Unpin statement item' : 'Pin statement item'}
                  >
                    📌 {tx.isPinned ? 'Pinned' : 'Pin'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Alerts Section (horizontal rows) */}
        <div className="fin-section">
          <h2 className="fin-section__title">Financial Alerts & Monitoring</h2>
          <div className="fin-alerts-list">
            {alerts.map((al) => (
              <div key={al.id} className="fin-alert-row">
                <div className="fin-alert-row__info">
                  <span className="fin-alert-time">{al.date} • {al.time}</span>
                  <p className="fin-alert-desc">{al.description}</p>
                </div>
                <div className="fin-alert-row__actions">
                  <button
                    type="button"
                    className={`alert-status-btn ${al.status === 'Active' ? 'active' : 'pause'}`}
                    onClick={() => toggleAlert(al.id)}
                  >
                    {al.status}
                  </button>
                  <button
                    type="button"
                    className="alert-toggle-btn"
                    onClick={() => toggleAlert(al.id)}
                  >
                    {al.status === 'Active' ? 'Pause' : 'Resume'}
                  </button>
                  <button
                    type="button"
                    className="alert-delete-btn"
                    onClick={() => deleteAlert(al.id)}
                    title="Delete alert"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
