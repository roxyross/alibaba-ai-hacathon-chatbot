"use client";

import React, { useState } from "react";
import Link from "next/link";

interface PricingTier {
  id: string;
  name: string;
  badge: string;
  priceUSD: number;
  pricePKR: number;
  period: string;
  description: string;
  features: string[];
  cta: string;
  isCurrent?: boolean;
}

export default function PricingPage() {
  const [billingCycle, setBillingCycle] = useState<"monthly" | "annual">("monthly");

  const tiers: PricingTier[] = [
    {
      id: "free",
      name: "Free",
      badge: "Core Access",
      priceUSD: 0,
      pricePKR: 0,
      period: "forever",
      description: "Essential personal AI intelligence for daily questions and lightweight exploration.",
      features: [
        "100 AI Gateway requests per month",
        "Standard Gemini 2.5 Flash & Grok Beta access",
        "Up to 3 Scheduled jobs (daily/weekly crons)",
        "Single workspace & 5 Document uploads",
        "Community support & basic telemetry"
      ],
      cta: "Current Plan",
      isCurrent: true
    },
    {
      id: "pro",
      name: "Pro",
      badge: "Full Power",
      priceUSD: billingCycle === "monthly" ? 19 : 15,
      pricePKR: billingCycle === "monthly" ? 5700 : 4500,
      period: "per month",
      description: "Unlimited autonomous capabilities, high-speed execution, Image Studio, and finance integrations.",
      features: [
        "Unlimited AI Gateway interactions",
        "Gemini 2.5 Pro, Grok 2, and Qwen 2.5 72B reasoning",
        "Unlimited Scheduled Jobs with voice & timezone triggers",
        "Plaid & Raast (Deewan / PISP Mode) integration",
        "High-definition Image Studio (500 gens/mo)",
        "Knowledge Vault with 500 MB document memory",
        "Fast response streaming & priority compute"
      ],
      cta: "Upgrade to Pro"
    },
    {
      id: "team",
      name: "Team",
      badge: "Collaborative",
      priceUSD: billingCycle === "monthly" ? 39 : 32,
      pricePKR: billingCycle === "monthly" ? 11700 : 9600,
      period: "per user / month",
      description: "Designed for engineering teams, agencies, and shared multi-agent orchestration.",
      features: [
        "Everything in Pro included",
        "Shared Workspace Hub with role-based access",
        "Centralized billing & invoice management",
        "Dedicated rate limits on Gemini & Grok",
        "Audit logs, team knowledge vault sharing & API access",
        "Priority 24/7 technical assistance"
      ],
      cta: "Upgrade to Team"
    }
  ];

  return (
    <div className="min-h-full py-12 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto mb-10">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-teal-50 text-[#0d9488] border border-teal-200 mb-3">
          <span>⚡</span>
          <span>Transparent, Predictable Plans</span>
        </div>
        <h1 className="text-3xl font-extrabold text-[#1e292b] tracking-tight sm:text-4xl">
          Plans for individual thinkers & high-velocity teams
        </h1>
        <p className="mt-3 text-sm text-slate-600">
          Supercharge your daily workflows with autonomous execution, real-time banking telemetry, and grounded intelligence.
        </p>

        {/* Monthly / Annual Toggle */}
        <div className="mt-6 inline-flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200">
          <button
            type="button"
            onClick={() => setBillingCycle("monthly")}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              billingCycle === "monthly"
                ? "bg-white text-[#1e292b] shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Monthly billing
          </button>
          <button
            type="button"
            onClick={() => setBillingCycle("annual")}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              billingCycle === "annual"
                ? "bg-white text-[#1e292b] shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <span>Annual billing</span>
            <span className="text-[10px] bg-teal-100 text-[#0d9488] px-1.5 py-0.5 rounded font-bold">Save 20%</span>
          </button>
        </div>
      </div>

      {/* 3-Card Vertical Stack */}
      <div className="space-y-6">
        {tiers.map((tier) => (
          <div
            key={tier.id}
            className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-sm hover:shadow-md transition-all flex flex-col md:flex-row md:items-center justify-between gap-6"
          >
            {/* Left Info */}
            <div className="md:max-w-md">
              <div className="flex items-center gap-2.5 mb-2">
                <h3 className="text-xl font-bold text-[#1e292b]">{tier.name}</h3>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                  {tier.badge}
                </span>
                {tier.isCurrent && (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
                    Active Plan
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-600 mb-4 leading-relaxed">
                {tier.description}
              </p>

              {/* Feature Checklist */}
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-700">
                {tier.features.map((feat, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-[#0d9488] font-bold">✓</span>
                    <span>{feat}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Right Pricing & Action */}
            <div className="flex flex-col sm:flex-row md:flex-col items-start md:items-end justify-between md:justify-center gap-4 pt-4 md:pt-0 border-t md:border-t-0 border-slate-100">
              <div className="text-left md:text-right">
                <div className="flex items-baseline md:justify-end gap-1">
                  <span className="text-3xl font-extrabold text-[#1e292b]">
                    ${tier.priceUSD}
                  </span>
                  <span className="text-xs text-slate-500 font-medium">/ {tier.period}</span>
                </div>
                <p className="text-xs font-semibold text-[#0d9488] mt-0.5">
                  Approx. Rs {tier.pricePKR.toLocaleString()} PKR / mo
                </p>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Dual currency checkout · Stripe & Raast PISP
                </p>
              </div>

              {tier.isCurrent ? (
                <button
                  disabled
                  className="w-full sm:w-auto px-6 py-2.5 rounded-xl text-xs font-bold bg-slate-100 text-slate-400 cursor-default"
                >
                  {tier.cta}
                </button>
              ) : (
                <Link
                  href="/billing"
                  className="w-full sm:w-auto px-6 py-2.5 rounded-xl text-xs font-bold bg-[#0d9488] hover:bg-[#0f766e] text-white text-center shadow-sm hover:shadow transition-all"
                >
                  {tier.cta} →
                </Link>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* PCI-DSS & Enterprise notice */}
      <div className="mt-12 text-center text-xs text-slate-500 space-y-1">
        <p>🔒 End-to-end encrypted · PCI-DSS Level 1 compliant payments via Stripe & Raast PISP Mode.</p>
        <p>
          Need custom enterprise SLAs or on-prem deployments?{" "}
          <Link href="/workspace-hub" className="text-[#0d9488] hover:underline font-medium">
            Contact Enterprise Team
          </Link>
        </p>
      </div>
    </div>
  );
}
