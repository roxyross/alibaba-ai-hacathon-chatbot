"use client";

import React, { useState } from "react";
import Link from "next/link";

export default function UsagePage() {
  const [balanceUSD, setBalanceUSD] = useState(48.50);
  const [topUpSuccess, setTopUpSuccess] = useState<string | null>(null);

  const balancePKR = balanceUSD * 300;
  const usedThisMonthUSD = 12.80;
  const usedThisMonthPKR = usedThisMonthUSD * 300;
  const remainingTokens = 745000;

  const handleTopUp = (amountUSD: number) => {
    setBalanceUSD(prev => prev + amountUSD);
    setTopUpSuccess(`Successfully topped up $${amountUSD} (≈ Rs ${(amountUSD * 300).toLocaleString()} PKR)!`);
    setTimeout(() => setTopUpSuccess(null), 4000);
  };

  const recentActivity = [
    { model: "Gemini 2.5 Flash", date: "Today, 15:42", tokens: "4,210 tokens", costUSD: "$0.02", costPKR: "Rs 6" },
    { model: "Stable Diffusion XL", date: "Today, 14:10", tokens: "1 Image Render", costUSD: "$0.04", costPKR: "Rs 12" },
    { model: "Grok 2 Reasoning", date: "Yesterday, 21:05", tokens: "8,920 tokens", costUSD: "$0.06", costPKR: "Rs 18" },
    { model: "Knowledge Vault Embed", date: "Sep 13, 11:20", tokens: "18,400 tokens", costUSD: "$0.01", costPKR: "Rs 3" },
  ];

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
          <p className="text-[11px] text-slate-400">142,500 tokens consumed across all models</p>
        </div>

        {/* Quick Top-up Packs */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
          <span className="text-xs font-semibold text-slate-700 block">Quick Top-Up Packs</span>
          <div className="grid grid-cols-3 gap-2">
            {[5, 10, 20].map((amt) => (
              <button
                key={amt}
                type="button"
                onClick={() => handleTopUp(amt)}
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
            Avg: 4,750 tokens / day
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

            {/* Data Dots */}
            {[
              [0, 140], [120, 110], [240, 70], [360, 95], [480, 40], [600, 25]
            ].map(([cx, cy], i) => (
              <circle key={i} cx={cx} cy={cy} r="4" fill="#ffffff" stroke="#0d9488" strokeWidth="2.5" />
            ))}
          </svg>
        </div>
        <div className="flex justify-between text-[10px] text-slate-400 font-mono pt-2 border-t border-slate-100">
          <span>30 days ago</span>
          <span>15 days ago</span>
          <span>Today (Peak)</span>
        </div>
      </div>

      {/* Recent Activity Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100">
          <h2 className="text-sm font-bold text-[#1e292b]">Recent Activity Log</h2>
          <p className="text-xs text-slate-500 mt-0.5">Granular model inference breakdown</p>
        </div>

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
            {recentActivity.map((row, i) => (
              <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                <td className="py-3.5 px-5 font-semibold text-slate-800">{row.model}</td>
                <td className="py-3.5 px-5 text-slate-500">{row.date}</td>
                <td className="py-3.5 px-5 font-mono text-[11px] text-slate-600">{row.tokens}</td>
                <td className="py-3.5 px-5 text-right font-mono text-slate-800">{row.costUSD}</td>
                <td className="py-3.5 px-5 text-right font-mono text-[#0d9488] font-semibold">{row.costPKR}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
