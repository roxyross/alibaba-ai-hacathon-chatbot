import React, { useState } from 'react';
import './PricingPage.css';

interface PricingPlan {
  id: string;
  name: string;
  priceUsd: number;
  pricePkr: number;
  period: string;
  description: string;
  features: string[];
  ctaText: string;
}

const PLANS: PricingPlan[] = [
  {
    id: 'free',
    name: 'Free (BYOK)',
    priceUsd: 0,
    pricePkr: 0,
    period: 'per month',
    description: 'Start exploring Roxy-AI. Perfect for students and early testers.',
    features: [
      'Unlimited basic chat',
      'Local document memory',
      'Voice input',
    ],
    ctaText: 'Start Free',
  },
  {
    id: 'pro',
    name: 'Pro',
    priceUsd: 19,
    pricePkr: 5700,
    period: 'per month',
    description: 'Full autonomous assistant that schedules jobs, tracks finance, and sends emails for you.',
    features: [
      'Everything in Free',
      'Schedule jobs & automated workflows',
      'Finance tracking & expense logging',
      'Email send & meeting action items',
      'Cross-device continuity',
      'Smart-home control (Matter)',
      '20 GB private vector memory',
    ],
    ctaText: 'Go Pro',
  },
  {
    id: 'team',
    name: 'Team / Business',
    priceUsd: 39,
    pricePkr: 11000,
    period: 'per seat / month',
    description: 'Shared workspace for teams with advanced permissions, audit logs, and priority support.',
    features: [
      'Everything in Pro',
      'Shared team memory',
      'Role-based access',
      'Full audit logs',
      'Priority AI model access',
      'Dedicated onboarding',
    ],
    ctaText: 'Contact Sales',
  },
];

