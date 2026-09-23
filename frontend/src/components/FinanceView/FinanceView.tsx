import React, { useState, useRef, useEffect } from 'react';
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
  accessToken,
  onBack,
  onNavigateView,
}) => {
  const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
  const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

  const [promptText, setPromptText] = useState('');
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [selectedModel, setSelectedModel] = useState('Google Gemini 2.0 Flash');
  const [isListening, setIsListening] = useState(false);
  const [statementPeriod, setStatementPeriod] = useState<'day' | 'week' | 'month' | 'year'>('month');
  const fileUploadRef = useRef<HTMLInputElement>(null);

  // Modals
  const [showRaastModal, setShowRaastModal] = useState(false);
  const [showPayModal, setShowPayModal] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Raast Form
  const [raastBank, setRaastBank] = useState('Meezan Bank');
  const [raastTitle, setRaastTitle] = useState('Operating Checking');
  const [raastIban, setRaastIban] = useState('PK89MEZN00012345678901');
  const [raastId, setRaastId] = useState('03001234567');

  // Pay Form
  const [payReceiver, setPayReceiver] = useState('');
  const [payAmount, setPayAmount] = useState('5000');
  const [payPurpose, setPayPurpose] = useState('Cloud Infrastructure / Server Bill');

  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'user' | 'assistant'; text: string }>>([
    {
      sender: 'assistant',
      text: 'Finance Agent ready. Connected with Plaid and Raast (Deewan / PISP Mode). Ask me to audit expenses, transfer via Raast, or check statement trends.',
    },
  ]);

  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchFinance = async () => {
    if (!accessToken) {
      setIsLoading(false);
      setFetchError(null);
      setAccounts([]);
      setTransactions([]);
      setAlerts([]);
      return;
    }
    setIsLoading(true);
    setFetchError(null);
    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${accessToken}`,
      };

      // 1. Fetch financial summary
      const sumRes = await fetch(`${API_BASE}/finance/summary`, { headers });
      if (sumRes.ok) {
        const sumData = await sumRes.json();
        if (Array.isArray(sumData.accounts)) {
          setAccounts(
            sumData.accounts.map((a: any) => ({
              id: a.account_id || a.connection_id,
              holder: a.name || a.institution || 'Operating Account',
              accountNumberFull: `${(a.type || 'DEP').toUpperCase()}-${a.mask || '0000'}`,
              accountNumberMasked: `••••••••${a.mask || '0000'}`,
              balanceUsd: a.balance_usd ?? a.balance ?? 0,
              balancePkr: a.balance_pkr ?? ((a.balance_usd ?? a.balance ?? 0) * 300),
              budgetUsd: a.budget_usd ?? 5000,
              budgetPkr: a.budget_pkr ?? 1500000,
              provider: a.provider === 'raast' || a.institution?.includes('Raast')
                ? 'Raast (Deewan / PISP Mode)'
                : 'Plaid',
              showNumber: false,
              showBalance: true,
            }))
          );
        }
      } else {
        const err = await sumRes.json().catch(() => ({}));
        setFetchError(err.detail || `Finance service returned status ${sumRes.status}`);
      }

      // 2. Fetch spending alerts
      const alRes = await fetch(`${API_BASE}/finance/alerts`, { headers });
      if (alRes.ok) {
        const alData = await alRes.json();
        if (Array.isArray(alData.alerts)) {
          setAlerts(
            alData.alerts.map((al: any) => ({
              id: al.id,
              date: 'Recently',
              time: '',
              description: `${al.name} (${al.alert_type}): Threshold $${al.threshold_amount || 0}`,
              status: al.enabled || al.status === 'Active' ? 'Active' : 'Pause',
            }))
          );
        }
      }

      // 3. Fetch real transactions with statementPeriod
      const txRes = await fetch(`${API_BASE}/finance/transactions?period=${statementPeriod}`, { headers });
      if (txRes.ok) {
        const txData = await txRes.json();
        if (Array.isArray(txData.transactions)) {
          setTransactions(
            txData.transactions.map((t: any) => ({
              id: t.id,
              date: t.date || 'Recent',
              time: t.time || '',
              description: t.description,
              reason: t.reason || '',
              amountUsd: t.amount_usd ?? t.amount ?? 0,
              amountPkr: t.amount_pkr ?? ((t.amount_usd ?? t.amount ?? 0) * 300),
              period: statementPeriod,
              isPinned: Boolean(t.is_pinned),
            }))
          );
        }
      }
    } catch (err: any) {
      setFetchError(err?.message || 'Failed to connect to financial ledger service.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchFinance();
  }, [accessToken, statementPeriod]);

  // Connect Plaid (Sandbox/Demo)
  const handleConnectPlaid = async () => {
    if (!accessToken) {
      setNotice({ type: 'error', text: 'Please sign in to link bank accounts via Plaid.' });
      return;
    }
    setIsConnecting(true);
    setNotice(null);
    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${accessToken}`,
      };

      const res = await fetch(`${API_BASE}/bank/demo-connect`, {
        method: 'POST',
        headers,
      });
      if (res.ok) {
        await fetchFinance();
        setNotice({ type: 'success', text: 'Bank accounts connected via Plaid.' });
        setChatMessages((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: '🏦 Bank accounts successfully connected via Plaid (Chase Premier Checking & Savings). Real-time transactions and balance ledger synchronized.',
          },
        ]);
      } else {
        const err = await res.json().catch(() => ({}));
        setNotice({ type: 'error', text: err.detail || 'Failed to connect Plaid account.' });
      }
    } catch (err: any) {
      setNotice({ type: 'error', text: err?.message || 'Network error connecting Plaid account.' });
    } finally {
      setIsConnecting(false);
    }
  };

  // Link Raast Account
  const handleLinkRaast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!raastIban.trim() || !raastTitle.trim()) return;

    if (!accessToken) {
      setNotice({ type: 'error', text: 'Please sign in to link Raast PISP accounts.' });
      setShowRaastModal(false);
      return;
    }

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      };

      const res = await fetch(`${API_BASE}/raast/link`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          iban: raastIban.trim(),
          account_title: raastTitle.trim(),
          bank_name: raastBank.trim(),
          raast_id: raastId.trim() || undefined,
          initial_balance_pkr: 150000.0,
        }),
      });

      if (res.ok) {
        setShowRaastModal(false);
        await fetchFinance();
        setNotice({ type: 'success', text: `Linked ${raastBank} account via Raast.` });
        setChatMessages((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: `🇵🇰 Successfully linked ${raastBank} account via Pakistan's Raast PISP (Deewan Mode). Account Title: ${raastTitle}. Instant payment rail is now active.`,
          },
        ]);
      } else {
        const err = await res.json().catch(() => ({}));
        setNotice({ type: 'error', text: err.detail || 'Failed to link Raast account.' });
      }
    } catch (err: any) {
      setNotice({ type: 'error', text: err?.message || 'Network error linking Raast account.' });
      setShowRaastModal(false);
    }
  };

  // Initiate Instant Raast Payment
  const handlePayRaast = async (e: React.FormEvent) => {
    e.preventDefault();
    const amountNum = parseFloat(payAmount);
    if (!payReceiver.trim() || isNaN(amountNum) || amountNum <= 0) return;

    if (!accessToken) {
      setNotice({ type: 'error', text: 'Please sign in to initiate Raast payments.' });
      setShowPayModal(false);
      return;
    }

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      };

      const res = await fetch(`${API_BASE}/raast/initiate-payment`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          receiver_raast_id: payReceiver.trim(),
          amount_pkr: amountNum,
          purpose: payPurpose.trim(),
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setShowPayModal(false);
        await fetchFinance();
        setNotice({ type: 'success', text: `Raast payment of Rs ${amountNum.toLocaleString()} completed.` });
        setChatMessages((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: `⚡ Instant Raast Payment Completed!\n• Reference: ${data.transaction_ref}\n• Amount: Rs ${amountNum.toLocaleString()} ($${data.amount_usd.toFixed(2)})\n• Receiver: ${data.receiver}\n• Remaining Balance: Rs ${data.remaining_balance_pkr.toLocaleString()}`,
          },
        ]);
      } else {
        const err = await res.json().catch(() => ({}));
        setNotice({ type: 'error', text: err.detail || 'Payment failed on Raast network.' });
      }
    } catch (err: any) {
      setNotice({ type: 'error', text: err?.message || 'Network error processing payment.' });
      setShowPayModal(false);
    }
  };

  // Unlink / Delete Account
  const handleUnlinkAccount = async (accountId: string) => {
    if (!confirm('Are you sure you want to disconnect this financial account?')) return;
    if (!accessToken) {
      setNotice({ type: 'error', text: 'Authentication required to disconnect accounts.' });
      return;
    }

    const previousAccounts = [...accounts];
    setAccounts((prev) => prev.filter((a) => a.id !== accountId));

    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${accessToken}`,
      };
      const res = await fetch(`${API_BASE}/finance/accounts/${accountId}`, {
        method: 'DELETE',
        headers,
      });
      if (res.ok) {
        setNotice({ type: 'success', text: 'Financial account disconnected.' });
        await fetchFinance();
      } else {
        const err = await res.json().catch(() => ({}));
        setAccounts(previousAccounts);
        setNotice({ type: 'error', text: err.detail || 'Failed to disconnect account.' });
      }
    } catch (err: any) {
      setAccounts(previousAccounts);
      setNotice({ type: 'error', text: err?.message || 'Network error disconnecting account.' });
    }
  };

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

  // Live Chat with Finance Agent
  const handleSend = async () => {
    if (!promptText.trim() || isSendingChat) return;
    const q = promptText.trim();
    setChatMessages((prev) => [...prev, { sender: 'user', text: q }]);
    setPromptText('');
    setIsSendingChat(true);

    if (!accessToken) {
      setIsSendingChat(false);
      setChatMessages((prev) => [
        ...prev,
        { sender: 'assistant', text: '🔒 Please sign in to consult with the Finance Agent and query your live accounts.' },
      ]);
      return;
    }

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      };
      const res = await fetch(`${API_BASE}/runtime/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: q,
          agent_override: 'finance',
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setChatMessages((prev) => [
          ...prev,
          { sender: 'assistant', text: data.response },
        ]);
        return;
      } else {
        const err = await res.json().catch(() => ({}));
        setChatMessages((prev) => [
          ...prev,
          { sender: 'assistant', text: `⚠️ Finance Agent error: ${err.detail || 'Could not process financial query.'}` },
        ]);
      }
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        { sender: 'assistant', text: `⚠️ Unable to connect to Finance Agent: ${err?.message || 'Connection error'}.` },
      ]);
    } finally {
      setIsSendingChat(false);
    }
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

  const togglePinTx = async (id: string) => {
    if (!accessToken) {
      setNotice({ type: 'error', text: 'Authentication required to pin transactions.' });
      return;
    }
    const previousTx = [...transactions];
    setTransactions((prev) =>
      prev.map((t) => (t.id === id ? { ...t, isPinned: !t.isPinned } : t))
    );

    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${accessToken}`,
      };
      const res = await fetch(`${API_BASE}/finance/transactions/${id}/pin`, {
        method: 'PATCH',
        headers,
      });
      if (res.ok) {
        const updated = await res.json();
        setTransactions((prev) =>
          prev.map((t) => (t.id === id ? { ...t, isPinned: Boolean(updated.is_pinned) } : t))
        );
      } else {
        const err = await res.json().catch(() => ({}));
        setTransactions(previousTx);
        setNotice({ type: 'error', text: err.detail || 'Failed to toggle transaction pin.' });
      }
    } catch (err: any) {
      setTransactions(previousTx);
      setNotice({ type: 'error', text: err?.message || 'Network error updating pin.' });
    }
  };

  const toggleAlert = async (id: string) => {
    if (!accessToken) {
      setNotice({ type: 'error', text: 'Authentication required to update alerts.' });
      return;
    }
    const previousAlerts = [...alerts];
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: a.status === 'Active' ? 'Pause' : 'Active' } : a))
    );

    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${accessToken}`,
      };
      const res = await fetch(`${API_BASE}/finance/alerts/${id}/status`, {
        method: 'PATCH',
        headers,
      });
      if (res.ok) {
        const data = await res.json();
        setAlerts((prev) =>
          prev.map((a) => (a.id === id ? { ...a, status: data.status as 'Active' | 'Pause' } : a))
        );
      } else {
        const err = await res.json().catch(() => ({}));
        setAlerts(previousAlerts);
        setNotice({ type: 'error', text: err.detail || 'Failed to update alert status.' });
      }
    } catch (err: any) {
      setAlerts(previousAlerts);
      setNotice({ type: 'error', text: err?.message || 'Network error updating alert.' });
    }
  };

  const deleteAlert = async (id: string) => {
    if (!accessToken) {
      setNotice({ type: 'error', text: 'Authentication required to delete alerts.' });
      return;
    }
    const previousAlerts = [...alerts];
    setAlerts((prev) => prev.filter((a) => a.id !== id));

    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${accessToken}`,
      };
      const res = await fetch(`${API_BASE}/finance/alerts/${id}`, {
        method: 'DELETE',
        headers,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setAlerts(previousAlerts);
        setNotice({ type: 'error', text: err.detail || 'Failed to delete alert.' });
      }
    } catch (err: any) {
      setAlerts(previousAlerts);
      setNotice({ type: 'error', text: err?.message || 'Network error deleting alert.' });
    }
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
        {/* Notice Toast */}
        {notice && (
          <div className={`finance-notice finance-notice--${notice.type}`}>
            <span>{notice.type === 'success' ? '✓' : '⚠️'}</span>
            <span className="finance-notice__text">{notice.text}</span>
            <button type="button" className="finance-notice__close" onClick={() => setNotice(null)}>×</button>
          </div>
        )}

        {/* Guest Auth Banner */}
        {!accessToken && (
          <div className="finance-auth-banner">
            <div className="finance-auth-banner__icon">🔒</div>
            <div className="finance-auth-banner__body">
              <h4 className="finance-auth-banner__title">Guest Session Mode</h4>
              <p className="finance-auth-banner__desc">
                Sign in to your account to securely link verified bank institutions via Plaid, initiate instant transfers on Pakistan's Raast PISP network, and manage multi-tenant transaction ledgers.
              </p>
            </div>
          </div>
        )}

        {/* Error Banner */}
        {fetchError && (
          <div className="finance-error-banner">
            <div className="finance-error-banner__content">
              <span className="finance-error-banner__icon">⚠️</span>
              <div>
                <h4 className="finance-error-banner__title">Failed to load financial records</h4>
                <p className="finance-error-banner__msg">{fetchError}</p>
              </div>
            </div>
            <button
              type="button"
              className="finance-error-banner__retry-btn"
              onClick={fetchFinance}
              disabled={isLoading}
            >
              {isLoading ? 'Retrying...' : '↻ Retry Connection'}
            </button>
          </div>
        )}

        <p className="fin-view__desc">
          Ask Roxy-AI to audit expenses, monitor runway, transfer via Raast, or check statement trends.
        </p>

        {/* Chat Messages */}
        <div className="fin-view__chat-box">
          {chatMessages.map((m, idx) => (
            <div key={idx} className={`fin-bubble fin-bubble--${m.sender}`}>
              {m.text}
            </div>
          ))}
        </div>

        {/* Chat input bar */}
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
                    handleConnectPlaid();
                    setShowPlusMenu(false);
                  }}
                >
                  <span>🏦</span> Connect Bank (Plaid)
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    setShowRaastModal(true);
                    setShowPlusMenu(false);
                  }}
                >
                  <span>🇵🇰</span> Link Raast (Deewan)
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    setShowPayModal(true);
                    setShowPlusMenu(false);
                  }}
                >
                  <span>⚡</span> Instant Raast Payment
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
                  <span>📅</span> Calendar & Schedule
                </button>
                <button
                  type="button"
                  className="plus-menu__item"
                  onClick={() => {
                    setPromptText('Reconcile all balances across Plaid and Raast');
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
          <div className="fin-section__header-row">
            <h2 className="fin-section__title">Connected Accounts (Plaid + Raast)</h2>
            <div className="fin-section__actions">
              <button
                type="button"
                className="fin-btn-action fin-btn-action--plaid"
                onClick={handleConnectPlaid}
                disabled={isConnecting}
              >
                🏦 Connect Bank (Plaid)
              </button>
              <button
                type="button"
                className="fin-btn-action fin-btn-action--raast"
                onClick={() => setShowRaastModal(true)}
              >
                🇵🇰 Link Raast (Deewan)
              </button>
              {accounts.some((a) => a.provider.includes('Raast')) && (
                <button
                  type="button"
                  className="fin-btn-action fin-btn-action--pay"
                  onClick={() => setShowPayModal(true)}
                >
                  ⚡ Instant Transfer
                </button>
              )}
            </div>
          </div>

          <div className="fin-accounts-list">
            {accounts.length === 0 ? (
              <div className="fin-empty-card">
                <div className="fin-empty-icon">🏦</div>
                <h3 className="fin-empty-title">No bank accounts connected yet</h3>
                <p className="fin-empty-desc">
                  Connect your bank via Plaid or Raast (Deewan / PISP Mode) to monitor live balances, manage runway, and detect anomalous spending.
                </p>
                <div className="fin-empty-actions">
                  <button
                    type="button"
                    className="fin-btn-action fin-btn-action--plaid"
                    onClick={handleConnectPlaid}
                    disabled={isConnecting}
                  >
                    Connect Bank (Plaid)
                  </button>
                  <button
                    type="button"
                    className="fin-btn-action fin-btn-action--raast"
                    onClick={() => setShowRaastModal(true)}
                  >
                    Link Raast (Deewan)
                  </button>
                </div>
              </div>
            ) : (
              accounts.map((acc) => (
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
                          ? `$${acc.balanceUsd.toLocaleString(undefined, { minimumFractionDigits: 2 })} / Rs ${acc.balancePkr.toLocaleString(undefined, { minimumFractionDigits: 0 })}`
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
                    <button
                      type="button"
                      className="fin-unlink-btn"
                      onClick={() => handleUnlinkAccount(acc.id)}
                      title="Disconnect Account"
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Statements Section */}
        <div className="fin-section">
          <div className="fin-statement-header">
            <h2 className="fin-section__title">Account Statements & Ledger</h2>
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
                ⬇️ Download CSV
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
            {transactions.length === 0 ? (
              <div className="fin-empty-card">
                <div className="fin-empty-icon">💳</div>
                <h3 className="fin-empty-title">No transactions recorded</h3>
                <p className="fin-empty-desc">
                  Transactions from your connected bank accounts and Raast transfers will appear here automatically.
                </p>
              </div>
            ) : (
              transactions.map((tx) => (
                <div key={tx.id} className="fin-tx-row">
                  <div className="fin-tx-date">
                    <span>{tx.date}</span>
                    <span className="fin-tx-time">{tx.time}</span>
                  </div>
                  <div className="fin-tx-desc">{tx.description}</div>
                  <div className="fin-tx-reason">{tx.reason}</div>
                  <div className={`fin-tx-amount ${tx.amountUsd >= 0 ? 'fin-tx-amount--credit' : 'fin-tx-amount--debit'}`}>
                    {tx.amountUsd >= 0 ? '+' : ''}${Math.abs(tx.amountUsd).toFixed(2)}{' '}
                    <span className="fin-tx-pkr">/ Rs {Math.abs(tx.amountPkr).toLocaleString()}</span>
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
              ))
            )}
          </div>
        </div>

        {/* Alerts Section (horizontal rows) */}
        <div className="fin-section">
          <h2 className="fin-section__title">Financial Alerts & Monitoring</h2>
          <div className="fin-alerts-list">
            {alerts.length === 0 ? (
              <div className="fin-empty-card">
                <div className="fin-empty-icon">🔔</div>
                <h3 className="fin-empty-title">No active spending alerts</h3>
                <p className="fin-empty-desc">
                  Ask the Finance Agent to set budget limits or alert thresholds for your expenses.
                </p>
              </div>
            ) : (
              alerts.map((al) => (
                <div key={al.id} className="fin-alert-row">
                  <div className="fin-alert-row__info">
                    <span className="fin-alert-time">{al.date}</span>
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
              ))
            )}
          </div>
        </div>

      </div>

      {/* Raast Linking Modal */}
      {showRaastModal && (
        <div className="fin-modal-overlay" onClick={() => setShowRaastModal(false)}>
          <div className="fin-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="fin-modal-title">🇵🇰 Link Account via Raast (Deewan Mode)</h3>
            <p className="fin-modal-desc">
              Connect your Pakistani bank account for instant zero-fee transfers via State Bank of Pakistan's Raast gateway.
            </p>
            <form onSubmit={handleLinkRaast} className="fin-modal-form">
              <div className="fin-form-group">
                <label>Bank Name</label>
                <select
                  value={raastBank}
                  onChange={(e) => setRaastBank(e.target.value)}
                  className="fin-form-input"
                >
                  <option value="Meezan Bank">Meezan Bank</option>
                  <option value="Habib Bank Limited (HBL)">Habib Bank Limited (HBL)</option>
                  <option value="Bank Alfalah">Bank Alfalah</option>
                  <option value="Easypaisa">Easypaisa</option>
                  <option value="JazzCash">JazzCash</option>
                  <option value="Nayapay">Nayapay</option>
                  <option value="Sadapay">Sadapay</option>
                  <option value="MCB Bank">MCB Bank</option>
                </select>
              </div>

              <div className="fin-form-group">
                <label>Account Title</label>
                <input
                  type="text"
                  value={raastTitle}
                  onChange={(e) => setRaastTitle(e.target.value)}
                  placeholder="e.g. Operating Checking"
                  required
                  className="fin-form-input"
                />
              </div>

              <div className="fin-form-group">
                <label>International Bank Account Number (IBAN)</label>
                <input
                  type="text"
                  value={raastIban}
                  onChange={(e) => setRaastIban(e.target.value)}
                  placeholder="PK89MEZN00012345678901"
                  required
                  className="fin-form-input"
                />
              </div>

              <div className="fin-form-group">
                <label>Raast ID (Mobile Number or CNIC)</label>
                <input
                  type="text"
                  value={raastId}
                  onChange={(e) => setRaastId(e.target.value)}
                  placeholder="03001234567"
                  className="fin-form-input"
                />
              </div>

              <div className="fin-modal-actions">
                <button
                  type="button"
                  className="fin-modal-cancel"
                  onClick={() => setShowRaastModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="fin-modal-submit">
                  Link Account
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Raast Payment Modal */}
      {showPayModal && (
        <div className="fin-modal-overlay" onClick={() => setShowPayModal(false)}>
          <div className="fin-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="fin-modal-title">⚡ Instant Raast Payment (PISP Mode)</h3>
            <p className="fin-modal-desc">
              Execute real-time peer-to-peer or merchant settlements directly from your linked Pakistani accounts.
            </p>
            <form onSubmit={handlePayRaast} className="fin-modal-form">
              <div className="fin-form-group">
                <label>Receiver Raast ID (Mobile / CNIC / IBAN)</label>
                <input
                  type="text"
                  value={payReceiver}
                  onChange={(e) => setPayReceiver(e.target.value)}
                  placeholder="e.g. 03219876543 or PK36BAHL00..."
                  required
                  className="fin-form-input"
                />
              </div>

              <div className="fin-form-group">
                <label>Amount (PKR)</label>
                <input
                  type="number"
                  value={payAmount}
                  onChange={(e) => setPayAmount(e.target.value)}
                  min="1"
                  step="any"
                  required
                  className="fin-form-input"
                />
                <span className="fin-helper-text">
                  ≈ ${(parseFloat(payAmount || '0') / 300).toFixed(2)} USD
                </span>
              </div>

              <div className="fin-form-group">
                <label>Purpose / Description</label>
                <input
                  type="text"
                  value={payPurpose}
                  onChange={(e) => setPayPurpose(e.target.value)}
                  placeholder="e.g. Cloud Hosting / Payroll"
                  required
                  className="fin-form-input"
                />
              </div>

              <div className="fin-modal-actions">
                <button
                  type="button"
                  className="fin-modal-cancel"
                  onClick={() => setShowPayModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="fin-modal-submit fin-modal-submit--pay">
                  Send Instant Payment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};
