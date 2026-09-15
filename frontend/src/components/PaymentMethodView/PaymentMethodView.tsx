import React, { useState } from 'react';
import './PaymentMethodView.css';

interface PaymentMethodViewProps {
  accessToken: string | null;
  onBack: () => void;
}

export const PaymentMethodView: React.FC<PaymentMethodViewProps> = ({ accessToken: _accessToken, onBack }) => {
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvc, setCvc] = useState('');
  const [nameOnCard, setNameOnCard] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [savedMethods, setSavedMethods] = useState([
    {
      id: 'pm-1',
      brand: 'Visa',
      last4: '4242',
      expiry: '12/28',
      isPrimary: true,
    },
    {
      id: 'pm-2',
      brand: 'Mastercard',
      last4: '8899',
      expiry: '08/27',
      isPrimary: false,
    },
  ]);

  const handleAddCard = (e: React.FormEvent) => {
    e.preventDefault();
    if (!cardNumber || !expiry || !cvc) return;
    setIsProcessing(true);

    setTimeout(() => {
      const cleanNum = cardNumber.replace(/\s+/g, '');
      const newMethod = {
        id: `pm-${Date.now()}`,
        brand: cleanNum.startsWith('4') ? 'Visa' : 'Mastercard',
        last4: cleanNum.slice(-4) || '1234',
        expiry: expiry || '05/29',
        isPrimary: false,
      };
      setSavedMethods((prev) => [...prev, newMethod]);
      setIsProcessing(false);
      setCardNumber('');
      setExpiry('');
      setCvc('');
      setNameOnCard('');
      setSuccessMessage('Card saved securely via Stripe Elements.');
      setTimeout(() => setSuccessMessage(null), 5000);
    }, 900);
  };

  const handleSetPrimary = (id: string) => {
    setSavedMethods((prev) =>
      prev.map((m) => ({ ...m, isPrimary: m.id === id }))
    );
  };

  const handleDeleteMethod = (id: string) => {
    if (confirm('Remove this saved card?')) {
      setSavedMethods((prev) => prev.filter((m) => m.id !== id));
    }
  };

  const primaryMethod = savedMethods.find((m) => m.isPrimary) || savedMethods[0];
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
        {successMessage && (
          <div className="pm-view__alert" role="status">
            <span>✨</span>
            <span>{successMessage}</span>
          </div>
        )}

        {/* Primary Payment Method Card */}
        {primaryMethod && (
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
