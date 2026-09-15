"use client";

import React, { useState } from "react";

interface AccountData {
  id: string;
  institution: string;
  type: "Plaid Checking" | "Raast PISP Account";
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
  channel: "Raast Instant" | "Plaid ACH" | "Stripe Card";
  pinned?: boolean;
}

interface FinanceAlert {
  id: string;
  title: string;
  condition: string;
  status: "Active" | "Paused";
}

export default function FinancePage() {
  const [showAccountNums, setShowAccountNums] = useState(false);
  const [showBalances, setShowBalances] = useState(true);
  const [periodFilter, setPeriodFilter] = useState<"day" | "week" | "month" | "year">("month");
  const [linkModalOpen, setLinkModalOpen] = useState(false);

  const [accounts] = useState<AccountData[]>([
    {
      id: "1",
      institution: "Meezan Bank Ltd",
      type: "Raast PISP Account",
      holder: "Primary Operational Holding",
      accountNumber: "PK72MEZN0012340102938401",
      balanceUSD: 14250.00,
      balancePKR: 4275000.00,
      status: "Active"
    },
    {
      id: "2",
      institution: "Silicon Valley Bank / First Republic",
      type: "Plaid Checking",
      holder: "Roxy US Treasury LLC",
      accountNumber: "US98SVBK000987654321",
      balanceUSD: 38400.50,
      balancePKR: 11520150.00,
      status: "Active"
    }
  ]);

  const [transactions, setTransactions] = useState<TransactionData[]>([
    {
      id: "tx-1",
      date: "Sep 15, 2026 · 14:23",
      description: "Settlement from Deewan PISP Gateway",
      reason: "B2B client retainer milestone payment",
      amountUSD: 2400.00,
      amountPKR: 720000.00,
      type: "credit",
      channel: "Raast Instant",
      pinned: true
    },
    {
      id: "tx-2",
      date: "Sep 14, 2026 · 09:12",
      description: "NeonDB Serverless compute auto-charge",
      reason: "Monthly postgres storage & pooling",
      amountUSD: 45.00,
      amountPKR: 13500.00,
      type: "debit",
      channel: "Stripe Card",
      pinned: false
    },
    {
      id: "tx-3",
      date: "Sep 12, 2026 · 18:40",
      description: "Vendor Disbursement to AI Model Gateway",
      reason: "Gemini 2.5 Flash token API cluster allocation",
      amountUSD: 320.00,
      amountPKR: 96000.00,
      type: "debit",
      channel: "Plaid ACH",
      pinned: false
    }
  ]);

  const [alerts, setAlerts] = useState<FinanceAlert[]>([
    {
      id: "alt-1",
      title: "Raast Inflow > Rs 100,000 Alert",
      condition: "Trigger instant push notification & email summary on high-value settlements",
      status: "Active"
    },
    {
      id: "alt-2",
      title: "Low Treasury Balance Warning (< $5,000)",
      condition: "Alert finance officer if combined Plaid Checking drops below $5,000 threshold",
      status: "Active"
    }
  ]);

  const togglePinTx = (id: string) => {
    setTransactions(prev =>
      prev.map(t => (t.id === id ? { ...t, pinned: !t.pinned } : t))
    );
  };

  const toggleAlert = (id: string) => {
    setAlerts(prev =>
      prev.map(a => (a.id === id ? { ...a, status: a.status === "Active" ? "Paused" : "Active" } : a))
    );
  };

  const deleteAlert = (id: string) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
  };

  const totalUSD = accounts.reduce((acc, a) => acc + a.balanceUSD, 0);
  const totalPKR = accounts.reduce((acc, a) => acc + a.balancePKR, 0);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
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
          <p className="text-[10px] text-slate-400">Aggregated from 2 linked institutions</p>
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
          <h2 className="text-sm font-bold text-[#1e292b]">Connected Accounts</h2>
          <button
            onClick={() => setShowAccountNums(!showAccountNums)}
            className="text-xs text-slate-500 hover:text-slate-800 transition-colors"
          >
            {showAccountNums ? "Hide Account Numbers" : "Show Account Numbers"}
          </button>
        </div>

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
      </div>

      {/* Statements & Transactions */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-bold text-[#1e292b]">Statement & Transaction History</h2>
            <p className="text-xs text-slate-500 mt-0.5">Dual currency reconciliation records</p>
          </div>

          {/* Period Filter: day, week, month, year */}
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
        <div className="space-y-3">
          {transactions.map((tx) => (
            <div
              key={tx.id}
              className="p-4 rounded-xl border border-slate-100 hover:border-slate-200 hover:bg-slate-50/70 transition-all flex flex-col md:flex-row md:items-center justify-between gap-3"
            >
              {/* Left Info: Date, Desc, Reason */}
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

              {/* Right: Amounts and Actions (Download / Share / Pin) */}
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
                  <button
                    onClick={() => alert(`Sharing statement voucher for ${tx.description}`)}
                    className="p-1.5 text-xs text-slate-400 hover:text-slate-700 rounded hover:bg-slate-200/60 transition-colors"
                    title="Share receipt"
                  >
                    ↗️
                  </button>
                  <button
                    onClick={() => alert(`Downloading PDF voucher for ${tx.description}`)}
                    className="p-1.5 text-xs text-[#0d9488] hover:bg-teal-50 rounded transition-colors font-semibold"
                    title="Download receipt"
                  >
                    PDF ↓
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Finance Alerts Section */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
        <h2 className="text-sm font-bold text-[#1e292b]">Automated Treasury Alerts</h2>
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
      </div>

      {/* Link Bank Modal */}
      {linkModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
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
              <div className="p-3.5 rounded-xl border border-teal-200 bg-teal-50/50 hover:bg-teal-50 cursor-pointer transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#1e292b]">Raast PISP (State Bank of Pakistan)</span>
                  <span className="text-[10px] bg-[#0d9488] text-white px-2 py-0.5 rounded font-bold">Instant</span>
                </div>
                <p className="text-[11px] text-slate-600 mt-1">
                  Connect local accounts via IBAN or mobile alias for zero-fee instant settlements.
                </p>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 cursor-pointer transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#1e292b]">Plaid Open Banking (US & Global)</span>
                  <span className="text-[10px] bg-slate-200 text-slate-700 px-2 py-0.5 rounded font-bold">ACH</span>
                </div>
                <p className="text-[11px] text-slate-600 mt-1">
                  Connect Chase, SVB, Wells Fargo, or 12,000+ financial institutions worldwide.
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