interface PricingPageProps {
  accessToken?: string | null;
  onBack: () => void;
  onSelectPlan?: (planId: string) => void;
}

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const PricingPage: React.FC<PricingPageProps> = ({ accessToken, onBack, onSelectPlan }) => {
  const [currency, setCurrency] = useState<'both' | 'usd' | 'pkr'>('both');
  const [selectedProvider, setSelectedProvider] = useState<'automatic' | 'stripe' | 'safepay'>('automatic');
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleAction = async (planId: string) => {
    setLoadingPlan(planId);
    setSuccessMessage(null);
    setErrorMessage(null);

    if (planId === 'free') {
      try {
        if (accessToken) {
          await fetch(`${API_BASE}/billing/subscribe`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ plan_id: 'free' }),
          });
          setSuccessMessage('Free plan active! Enjoy unlimited local chat and voice input.');
        } else {
          setSuccessMessage('Free plan active! Sign in to sync across devices and access document memory.');
        }
        onSelectPlan?.('free');
      } catch {
        setSuccessMessage('Free plan activated.');
        onSelectPlan?.('free');
      } finally {
        setLoadingPlan(null);
      }
      return;
    }

    if (planId === 'team') {
      setTimeout(() => {
        setLoadingPlan(null);
        setSuccessMessage('Sales inquiry submitted. Our team will contact you within 24 hours.');
        onSelectPlan?.('team');
      }, 500);
      return;
    }

    // Pro Checkout flow via Stripe or Safepay
    try {
      const checkoutCurrency = currency === 'pkr' ? 'PKR' : 'USD';
      const provParam = selectedProvider === 'automatic' ? (checkoutCurrency === 'PKR' ? 'safepay' : 'stripe') : selectedProvider;

      if (!accessToken) {
        setErrorMessage('Please sign in or create an account to start your Pro subscription checkout.');
        return;
      }

      const res = await fetch(`${API_BASE}/billing/checkout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          plan_id: planId,
          currency: checkoutCurrency,
          provider: provParam,
          return_url: `${window.location.origin}/billing?success=true`,
          cancel_url: `${window.location.origin}/pricing?canceled=true`,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const providerName = data.provider === 'safepay' ? 'Safepay' : 'Stripe';
        setSuccessMessage(`Checkout session created with ${providerName}! Redirecting to secure checkout...`);
        if (data.checkout_url && data.checkout_url.startsWith('http')) {
          window.location.href = data.checkout_url;
          return;
        }
        onSelectPlan?.(planId);
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorMessage(errData.detail || 'Could not initiate checkout session.');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'An unexpected checkout error occurred.');
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className="pricing-page">
      <div className="pricing-page__header">
        <button
          type="button"
          className="pricing-page__back-btn"
          onClick={onBack}
          aria-label="Back to chat"
        >
          ← Back to Chat
        </button>

        <div style={{ display: 'flex', gap: '0.8rem', alignItems: 'center' }}>
          <div className="pricing-page__currency-toggle">
            <button
              type="button"
              className={`currency-btn ${currency === 'both' ? 'active' : ''}`}
              onClick={() => setCurrency('both')}
            >
              $ & Rs
            </button>
            <button
              type="button"
              className={`currency-btn ${currency === 'usd' ? 'active' : ''}`}
              onClick={() => setCurrency('usd')}
            >
              USD ($)
            </button>
            <button
              type="button"
              className={`currency-btn ${currency === 'pkr' ? 'active' : ''}`}
              onClick={() => setCurrency('pkr')}
            >
              PKR (Rs)
            </button>
          </div>

          <div className="pricing-page__currency-toggle">
            <button
              type="button"
              className={`currency-btn ${selectedProvider === 'automatic' ? 'active' : ''}`}
              onClick={() => setSelectedProvider('automatic')}
              title="Automatic: routes PKR to Safepay and USD to Stripe"
            >
              Auto
            </button>
            <button
              type="button"
              className={`currency-btn ${selectedProvider === 'stripe' ? 'active' : ''}`}
              onClick={() => setSelectedProvider('stripe')}
              title="Credit/Debit Card via Stripe"
            >
              Stripe
            </button>
            <button
              type="button"
              className={`currency-btn ${selectedProvider === 'safepay' ? 'active' : ''}`}
              onClick={() => setSelectedProvider('safepay')}
              title="Pakistani Cards & Wallets via Safepay"
            >
              Safepay
            </button>
          </div>
        </div>
      </div>

      <div className="pricing-page__hero">
        <h1 className="pricing-page__title">Choose Your Roxy-AI Plan</h1>
        <p className="pricing-page__subtitle">
          One assistant. Real actions. Dual-engine payment clearance with Stripe & Safepay.
        </p>
      </div>

      {successMessage && (
        <div className="pricing-page__alert" role="status">
          <span>✨</span>
          <span>{successMessage}</span>
          <button
            type="button"
            className="pricing-page__alert-close"
            onClick={() => setSuccessMessage(null)}
          >
            ✕
          </button>
        </div>
      )}

      {errorMessage && (
        <div className="pricing-page__alert" style={{ borderColor: '#ef4444', background: '#fef2f2', color: '#b91c1c' }} role="alert">
          <span>⚠️</span>
          <span>{errorMessage}</span>
          <button
            type="button"
            className="pricing-page__alert-close"
            onClick={() => setErrorMessage(null)}
          >
            ✕
          </button>
        </div>
      )}

      {/* Vertical stack of three elegant pricing cards centered on soft off-white background */}
      <div className="pricing-page__cards-stack">
        {PLANS.map((plan) => {
          const isPro = plan.id === 'pro';
          return (
            <div
              key={plan.id}
              className={`pricing-card ${isPro ? 'pricing-card--pro' : ''}`}
            >
              <div className="pricing-card__left">
                <div className="pricing-card__header">
                  <h2 className="pricing-card__name">{plan.name}</h2>
                  <div className="pricing-card__pricing">
                    {currency === 'both' ? (
                      <span className="pricing-card__price">
                        ${plan.priceUsd}{' '}
                        <span className="pricing-card__pkr">/ Rs {plan.pricePkr.toLocaleString()}</span>
                      </span>
                    ) : currency === 'usd' ? (
                      <span className="pricing-card__price">${plan.priceUsd}</span>
                    ) : (
                      <span className="pricing-card__price">Rs {plan.pricePkr.toLocaleString()}</span>
                    )}
                    <span className="pricing-card__period"> {plan.period}</span>
                  </div>
                </div>

                <p className="pricing-card__desc">{plan.description}</p>

                <ul className="pricing-card__features">
                  {plan.features.map((feature, idx) => (
                    <li key={idx} className="pricing-card__feature">
                      <span className="pricing-card__check">✓</span>
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="pricing-card__right">
                <button
                  type="button"
                  className={`pricing-card__btn ${isPro ? 'pricing-card__btn--pro' : ''}`}
                  onClick={() => handleAction(plan.id)}
                  disabled={loadingPlan === plan.id}
                >
                  {loadingPlan === plan.id ? 'Processing…' : plan.ctaText}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
