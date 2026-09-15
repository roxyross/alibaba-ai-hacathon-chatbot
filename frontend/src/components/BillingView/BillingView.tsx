import React, { useState } from 'react';
import './BillingView.css';

interface BillingViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigatePricing?: () => void;
  onNavigateUsage?: () => void;
  onNavigatePaymentMethods?: () => void;
}

export const BillingView: React.FC<BillingViewProps> = ({
  accessToken: _accessToken,
  onBack,
  onNavigatePricing,
  onNavigateUsage,
  onNavigatePaymentMethods,
}) => {
  const [cancelModal, setCancelModal] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const plan = {
    name: 'Roxy-AI Pro',
    priceUsd: 19.0,
    pricePkr: 5700.0,
    period: 'per month',
    status: 'Active',
    nextBillingDate: 'Oct 06, 2026',
    renewsAutomatically: true,
  };

  const paymentMethod = {
    brand: 'Visa',
    last4: '4242',
    expiry: '12/28',
    poweredBy: 'Stripe',
  };

  const invoices = [
    {
      id: 'INV-2026-009',
      date: 'Sep 06, 2026',
      description: 'Roxy-AI Pro Subscription (Monthly)',
      amountUsd: 19.0,
      amountPkr: 5700.0,
      status: 'Paid',
    },
    {
      id: 'INV-2026-008',
      date: 'Aug 06, 2026',
      description: 'Roxy-AI Pro Subscription (Monthly)',
      amountUsd: 19.0,
      amountPkr: 5700.0,
      status: 'Paid',
    },
    {
      id: 'INV-2026-007',
      date: 'Jul 24, 2026',
      description: 'Credit Top-Up (Studio Ultra Pack)',
      amountUsd: 20.0,
      amountPkr: 5600.0,
      status: 'Paid',
    },
  ];

  const handleDownloadInvoice = (invId: string) => {
    alert(`Downloading PDF receipt for invoice ${invId}...`);
  };

  const handleCancelConfirm = () => {
    setCancelModal(false);
    setNotification('Your subscription cancellation is confirmed. You will have full Pro access until Oct 06, 2026.');
    setTimeout(() => setNotification(null), 6000);
  };

  return (
    <div className="billing-view">
      <header className="billing-view__header">
        <div className="billing-view__header-left">
          <button type="button" className="billing-view__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <h1 className="billing-view__title">Billing & Subscriptions</h1>
        </div>
        <div className="billing-view__header-actions">
          <button type="button" className="billing-action-btn" onClick={onNavigateUsage}>
            📊 View Usage
          </button>
          <button type="button" className="billing-action-btn billing-action-btn--teal" onClick={onNavigatePricing}>
            ⚡ Change Plan
          </button>
        </div>
      </header>

      <div className="billing-view__body">
        {notification && (
          <div className="billing-view__alert" role="status">
            <span>ℹ️</span>
            <span>{notification}</span>
          </div>
        )}

        {/* Current Plan Card */}
        <div className="billing-card current-plan-card">
          <div className="current-plan__left">
            <div className="current-plan__title-wrap">
              <h2 className="current-plan__name">{plan.name}</h2>
              <span className="current-plan__status-badge">{plan.status}</span>
            </div>
            <p className="current-plan__price">
              ${plan.priceUsd.toFixed(2)}{' '}
              <span className="current-plan__pkr">/ Rs {plan.pricePkr.toLocaleString()}</span>
              <span className="current-plan__period"> {plan.period}</span>
            </p>
            <div className="current-plan__meta">
              <span>Next billing date: <strong>{plan.nextBillingDate}</strong></span>
              <span>•</span>
              <span>Auto-renews via Stripe</span>
            </div>
          </div>

          <div className="current-plan__actions">
            <button
              type="button"
              className="current-plan__change-btn"
              onClick={onNavigatePricing}
            >
              Change Plan
            </button>
            <button
              type="button"
              className="current-plan__cancel-btn"
              onClick={() => setCancelModal(true)}
            >
              Cancel Subscription
            </button>
          </div>
        </div>

        {/* Payment Method Summary */}
        <div className="billing-card payment-method-card">
          <div className="pm-card__info">
            <h3 className="pm-card__title">Payment Method</h3>
            <div className="pm-card__details">
              <span className="pm-card__card-icon">💳</span>
              <span className="pm-card__brand">{paymentMethod.brand}</span>
              <span className="pm-card__number">ending in •••• {paymentMethod.last4}</span>
              <span className="pm-card__expiry">Exp: {paymentMethod.expiry}</span>
              <span className="pm-card__powered">Powered by Stripe</span>
            </div>
          </div>
          <button
            type="button"
            className="pm-card__manage-btn"
            onClick={onNavigatePaymentMethods}
          >
            Manage Cards
          </button>
        </div>

        {/* Full Billing History Table */}
        <div className="billing-history-section">
          <h2 className="billing-section-title">Billing History & Invoices</h2>
          <div className="billing-table">
            <div className="billing-table__header">
              <span>Invoice</span>
              <span>Date</span>
              <span>Description</span>
              <span>Amount ($ & Rs)</span>
              <span>Status</span>
              <span>Download</span>
            </div>
            {invoices.map((inv) => (
              <div key={inv.id} className="billing-table__row">
                <span className="inv-id">{inv.id}</span>
                <span className="inv-date">{inv.date}</span>
                <span className="inv-desc">{inv.description}</span>
                <span className="inv-amount">
                  ${inv.amountUsd.toFixed(2)}{' '}
                  <span className="inv-pkr">/ Rs {inv.amountPkr.toLocaleString()}</span>
                </span>
                <span className="inv-status">
                  <span className="status-dot" /> {inv.status}
                </span>
                <button
                  type="button"
                  className="inv-download-btn"
                  onClick={() => handleDownloadInvoice(inv.id)}
                  title="Download invoice receipt"
                >
                  ⬇️ PDF
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Cancel Confirmation Modal */}
      {cancelModal && (
        <div className="billing-modal-overlay">
          <div className="billing-modal">
            <h3>Cancel Roxy-AI Subscription?</h3>
            <p>
              Are you sure you want to cancel your Pro plan? You will retain all autonomous scheduling, finance tracking, and 20 GB private vector memory until {plan.nextBillingDate}.
            </p>
            <div className="billing-modal__actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setCancelModal(false)}
              >
                Keep Subscription
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={handleCancelConfirm}
              >
                Confirm Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
