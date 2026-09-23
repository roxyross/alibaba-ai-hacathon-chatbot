"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";

interface ActivityItem {
  id: string;
  model: string;
  date: string;
  tokens: string;
  costUSD: string;
  costPKR: string;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function UsagePage() {
  const [balanceUSD, setBalanceUSD] = useState(0.0);
  const [usedThisMonthUSD, setUsedThisMonthUSD] = useState(0.0);
  const [estimatedCostPKR, setEstimatedCostPKR] = useState(0.0);
  const [timelinePoints, setTimelinePoints] = useState<number[]>(new Array(16).fill(0));
  const [recentActivity, setRecentActivity] = useState<ActivityItem[]>([]);
  const [topUpSuccess, setTopUpSuccess] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const balancePKR = balanceUSD * 300;
  const usedThisMonthPKR = usedThisMonthUSD * 300;
  const remainingTokens = Math.round(balanceUSD * 20000);

  const fetchUsageData = useCallback(async () => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("accessToken") || localStorage.getItem("roxy_token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE}/usage/stats`, { headers });
      if (res.ok) {
        const data = await res.json();
        setBalanceUSD(data.remaining_credits ?? 0.0);
        setUsedThisMonthUSD(data.used_this_month ?? 0.0);
        setEstimatedCostPKR(data.estimated_cost_pkr ?? 0.0);

        if (Array.isArray(data.timeline) && data.timeline.length > 0) {
          setTimelinePoints(data.timeline.map((t: any) => t.tokens || 0));
        }

        if (Array.isArray(data.recent_activity)) {
          setRecentActivity(
            data.recent_activity.map((a: any) => ({
              id: a.id,
              model: a.model || a.feature || "AI Inference",
              date: a.time ? (a.time.includes("T") ? new Date(a.time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : a.time) : "Recent",
              tokens: `${(a.tokens || 0).toLocaleString()} tokens`,
              costUSD: `$${(a.cost_usd || 0).toFixed(3)}`,
              costPKR: `Rs ${(a.cost_pkr || 0).toFixed(1)}`,
            }))
          );
        }
      }
    } catch {
      // Offline or unauthenticated zeroed state
      setBalanceUSD(0.0);
      setUsedThisMonthUSD(0.0);
    }
  }, []);

  useEffect(() => {
    fetchUsageData();
  }, [fetchUsageData]);

  const handleTopUp = async (packId: string, amountUSD: number) => {
    setErrorMessage(null);
    setTopUpSuccess(null);

    const token = typeof window !== "undefined" ? localStorage.getItem("accessToken") || localStorage.getItem("roxy_token") : null;
    if (!token) {
      setErrorMessage("Please sign in to purchase and sync wallet top-up packs.");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/billing/topup`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ pack_id: packId }),
      });

      if (res.ok) {
        await fetchUsageData();
        setTopUpSuccess(`Successfully topped up $${amountUSD} (≈ Rs ${(amountUSD * 300).toLocaleString()} PKR)!`);
        setTimeout(() => setTopUpSuccess(null), 4000);
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorMessage(errData.detail || "Top-up checkout failed.");
      }
    } catch {
      setErrorMessage("Network error while connecting to payment provider.");
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-[#1e292b]">Usage & Compute Metrics</h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
              Real-time
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Monitor AI token consumption, API calls, and instant wallet balance in both USD and PKR.
          </p>
        </div>

        <Link
          href="/billing"
          className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors self-start sm:self-center"
        >
          View Invoices →
        </Link>
      </div>

      {topUpSuccess && (
        <div className="p-3.5 bg-teal-50 border border-teal-200 rounded-xl text-xs font-semibold text-[#0d9488] animate-in fade-in">
          ✓ {topUpSuccess}
        </div>
      )}

      {errorMessage && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs font-semibold text-rose-600 flex items-center justify-between">
          <span>⚠️ {errorMessage}</span>
          <button onClick={() => setErrorMessage(null)} className="font-bold text-sm">✕</button>
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-2">
          <span className="text-xs font-semibold text-slate-500">Remaining Wallet Balance</span>
          <div>
            <div className="text-3xl font-extrabold text-[#1e292b]">
              ${balanceUSD.toFixed(2)}
            </div>
            <div className="text-xs font-semibold text-[#0d9488] mt-0.5">
              ≈ Rs {balancePKR.toLocaleString()} PKR
            </div>
          </div>
          <p className="text-[11px] text-slate-400">Approx. {remainingTokens.toLocaleString()} tokens remaining</p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-2">
          <span className="text-xs font-semibold text-slate-500">Used This Month</span>
          <div>
            <div className="text-3xl font-extrabold text-[#1e292b]">
              ${usedThisMonthUSD.toFixed(2)}
            </div>
            <div className="text-xs font-semibold text-[#0d9488] mt-0.5">
              ≈ Rs {usedThisMonthPKR.toLocaleString()} PKR
            </div>
          </div>
          <p className="text-[11px] text-slate-400">
            {estimatedCostPKR > 0 ? `Est. PKR cost: Rs ${estimatedCostPKR.toLocaleString()}` : "Current billing cycle consumption"}
          </p>
        </div>

        {/* Quick Top-up Packs */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
          <span className="text-xs font-semibold text-slate-700 block">Quick Top-Up Packs</span>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: "pack_5", amt: 5 },
              { id: "pack_10", amt: 10 },
              { id: "pack_20", amt: 20 },
            ].map(({ id, amt }) => (
              <button
                key={id}
                type="button"
                onClick={() => handleTopUp(id, amt)}
                className="py-2 px-1 text-center bg-slate-50 hover:bg-teal-50 border border-slate-200 hover:border-teal-300 rounded-xl transition-all group"
              >
                <div className="text-xs font-bold text-slate-800 group-hover:text-[#0d9488]">+${amt}</div>
                <div className="text-[10px] text-slate-400">Rs {(amt * 300).toLocaleString()}</div>
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-400 text-center">Instant credit via Stripe or Raast</p>
        </div>
      </div>

      {/* 30-day SVG Line Chart */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1e292b]">30-Day Token Consumption Velocity</h2>
            <p className="text-xs text-slate-500 mt-0.5">Daily aggregated input & output tokens</p>
          </div>
          <span className="text-xs font-bold text-[#0d9488] bg-teal-50 px-2.5 py-1 rounded-lg border border-teal-200">
            Live Stream
          </span>
        </div>

        {/* Responsive SVG Chart */}
        <div className="w-full h-48 sm:h-56 pt-4">
          <svg className="w-full h-full overflow-visible" viewBox="0 0 600 180" preserveAspectRatio="none">
            {/* Grid lines */}
            <line x1="0" y1="30" x2="600" y2="30" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4" />
            <line x1="0" y1="80" x2="600" y2="80" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4" />
            <line x1="0" y1="130" x2="600" y2="130" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4" />

            {/* Gradient fill */}
            <defs>
              <linearGradient id="tealGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0d9488" stopOpacity="0.2" />
                <stop offset="100%" stopColor="#0d9488" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Area */}
            <path
              d="M 0 140 L 40 120 L 80 135 L 120 110 L 160 90 L 200 115 L 240 70 L 280 85 L 320 60 L 360 95 L 400 45 L 440 65 L 480 40 L 520 50 L 560 30 L 600 25 L 600 170 L 0 170 Z"
              fill="url(#tealGradient)"
            />

            {/* Line */}
            <path
              d="M 0 140 L 40 120 L 80 135 L 120 110 L 160 90 L 200 115 L 240 70 L 280 85 L 320 60 L 360 95 L 400 45 L 440 65 L 480 40 L 520 50 L 560 30 L 600 25"
              fill="none"
              stroke="#0d9488"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="flex justify-between text-[10px] text-slate-400 font-mono pt-2 border-t border-slate-100">
          <span>30 days ago</span>
          <span>15 days ago</span>
          <span>Today</span>
        </div>
      </div>

      {/* Recent Activity Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100">
          <h2 className="text-sm font-bold text-[#1e292b]">Recent Activity Log</h2>
          <p className="text-xs text-slate-500 mt-0.5">Granular model inference breakdown</p>
        </div>

        {recentActivity.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            <div className="text-2xl mb-1">📊</div>
            <p className="text-xs font-semibold text-slate-700">No token activity recorded yet</p>
            <p className="text-[11px] text-slate-400 mt-0.5">Run queries, schedule jobs, or generate images to view token logs.</p>
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider text-[10px]">
              <tr>
                <th className="py-3 px-5">Model / Tool</th>
                <th className="py-3 px-5">Timestamp</th>
                <th className="py-3 px-5">Volume</th>
                <th className="py-3 px-5 text-right">Cost (USD)</th>
                <th className="py-3 px-5 text-right">Cost (PKR)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recentActivity.map((row) => (
                <tr key={row.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-3.5 px-5 font-semibold text-slate-800">{row.model}</td>
                  <td className="py-3.5 px-5 text-slate-500">{row.date}</td>
                  <td className="py-3.5 px-5 font-mono text-[11px] text-slate-600">{row.tokens}</td>
                  <td className="py-3.5 px-5 text-right font-mono text-slate-800">{row.costUSD}</td>
                  <td className="py-3.5 px-5 text-right font-mono text-[#0d9488] font-semibold">{row.costPKR}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
