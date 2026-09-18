import React, { useState, useEffect, useCallback } from 'react';
import './BillingView.css';

interface BillingViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigatePricing?: () => void;
  onNavigateUsage?: () => void;
  onNavigatePaymentMethods?: () => void;
}

interface PlanState {
  id: string;
  name: string;
  priceUsd: number;
  pricePkr: number;
  period: string;
  status: string;
  nextBillingDate: string | null;
  renewsAutomatically: boolean;
  provider?: string;
}

interface PaymentMethodSummary {
  brand: string;
  last4: string;
  expiry: string;
  poweredBy: string;
}

interface InvoiceItem {
  id: string;
  date: string;
  description: string;
  amountUsd: number;
  amountPkr: number;
  status: string;
  invoicePdfUrl?: string;
}

export const BillingView: React.FC<BillingViewProps> = ({
  accessToken,
  onBack,
  onNavigatePricing,
  onNavigateUsage,
  onNavigatePaymentMethods,
}) => {
  const [cancelModal, setCancelModal] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);
  const [_isLoading, setIsLoading] = useState(false);

  const [plan, setPlan] = useState<PlanState>({
    id: 'free',
    name: 'Free (BYOK)',
    priceUsd: 0.0,
    pricePkr: 0.0,
    period: 'forever',
    status: 'Active',
    nextBillingDate: null,
    renewsAutomatically: false,
  });

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethodSummary | null>(null);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);

  const fetchBillingData = useCallback(async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      // 1. Fetch Subscription
      const subRes = await fetch('/api/v1/billing/subscription', {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (subRes.ok) {
        const subData = await subRes.json();
        const p = subData.plan;
        if (p) {
          setPlan({
            id: p.id || 'free',
            name: p.name || (p.id === 'free' ? 'Free (BYOK)' : 'Pro'),
            priceUsd: typeof p.price_usd === 'number' ? p.price_usd : 0,
            pricePkr: typeof p.price_pkr === 'number' ? p.price_pkr : 0,
            period: p.id === 'free' ? 'forever' : 'per month',
            status: p.status === 'active' ? 'Active' : p.status || 'Active',
            nextBillingDate: p.next_billing_date ? new Date(p.next_billing_date).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }) : null,
            renewsAutomatically: !p.cancel_at_period_end,
            provider: p.provider || 'stripe',
          });
        }
      }

      // 2. Fetch Payment Methods
      const pmRes = await fetch('/api/v1/billing/payment-methods', {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (pmRes.ok) {
        const pmData = await pmRes.json();
        const prim = pmData.primary;
        if (prim) {
          const exp = prim.expiry || `${String(prim.exp_month || 12).padStart(2, '0')}/${String(prim.exp_year || 2028).slice(-2)}`;
          setPaymentMethod({
            brand: (prim.brand || 'Card').toUpperCase(),
            last4: prim.last4 || '4242',
            expiry: exp,
            poweredBy: prim.powered_by || (prim.provider === 'safepay' ? 'Safepay' : 'Stripe'),
          });
        } else {
          setPaymentMethod(null);
        }
      }

      // 3. Fetch Invoices
      const invRes = await fetch('/api/v1/billing/invoices', {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (invRes.ok) {
        const invData = await invRes.json();
        if (Array.isArray(invData.invoices)) {
          setInvoices(
            invData.invoices.map((inv: any) => ({
              id: inv.id,
              date: inv.date,
              description: inv.description,
              amountUsd: inv.amount_usd ?? inv.amountUsd ?? 0,
              amountPkr: inv.amount_pkr ?? inv.amountPkr ?? 0,
              status: inv.status || 'Paid',
              invoicePdfUrl: inv.invoice_pdf_url,
            }))
          );
        }
      }
    } catch (err) {
      console.error('Failed to fetch billing data', err);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchBillingData();
  }, [fetchBillingData]);

  const handleDownloadInvoice = (invId: string) => {
    alert(`Downloading PDF receipt for invoice ${invId}...`);
  };

  const handleCancelConfirm = async () => {
    setCancelModal(false);
    try {
      if (accessToken) {
        await fetch('/api/v1/billing/cancel', {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        await fetchBillingData();
      }
      setNotification('Your subscription cancellation is confirmed. You will retain access until the end of your billing cycle.');
      setTimeout(() => setNotification(null), 6000);
    } catch (err) {
      console.error('Failed to cancel subscription', err);
    }
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
              {plan.pricePkr > 0 && (
                <span className="current-plan__pkr">/ Rs {plan.pricePkr.toLocaleString()}</span>
              )}
              <span className="current-plan__period"> {plan.period}</span>
            </p>
            <div className="current-plan__meta">
              {plan.nextBillingDate ? (
                <>
                  <span>Next billing date: <strong>{plan.nextBillingDate}</strong></span>
                  <span>•</span>
                  <span>Auto-renews via {plan.provider === 'safepay' ? 'Safepay' : 'Stripe'}</span>
                </>
              ) : (
                <span>No recurring charges active • Upgrade anytime to unlock Pro tools</span>
              )}
            </div>
          </div>

          <div className="current-plan__actions">
            {plan.priceUsd > 0 ? (
              <>
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
              </>
            ) : (
              <button
                type="button"
                className="current-plan__change-btn"
                onClick={onNavigatePricing}
              >
                Upgrade to Pro
              </button>
            )}
          </div>
        </div>

        {/* Payment Method Summary */}
        <div className="billing-card payment-method-card">
          <div className="pm-card__info">
            <h3 className="pm-card__title">Payment Method</h3>
            {paymentMethod ? (
              <div className="pm-card__details">
                <span className="pm-card__card-icon">💳</span>
                <span className="pm-card__brand">{paymentMethod.brand}</span>
                <span className="pm-card__number">ending in •••• {paymentMethod.last4}</span>
                <span className="pm-card__expiry">Exp: {paymentMethod.expiry}</span>
                <span className="pm-card__powered">Powered by Stripe</span>
              </div>
            ) : (
              <div className="pm-card__details">
                <span className="pm-card__card-icon">💳</span>
                <span className="pm-card__number" style={{ color: 'var(--color-muted, #64748b)' }}>
                  No saved payment methods on file
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            className="pm-card__manage-btn"
            onClick={onNavigatePaymentMethods}
          >
            {paymentMethod ? 'Manage Cards' : '+ Add Card'}
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
            {invoices.length === 0 ? (
              <div className="billing-empty-invoices">
                <div className="billing-empty-icon">📄</div>
                <h4>No Invoices Yet</h4>
                <p>Your subscription receipts and credit top-up records will appear here.</p>
              </div>
            ) : (
              invoices.map((inv) => (
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
              ))
            )}
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
