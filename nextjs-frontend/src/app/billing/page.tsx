"use client";

import React, { useState } from "react";
import Link from "next/link";

interface InvoiceRecord {
  id: string;
  number: string;
  date: string;
  amountUSD: number;
  amountPKR: number;
  status: "Paid" | "Pending";
  description: string;
}

export default function BillingPage() {
  const [invoices] = useState<InvoiceRecord[]>([
    {
      id: "inv-1",
      number: "INV-2026-0901",
      date: "Sep 1, 2026",
      amountUSD: 19.00,
      amountPKR: 5700.00,
      status: "Paid",
      description: "Roxy Pro Subscription - Monthly"
    },
    {
      id: "inv-2",
      number: "INV-2026-0801",
      date: "Aug 1, 2026",
      amountUSD: 19.00,
      amountPKR: 5700.00,
      status: "Paid",
      description: "Roxy Pro Subscription - Monthly"
    },
    {
      id: "inv-3",
      number: "INV-2026-0701",
      date: "Jul 1, 2026",
      amountUSD: 19.00,
      amountPKR: 5700.00,
      status: "Paid",
      description: "Roxy Pro Subscription - Monthly"
    }
  ]);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#1e292b]">Billing & Subscriptions</h1>
        <p className="text-xs text-slate-500 mt-1">
          Manage your active tier, invoice records, and primary payment routing.
        </p>
      </div>

      {/* Current Plan Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="text-xl font-extrabold text-[#1e292b]">Pro Plan</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
                Active Tier
              </span>
            </div>
            <p className="text-xs text-slate-600 mt-1">
              Next billing cycle renews on <strong>October 1, 2026</strong> for <strong>$19.00</strong> (≈ Rs 5,700 PKR).
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Link
              href="/pricing"
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#0d9488] hover:bg-[#0f766e] text-white transition-all shadow-sm"
            >
              Change Plan
            </Link>
            <button
              onClick={() => alert("Subscription cancellation flow triggered. Your plan will remain active until end of cycle.")}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-white border border-slate-200 hover:bg-rose-50 hover:text-rose-600 text-slate-600 transition-colors"
            >
              Cancel Plan
            </button>
          </div>
        </div>

        {/* Payment method summary */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-7 rounded bg-slate-100 border border-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
              💳
            </div>
            <div>
              <p className="text-xs font-bold text-slate-800">Mastercard ending in 4242</p>
              <p className="text-[11px] text-slate-400">Expires 12/28 · Default method via Stripe</p>
            </div>
          </div>

          <Link
            href="/payment-methods"
            className="text-xs font-semibold text-[#0d9488] hover:underline"
          >
            Manage Payment Methods →
          </Link>
        </div>
      </div>

      {/* Billing History Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1e292b]">Billing & Invoice History</h2>
            <p className="text-xs text-slate-500 mt-0.5">Download official tax invoices & receipts</p>
          </div>
        </div>

        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider text-[10px]">
            <tr>
              <th className="py-3 px-5">Invoice</th>
              <th className="py-3 px-5">Date</th>
              <th className="py-3 px-5">Description</th>
              <th className="py-3 px-5 text-right">Amount (USD)</th>
              <th className="py-3 px-5 text-right">Amount (PKR)</th>
              <th className="py-3 px-5 text-center">Status</th>
              <th className="py-3 px-5 text-right">Download</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {invoices.map((inv) => (
              <tr key={inv.id} className="hover:bg-slate-50/80 transition-colors">
                <td className="py-3.5 px-5 font-mono font-semibold text-slate-800">{inv.number}</td>
                <td className="py-3.5 px-5 text-slate-500">{inv.date}</td>
                <td className="py-3.5 px-5 text-slate-700">{inv.description}</td>
                <td className="py-3.5 px-5 text-right font-mono font-medium text-slate-800">
                  ${inv.amountUSD.toFixed(2)}
                </td>
                <td className="py-3.5 px-5 text-right font-mono text-[#0d9488] font-semibold">
                  Rs {inv.amountPKR.toLocaleString()}
                </td>
                <td className="py-3.5 px-5 text-center">
                  <span className="inline-block text-[10px] font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
                    {inv.status}
                  </span>
                </td>
                <td className="py-3.5 px-5 text-right">
                  <button
                    onClick={() => alert(`Downloading PDF invoice ${inv.number}`)}
                    className="text-[#0d9488] font-semibold hover:underline"
                  >
                    PDF ↓
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
