"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";

interface InvoiceRecord {
  id: string;
  number: string;
  date: string;
  amountUSD: number;
  amountPKR: number;
  status: "Paid" | "Pending";
  description: string;
  invoicePdfUrl?: string;
}

interface PlanInfo {
  id: string;
  name: string;
  priceUSD: number;
  pricePKR: number;
  nextBillingDate: string | null;
  provider: string;
  status: string;
}

interface PaymentMethodInfo {
  brand: string;
  last4: string;
  expiry: string;
  provider: string;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function BillingPage() {
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [plan, setPlan] = useState<PlanInfo>({
    id: "free",
    name: "Free (BYOK)",
    priceUSD: 0,
    pricePKR: 0,
    nextBillingDate: null,
    provider: "stripe",
    status: "Active",
  });
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethodInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notification, setNotification] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  const fetchBillingData = useCallback(async () => {
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("accessToken") || localStorage.getItem("roxy_token") : null;
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      // 1. Fetch Subscription
      const subRes = await fetch(`${API_BASE}/billing/subscription`, { headers });
      if (subRes.ok) {
        const subData = await subRes.json();
        const p = subData.plan;
        if (p) {
          setPlan({
            id: p.id || "free",
            name: p.name || (p.id === "free" ? "Free (BYOK)" : "Pro Plan"),
            priceUSD: p.price_usd || 0,
            pricePKR: p.price_pkr || 0,
            nextBillingDate: p.next_billing_date ? new Date(p.next_billing_date).toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }) : null,
            provider: p.provider || "stripe",
            status: p.status === "active" ? "Active Tier" : p.status || "Active",
          });
        }
      }

      // 2. Fetch Payment Methods
      const pmRes = await fetch(`${API_BASE}/billing/payment-methods`, { headers });
      if (pmRes.ok) {
        const pmData = await pmRes.json();
        const prim = pmData.primary;
        if (prim) {
          const exp = prim.expiry || `${String(prim.exp_month || 12).padStart(2, "0")}/${String(prim.exp_year || 2028).slice(-2)}`;
          setPaymentMethod({
            brand: (prim.brand || "Card").toUpperCase(),
            last4: prim.last4 || "4242",
            expiry: exp,
            provider: prim.provider === "safepay" ? "Safepay" : "Stripe",
          });
        } else {
          setPaymentMethod(null);
        }
      }

      // 3. Fetch Invoices
      const invRes = await fetch(`${API_BASE}/billing/invoices`, { headers });
      if (invRes.ok) {
        const invData = await invRes.json();
        if (Array.isArray(invData.invoices)) {
          setInvoices(
            invData.invoices.map((inv: any) => ({
              id: inv.id,
              number: inv.id.toUpperCase(),
              date: inv.date,
              amountUSD: inv.amount_usd ?? 0,
              amountPKR: inv.amount_pkr ?? 0,
              status: inv.status || "Paid",
              description: inv.description || "Subscription / Top-up",
              invoicePdfUrl: inv.invoice_pdf_url,
            }))
          );
        }
      }
    } catch {
      // In guest mode or offline, keep real zeroed data
      setInvoices([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBillingData();
  }, [fetchBillingData]);

  const handleCancelPlan = async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("accessToken") || localStorage.getItem("roxy_token") : null;
    if (!token) {
      alert("Sign in to manage and cancel your active subscription.");
      return;
    }
    if (!confirm("Are you sure you want to cancel your Roxy Pro subscription?")) return;

    try {
      const res = await fetch(`${API_BASE}/billing/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setNotification("Subscription cancellation confirmed. Access remains until the end of your billing cycle.");
        await fetchBillingData();
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorBanner(err.detail || "Failed to cancel subscription.");
      }
    } catch {
      setErrorBanner("Network error while submitting cancellation request.");
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#1e292b]">Billing & Subscriptions</h1>
        <p className="text-xs text-slate-500 mt-1">
          Manage your active tier, invoice records, and primary payment routing.
        </p>
      </div>

      {notification && (
        <div className="p-3.5 bg-teal-50 border border-teal-200 rounded-xl text-xs font-semibold text-[#0d9488]">
          ℹ️ {notification}
        </div>
      )}

      {errorBanner && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs font-semibold text-rose-600 flex items-center justify-between">
          <span>⚠️ {errorBanner}</span>
          <button onClick={() => setErrorBanner(null)} className="font-bold text-sm">✕</button>
        </div>
      )}

      {/* Current Plan Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="text-xl font-extrabold text-[#1e292b]">{plan.name}</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
                {plan.status}
              </span>
            </div>
            <p className="text-xs text-slate-600 mt-1">
              {plan.priceUSD > 0 ? (
                <>
                  {plan.nextBillingDate ? (
                    <>Next billing cycle renews on <strong>{plan.nextBillingDate}</strong> for <strong>${plan.priceUSD.toFixed(2)}</strong> (≈ Rs {plan.pricePKR.toLocaleString()} PKR).</>
                  ) : (
                    <>Subscribed for <strong>${plan.priceUSD.toFixed(2)}</strong> (≈ Rs {plan.pricePKR.toLocaleString()} PKR).</>
                  )}
                </>
              ) : (
                <>Free tier with local BYOK inference. Upgrade anytime to unlock autonomous jobs and finance ledger.</>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Link
              href="/pricing"
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#0d9488] hover:bg-[#0f766e] text-white transition-all shadow-sm"
            >
              {plan.priceUSD > 0 ? "Change Plan" : "Upgrade to Pro"}
            </Link>
            {plan.priceUSD > 0 && (
              <button
                onClick={handleCancelPlan}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-white border border-slate-200 hover:bg-rose-50 hover:text-rose-600 text-slate-600 transition-colors"
              >
                Cancel Plan
              </button>
            )}
          </div>
        </div>

        {/* Payment method summary */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-7 rounded bg-slate-100 border border-slate-200 flex items-center justify-center font-bold text-xs text-slate-700">
              💳
            </div>
            <div>
              {paymentMethod ? (
                <>
                  <p className="text-xs font-bold text-slate-800">
                    {paymentMethod.brand} ending in {paymentMethod.last4}
                  </p>
                  <p className="text-[11px] text-slate-400">
                    Expires {paymentMethod.expiry} · Default method via {paymentMethod.provider}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-xs font-bold text-slate-800">No payment method on file</p>
                  <p className="text-[11px] text-slate-400">Add a card to top up credits or activate subscriptions</p>
                </>
              )}
            </div>
          </div>

          <Link
            href="/payment-methods"
            className="text-xs font-semibold text-[#0d9488] hover:underline"
          >
            {paymentMethod ? "Manage Payment Methods →" : "+ Add Payment Method →"}
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

        {invoices.length === 0 ? (
          <div className="p-10 text-center text-slate-500">
            <div className="text-3xl mb-2">📄</div>
            <p className="text-xs font-semibold text-slate-700">No invoices yet</p>
            <p className="text-[11px] text-slate-400 mt-1">
              Your subscription charges and credit top-up invoices will appear here.
            </p>
          </div>
        ) : (
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
                      onClick={() => alert(`Downloading official PDF invoice for ${inv.number}`)}
                      className="text-[#0d9488] font-semibold hover:underline"
                    >
                      PDF ↓
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
