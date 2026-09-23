"use client";

import React, { useState, useEffect, useCallback } from "react";

interface AccountData {
  id: string;
  institution: string;
  type: string;
  holder: string;
  accountNumber: string;
  balanceUSD: number;
  balancePKR: number;
  status: "Active";
}

interface TransactionData {
  id: string;
  date: string;
  description: string;
  reason: string;
  amountUSD: number;
  amountPKR: number;
  type: "credit" | "debit";
  channel: string;
  pinned?: boolean;
}

interface FinanceAlert {
  id: string;
  title: string;
  condition: string;
  status: "Active" | "Pause";
}

export default function FinancePage() {
  const [showAccountNums, setShowAccountNums] = useState(false);
  const [showBalances, setShowBalances] = useState(true);
  const [periodFilter, setPeriodFilter] = useState<"day" | "week" | "month" | "year">("month");
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  const [accounts, setAccounts] = useState<AccountData[]>([]);
  const [transactions, setTransactions] = useState<TransactionData[]>([]);
  const [alerts, setAlerts] = useState<FinanceAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchFinance = useCallback(async () => {
    setIsLoading(true);
    setErrorBanner(null);
    try {
      // 1. Fetch summary
      const sumRes = await fetch("/api/v1/finance/summary");
      if (sumRes.ok) {
        const sumData = await sumRes.json();
        if (Array.isArray(sumData.accounts)) {
          setAccounts(
            sumData.accounts.map((a: any) => ({
              id: a.account_id || a.connection_id,
              institution: a.institution || a.name || "Operating Account",
              type: a.provider === "raast" || a.institution?.includes("Raast") ? "Raast PISP Account" : "Plaid Checking",
              holder: a.name || a.institution || "Primary Holding",
              accountNumber: a.mask ? `••••••••${a.mask}` : "••••••••0000",
              balanceUSD: a.balance_usd ?? a.balance ?? 0,
              balancePKR: a.balance_pkr ?? ((a.balance_usd ?? a.balance ?? 0) * 300),
              status: "Active",
            }))
          );
        }
      } else if (sumRes.status !== 401) {
        const err = await sumRes.json().catch(() => ({}));
        setErrorBanner(err.detail || `Summary returned status ${sumRes.status}`);
      }

      // 2. Fetch alerts
      const alRes = await fetch("/api/v1/finance/alerts");
      if (alRes.ok) {
        const alData = await alRes.json();
        if (Array.isArray(alData.alerts)) {
          setAlerts(
            alData.alerts.map((al: any) => ({
              id: al.id,
              title: al.name,
              condition: `${al.alert_type} threshold: $${al.threshold_amount || 0}`,
              status: al.enabled || al.status === "Active" ? "Active" : "Pause",
            }))
          );
        }
      }

      // 3. Fetch transactions
      const txRes = await fetch(`/api/v1/finance/transactions?period=${periodFilter}`);
      if (txRes.ok) {
        const txData = await txRes.json();
        if (Array.isArray(txData.transactions)) {
          setTransactions(
            txData.transactions.map((t: any) => ({
              id: t.id,
              date: t.date || "Recent",
              description: t.description,
              reason: t.reason || "Operational ledger entry",
              amountUSD: Math.abs(t.amount_usd ?? t.amount ?? 0),
              amountPKR: Math.abs(t.amount_pkr ?? ((t.amount_usd ?? t.amount ?? 0) * 300)),
              type: (t.amount_usd ?? t.amount ?? 0) >= 0 ? "credit" : "debit",
              channel: t.channel || (t.description?.includes("Raast") ? "Raast Instant" : "Plaid ACH"),
              pinned: Boolean(t.is_pinned),
            }))
          );
        }
      }
    } catch {
      // Offline fallback: clean empty state
      setAccounts([]);
      setTransactions([]);
      setAlerts([]);
    } finally {
      setIsLoading(false);
    }
  }, [periodFilter]);

  useEffect(() => {
    fetchFinance();
  }, [fetchFinance]);

  const handleConnectPlaid = async () => {
    setIsConnecting(true);
    try {
      const res = await fetch("/api/v1/bank/demo-connect", { method: "POST" });
      if (res.ok) {
        await fetchFinance();
        setToastMessage({ type: "success", text: "Plaid sandbox bank connected successfully." });
        setLinkModalOpen(false);
      } else {
        const err = await res.json().catch(() => ({}));
        setToastMessage({ type: "error", text: err.detail || "Failed to connect Plaid account." });
      }
    } catch {
      setToastMessage({ type: "error", text: "Network error connecting Plaid account." });
    } finally {
      setIsConnecting(false);
    }
  };

  const handleLinkRaast = async () => {
    setIsConnecting(true);
    try {
      const res = await fetch("/api/v1/raast/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          iban: "PK89MEZN00012345678901",
          account_title: "Operating Checking",
          bank_name: "Meezan Bank",
          initial_balance_pkr: 150000.0,
        }),
      });
      if (res.ok) {
        await fetchFinance();
        setToastMessage({ type: "success", text: "Meezan Bank linked via Raast PISP." });
        setLinkModalOpen(false);
      } else {
        const err = await res.json().catch(() => ({}));
        setToastMessage({ type: "error", text: err.detail || "Failed to link Raast account." });
      }
    } catch {
      setToastMessage({ type: "error", text: "Network error linking Raast account." });
    } finally {
      setIsConnecting(false);
    }
  };

  const togglePinTx = async (id: string) => {
    const prevTx = [...transactions];
    setTransactions((prev) =>
      prev.map((t) => (t.id === id ? { ...t, pinned: !t.pinned } : t))
    );
    try {
      const res = await fetch(`/api/v1/finance/transactions/${id}/pin`, { method: "PATCH" });
      if (!res.ok) {
        setTransactions(prevTx);
        setToastMessage({ type: "error", text: "Failed to update transaction pin." });
      }
    } catch {
      setTransactions(prevTx);
      setToastMessage({ type: "error", text: "Connection error updating pin." });
    }
  };

  const toggleAlert = async (id: string) => {
    const prevAlerts = [...alerts];
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: a.status === "Active" ? "Pause" : "Active" } : a))
    );
    try {
      const res = await fetch(`/api/v1/finance/alerts/${id}/status`, { method: "PATCH" });
      if (!res.ok) {
        setAlerts(prevAlerts);
        setToastMessage({ type: "error", text: "Failed to toggle alert status." });
      }
    } catch {
      setAlerts(prevAlerts);
      setToastMessage({ type: "error", text: "Connection error toggling alert." });
    }
  };

  const deleteAlert = async (id: string) => {
    const prevAlerts = [...alerts];
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    try {
      const res = await fetch(`/api/v1/finance/alerts/${id}`, { method: "DELETE" });
      if (!res.ok) {
        setAlerts(prevAlerts);
        setToastMessage({ type: "error", text: "Failed to delete alert." });
      }
    } catch {
      setAlerts(prevAlerts);
      setToastMessage({ type: "error", text: "Connection error deleting alert." });
    }
  };

  const totalUSD = accounts.reduce((acc, a) => acc + a.balanceUSD, 0);
  const totalPKR = accounts.reduce((acc, a) => acc + a.balancePKR, 0);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          className={`flex items-center justify-between p-3 rounded-xl text-xs font-medium ${
            toastMessage.type === "success"
              ? "bg-teal-50 border border-teal-200 text-teal-800"
              : "bg-rose-50 border border-rose-200 text-rose-800"
          }`}
        >
          <span>{toastMessage.text}</span>
          <button
            onClick={() => setToastMessage(null)}
            className="text-slate-400 hover:text-slate-700 ml-3 text-sm font-bold"
          >
            ✕
          </button>
        </div>
      )}

      {/* Error Banner */}
      {errorBanner && (
        <div className="flex items-center justify-between p-4 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-800">
          <div className="flex items-center gap-2">
            <span className="text-base">⚠️</span>
            <span>{errorBanner}</span>
          </div>
          <button
            onClick={fetchFinance}
            className="px-3 py-1 bg-rose-600 text-white rounded-lg hover:bg-rose-700 font-semibold transition-colors"
          >
            ↻ Retry
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold text-[#1e292b]">Finance</h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
              Active
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Real-time unified treasury telemetry powered by Plaid Open Banking and State Bank Raast (Deewan / PISP Mode).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setLinkModalOpen(true)}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-[#1e292b] hover:bg-black text-white transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <span>+</span>
            <span>Link Bank (Raast / Plaid)</span>
          </button>
        </div>
      </div>

      {/* Summary Cards with Privacy Toggles */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span className="font-semibold text-slate-700">Total Treasury Holding</span>
            <button
              onClick={() => setShowBalances(!showBalances)}
              className="text-[#0d9488] hover:underline text-[11px] font-medium"
            >
              {showBalances ? "Hide Balance" : "Show Balance"}
            </button>
          </div>
          <div>
            <div className="text-2xl font-extrabold text-[#1e292b]">
              {showBalances ? `$${totalUSD.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "••••••••"}
            </div>
            <div className="text-xs font-semibold text-[#0d9488] mt-0.5">
              {showBalances ? `≈ Rs ${totalPKR.toLocaleString("en-US", { minimumFractionDigits: 2 })} PKR` : "••••••••"}
            </div>
          </div>
          <p className="text-[10px] text-slate-400">
            {accounts.length > 0 ? `Aggregated from ${accounts.length} linked institution${accounts.length > 1 ? "s" : ""}` : "No accounts linked"}
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-2">
          <div className="text-xs font-semibold text-slate-700">Settlement Speed</div>
          <div className="text-xl font-bold text-[#1e292b] flex items-center gap-2">
            <span>Instant</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
              Raast PISP
            </span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Direct account-to-account settlement with ISO 20022 compliance.
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-2">
          <div className="text-xs font-semibold text-slate-700">Security & Encryption</div>
          <div className="text-xl font-bold text-[#1e292b] flex items-center gap-2">
            <span>256-bit AES</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
              SOC-2
            </span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Read-only credentials with webhook telemetry and tokenized storage.
          </p>
        </div>
      </div>

      {/* Account Rows */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[#1e292b]">Connected Accounts ({accounts.length})</h2>
          {accounts.length > 0 && (
            <button
              onClick={() => setShowAccountNums(!showAccountNums)}
              className="text-xs text-slate-500 hover:text-slate-800 transition-colors"
            >
              {showAccountNums ? "Hide Account Numbers" : "Show Account Numbers"}
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="py-8 text-center text-xs text-slate-500">
            <div className="w-6 h-6 border-2 border-[#0d9488] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            <span>Loading connected accounts...</span>
          </div>
        ) : accounts.length === 0 ? (
          <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-8 text-center space-y-2">
            <span className="text-3xl block">🏦</span>
            <h4 className="text-sm font-bold text-slate-800">No bank accounts connected</h4>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Link your institution via Plaid Open Banking or connect Pakistan's Raast PISP network.
            </p>
            <div className="pt-2 flex justify-center gap-3">
              <button
                onClick={handleConnectPlaid}
                disabled={isConnecting}
                className="px-3 py-1.5 text-xs font-semibold bg-[#1e292b] text-white rounded-lg hover:bg-black transition-colors"
              >
                + Connect Plaid
              </button>
              <button
                onClick={handleLinkRaast}
                disabled={isConnecting}
                className="px-3 py-1.5 text-xs font-semibold bg-[#0d9488] text-white rounded-lg hover:bg-[#0f766e] transition-colors"
              >
                + Link Raast
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-[#1e292b]">{acc.institution}</h3>
                    <p className="text-xs text-slate-500 font-medium">{acc.holder}</p>
                  </div>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
                    {acc.type}
                  </span>
                </div>

                <div className="bg-slate-50 rounded-xl p-3 flex items-center justify-between font-mono text-xs">
                  <span className="text-slate-400">Account:</span>
                  <span className="text-slate-700 font-semibold">
                    {showAccountNums ? acc.accountNumber : `••••••••${acc.accountNumber.slice(-4)}`}
                  </span>
                </div>

                <div className="flex items-baseline justify-between pt-1">
                  <span className="text-xs text-slate-500">Available Balance</span>
                  <div className="text-right">
                    <div className="text-base font-bold text-[#1e292b]">
                      {showBalances ? `$${acc.balanceUSD.toLocaleString()}` : "••••••"}
                    </div>
                    <div className="text-[11px] font-semibold text-[#0d9488]">
                      {showBalances ? `Rs ${acc.balancePKR.toLocaleString()}` : "••••••"}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Statements & Transactions */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-bold text-[#1e292b]">Statement & Transaction History ({transactions.length})</h2>
            <p className="text-xs text-slate-500 mt-0.5">Dual currency reconciliation records</p>
          </div>

          {/* Period Filter */}
          <div className="inline-flex p-1 bg-slate-100 rounded-xl border border-slate-200 text-xs">
            {(["day", "week", "month", "year"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriodFilter(p)}
                className={`px-3 py-1 rounded-lg font-medium capitalize transition-all ${
                  periodFilter === p
                    ? "bg-white text-[#1e292b] shadow-sm font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Transaction Rows */}
        {transactions.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-400">
            No transactions recorded for the selected statement period.
          </div>
        ) : (
          <div className="space-y-3">
            {transactions.map((tx) => (
              <div
                key={tx.id}
                className="p-4 rounded-xl border border-slate-100 hover:border-slate-200 hover:bg-slate-50/70 transition-all flex flex-col md:flex-row md:items-center justify-between gap-3"
              >
                {/* Left Info */}
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold ${tx.type === "credit" ? "text-[#0d9488]" : "text-slate-800"}`}>
                      {tx.type === "credit" ? "+ Inflow" : "- Outflow"}
                    </span>
                    <span className="text-xs font-bold text-slate-800">{tx.description}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                      {tx.channel}
                    </span>
                    {tx.pinned && (
                      <span className="text-xs" title="Pinned to top">
                        📌
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">{tx.reason}</p>
                  <p className="text-[10px] text-slate-400">{tx.date}</p>
                </div>

                {/* Right: Amounts and Pin */}
                <div className="flex items-center justify-between md:justify-end gap-4">
                  <div className="text-left md:text-right">
                    <div className={`text-sm font-bold ${tx.type === "credit" ? "text-[#0d9488]" : "text-slate-800"}`}>
                      {tx.type === "credit" ? "+" : "-"}${tx.amountUSD.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </div>
                    <div className="text-[11px] text-slate-500 font-medium">
                      ≈ Rs {tx.amountPKR.toLocaleString()} PKR
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => togglePinTx(tx.id)}
                      className="p-1.5 text-xs text-slate-400 hover:text-slate-700 rounded hover:bg-slate-200/60 transition-colors"
                      title={tx.pinned ? "Unpin statement" : "Pin statement"}
                    >
                      📌
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Finance Alerts Section */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1e292b]">Automated Treasury Alerts ({alerts.length})</h2>
        {alerts.length === 0 ? (
          <div className="py-6 text-center text-xs text-slate-400">
            No spending alerts configured.
          </div>
        ) : (
          <div className="space-y-2.5">
            {alerts.map((alt) => (
              <div
                key={alt.id}
                className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-xs font-bold text-slate-800">{alt.title}</h4>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${
                        alt.status === "Active"
                          ? "bg-teal-50 text-[#0d9488] border-teal-200"
                          : "bg-slate-200 text-slate-500 border-slate-300"
                      }`}
                    >
                      {alt.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">{alt.condition}</p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleAlert(alt.id)}
                    className="px-3 py-1 text-xs font-semibold rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-700"
                  >
                    {alt.status === "Active" ? "Pause" : "Resume"}
                  </button>
                  <button
                    onClick={() => deleteAlert(alt.id)}
                    className="px-3 py-1 text-xs font-semibold rounded-lg bg-rose-50 border border-rose-200 text-rose-600 hover:bg-rose-100"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Link Bank Modal */}
      {linkModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-sm font-bold text-[#1e292b]">Link Banking Channel</h3>
              <button
                onClick={() => setLinkModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div
                onClick={handleLinkRaast}
                className="p-3.5 rounded-xl border border-teal-200 bg-teal-50/50 hover:bg-teal-50 cursor-pointer transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#1e292b]">Raast PISP (State Bank of Pakistan)</span>
                  <span className="text-[10px] bg-[#0d9488] text-white px-2 py-0.5 rounded font-bold">Instant</span>
                </div>
                <p className="text-[11px] text-slate-600 mt-1">
                  Connect Meezan Bank via Raast PISP for zero-fee instant settlements.
                </p>
              </div>

              <div
                onClick={handleConnectPlaid}
                className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 cursor-pointer transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#1e292b]">Plaid Open Banking (US & Global)</span>
                  <span className="text-[10px] bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-bold">ACH</span>
                </div>
                <p className="text-[11px] text-slate-600 mt-1">
                  Connect Chase Premier Checking & Savings sandbox ledger.
                </p>
              </div>
            </div>

            <button
              onClick={() => setLinkModalOpen(false)}
              className="w-full py-2.5 rounded-xl text-xs font-bold bg-[#1e292b] hover:bg-black text-white transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
