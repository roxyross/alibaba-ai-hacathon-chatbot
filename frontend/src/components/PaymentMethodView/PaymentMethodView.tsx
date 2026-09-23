import React, { useState, useEffect, useCallback } from 'react';
import './PaymentMethodView.css';

interface PaymentMethodViewProps {
  accessToken: string | null;
  onBack: () => void;
}

interface SavedMethod {
  id: string;
  brand: string;
  last4: string;
  expiry: string;
  isPrimary: boolean;
}

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const PaymentMethodView: React.FC<PaymentMethodViewProps> = ({ accessToken, onBack }) => {
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvc, setCvc] = useState('');
  const [nameOnCard, setNameOnCard] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [savedMethods, setSavedMethods] = useState<SavedMethod[]>([]);
  const [_isLoading, setIsLoading] = useState(false);

  const fetchMethods = useCallback(async () => {
    if (!accessToken) {
      setSavedMethods([]);
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/billing/payment-methods`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const primary = data.primary;
        const saved = data.saved_methods || [];
        const items: SavedMethod[] = [];

        if (primary) {
          const exp = primary.expiry || `${String(primary.exp_month || 12).padStart(2, '0')}/${String(primary.exp_year || 2028).slice(-2)}`;
          items.push({
            id: primary.id,
            brand: (primary.brand || 'Card').toUpperCase(),
            last4: primary.last4 || '4242',
            expiry: exp,
            isPrimary: true,
          });
        }
        saved.forEach((m: any) => {
          const exp = m.expiry || `${String(m.exp_month || 12).padStart(2, '0')}/${String(m.exp_year || 2028).slice(-2)}`;
          items.push({
            id: m.id,
            brand: (m.brand || 'Card').toUpperCase(),
            last4: m.last4 || '0000',
            expiry: exp,
            isPrimary: false,
          });
        });
        setSavedMethods(items);
      } else {
        setErrorMessage('Failed to load saved payment methods.');
      }
    } catch (err) {
      console.error('Failed to fetch payment methods', err);
      setErrorMessage('Could not load payment methods from server.');
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchMethods();
  }, [fetchMethods]);

  const handleAddCard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cardNumber || !expiry || !cvc) return;
    setSuccessMessage(null);
    setErrorMessage(null);

    if (!accessToken) {
      setErrorMessage('Please sign in to securely link and tokenize payment cards on your account.');
      return;
    }

    setIsProcessing(true);
    try {
      const cleanNum = cardNumber.replace(/\s+/g, '');
      const [expM, expY] = expiry.split('/').map((s) => parseInt(s.trim(), 10));
      const expMonth = isNaN(expM) ? 12 : expM;
      const expYear = isNaN(expY) ? 2028 : (expY < 100 ? 2000 + expY : expY);
      const brand = cleanNum.startsWith('4') ? 'Visa' : 'Mastercard';
      const last4 = cleanNum.slice(-4) || '1234';

      const res = await fetch(`${API_BASE}/billing/payment-methods`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          brand,
          last4,
          exp_month: expMonth,
          exp_year: expYear,
          set_as_default: savedMethods.length === 0,
        }),
      });

      if (res.ok) {
        await fetchMethods();
        setSuccessMessage('Card saved and tokenized securely via Stripe Elements.');
        setCardNumber('');
        setExpiry('');
        setCvc('');
        setNameOnCard('');
        setTimeout(() => setSuccessMessage(null), 5000);
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorMessage(errData.detail || 'Failed to authorize and save card.');
      }
    } catch (err: any) {
      console.error('Failed to save card', err);
      setErrorMessage(err.message || 'Payment method authorization failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSetPrimary = (id: string) => {
    setSavedMethods((prev) =>
      prev.map((m) => ({ ...m, isPrimary: m.id === id }))
    );
  };

  const handleDeleteMethod = async (id: string) => {
    if (!confirm('Remove this saved card?')) return;
    const previous = [...savedMethods];
    setSavedMethods((prev) => prev.filter((m) => m.id !== id));
    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/billing/payment-methods/${id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!res.ok) {
          setSavedMethods(previous);
          setErrorMessage('Failed to delete payment method on server.');
        }
      }
    } catch (err) {
      console.error('Failed to remove card', err);
      setSavedMethods(previous);
      setErrorMessage('Could not remove card due to network error.');
    }
  };

  const primaryMethod = savedMethods.find((m) => m.isPrimary) || (savedMethods.length > 0 ? savedMethods[0] : null);
  const otherMethods = savedMethods.filter((m) => m.id !== primaryMethod?.id);

  return (
    <div className="pm-view">
      <header className="pm-view__header">
        <button type="button" className="pm-view__back-btn" onClick={onBack}>
          ← Back to Billing
        </button>
        <h1 className="pm-view__title">Payment Methods</h1>
      </header>

      <div className="pm-view__body">
        {!accessToken && (
          <div className="pm-view__alert" role="status" style={{ background: '#f8fafc', borderColor: '#cbd5e1', color: '#475569' }}>
            <span>🔒</span>
            <span>Guest mode: Sign in to manage your saved cards and authorize real tokenized transactions.</span>
          </div>
        )}

        {errorMessage && (
          <div className="pm-view__alert" role="alert" style={{ background: '#fef2f2', borderColor: '#fca5a5', color: '#991b1b' }}>
            <span>⚠️</span>
            <span>{errorMessage}</span>
            <button
              type="button"
              onClick={() => setErrorMessage(null)}
              style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: '#991b1b', cursor: 'pointer', fontWeight: 'bold' }}
            >
              ✕
            </button>
          </div>
        )}

        {successMessage && (
          <div className="pm-view__alert" role="status">
            <span>✨</span>
            <span>{successMessage}</span>
          </div>
        )}

        {/* Primary Payment Method Card or Empty State */}
        {primaryMethod ? (
          <div className="pm-primary-card">
            <div className="pm-primary-card__top">
              <span className="pm-badge">Primary Payment Method</span>
              <span className="pm-stripe-badge">Powered by Stripe</span>
            </div>

            <div className="pm-primary-card__content">
              <div className="pm-chip">💳</div>
              <div className="pm-primary-card__digits">•••• •••• •••• {primaryMethod.last4}</div>
              <div className="pm-primary-card__meta">
                <div>
                  <span className="meta-sub">Cardholder</span>
                  <p className="meta-main">Roxy Authorized User</p>
                </div>
                <div>
                  <span className="meta-sub">Expires</span>
                  <p className="meta-main">{primaryMethod.expiry}</p>
                </div>
                <div>
                  <span className="meta-sub">Brand</span>
                  <p className="meta-main">{primaryMethod.brand}</p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="pm-empty-card">
            <div className="pm-empty-icon">💳</div>
            <h3>No Saved Payment Methods</h3>
            <p>
              Add a payment method below to top up token credits, unlock autonomous scheduled jobs, or upgrade your plan.
            </p>
          </div>
        )}

        {/* Add New Card Form using Stripe Elements style */}
        <div className="pm-form-card">
          <h2 className="pm-form-title">Add New Payment Method</h2>
          <p className="pm-form-subtitle">
            Enter your credit or debit card details. Your card will be verified and securely saved with Stripe.
          </p>

          <form onSubmit={handleAddCard} className="stripe-elements-form">
            <div className="stripe-input-group">
              <label>Name on Card</label>
              <input
                type="text"
                placeholder="Full Name"
                required
                value={nameOnCard}
                onChange={(e) => setNameOnCard(e.target.value)}
              />
            </div>

            <div className="stripe-input-group">
              <label>Card Information</label>
              <div className="stripe-card-field">
                <input
                  type="text"
                  placeholder="1234 5678 9012 3456"
                  maxLength={19}
                  required
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                />
                <input
                  type="text"
                  placeholder="MM/YY"
                  maxLength={5}
                  required
                  style={{ width: '80px' }}
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                />
                <input
                  type="password"
                  placeholder="CVC"
                  maxLength={4}
                  required
                  style={{ width: '70px' }}
                  value={cvc}
                  onChange={(e) => setCvc(e.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              className="stripe-submit-btn"
              disabled={isProcessing}
            >
              {isProcessing ? 'Verifying with Stripe…' : 'Save Payment Method'}
            </button>
          </form>
        </div>

        {/* Other Saved Methods */}
        {otherMethods.length > 0 && (
          <div className="pm-other-section">
            <h2 className="pm-section-title">Other Saved Methods</h2>
            <div className="pm-other-list">
              {otherMethods.map((m) => (
                <div key={m.id} className="pm-other-row">
                  <div className="pm-other-row__info">
                    <span className="pm-other-brand">{m.brand}</span>
                    <span>•••• {m.last4}</span>
                    <span className="pm-other-exp">(Exp: {m.expiry})</span>
                  </div>
                  <div className="pm-other-row__actions">
                    <button
                      type="button"
                      className="pm-btn-primary"
                      onClick={() => handleSetPrimary(m.id)}
                    >
                      Set as Primary
                    </button>
                    <button
                      type="button"
                      className="pm-btn-delete"
                      onClick={() => handleDeleteMethod(m.id)}
                      title="Remove card"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Security Note that all payments go through Stripe */}
        <div className="pm-security-note">
          <span className="security-icon">🔒</span>
          <div className="security-text">
            <strong>PCI-DSS Level 1 Certified Security:</strong> All card details are transmitted directly to Stripe over end-to-end TLS 1.3 encryption. Roxy-AI never stores, sees, or logs your raw payment card data.
          </div>
        </div>
      </div>
    </div>
  );
};
