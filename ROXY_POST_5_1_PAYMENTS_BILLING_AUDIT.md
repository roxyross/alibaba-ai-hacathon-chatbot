# ROXY-AI — POST-PHASE 5.1: PAYMENTS, SUBSCRIPTIONS & BILLING AUDIT
*(Workstream N Deliverable)*

## 1. Billing Architecture & Provider Ecosystem

Roxy-AI's monetization and billing subsystem integrates multi-currency payment providers with strict entitlement enforcement:

- **Stripe Provider:** [backend/src/app/billing/providers/stripe_provider.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/billing/providers/stripe_provider.py) handles international credit card checkouts and recurring subscriptions.
- **Safepay Provider:** [backend/src/app/billing/providers/safepay_provider.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/billing/providers/safepay_provider.py) handles Pakistan Rupee (PKR) and mobile wallet payments.
- **Raast Payment Engine:** [backend/src/app/raast/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/raast/) generates instant Pakistani payment QR codes and payment requests.
- **Frontend Views:** [BillingView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Billing/BillingView.tsx), [PricingPlans.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/PricingPlans/PricingPlans.tsx), and [PaymentMethodView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/PaymentMethods/PaymentMethodView.tsx).

---

## 2. Production Security & Fail-Closed Enforcement

A critical security principle enforced across the payment system is **Strict Fail-Closed Behavior**:

1. **Unconfigured Provider Fail-Closed:**
   - In production (`APP_ENV=production`), if `STRIPE_SECRET_KEY` or `SAFEPAY_API_KEY` are empty or unconfigured, the checkout endpoints immediately reject transactions with `HTTP 503 Provider Unavailable`.
   - The system **never** grants free plan upgrades, simulates fake successful checkouts, or bypasses paywalls when payment credentials are missing.
2. **Webhook Signature Cryptographic Verification:**
   - Stripe webhook payloads require valid `Stripe-Signature` headers verified against `STRIPE_WEBHOOK_SECRET`. Unsigned or tampered requests are rejected (`HTTP 400`).
   - Safepay webhook requests verify HMAC-SHA256 signatures before provisioning credits.
3. **Card Data Isolation (PCI-DSS Compliance):**
   - The frontend never collects or transmits raw credit card numbers to the FastAPI backend. All card entry fields utilize Stripe Elements / Safepay Checkout modals, returning tokenized identifiers (`pm_...`).

---

## 3. Subscription Lifecycle & Credit Tracking

| Plan Tier | Monthly Price | Token Quota | Model Access | Team Seats |
| :--- | :--- | :--- | :--- | :---: |
| **Free Starter** | $0 / mo | 100,000 tokens | `gemini-3.8-flash`, `gemini-3.6-flash` | 1 |
| **Pro Developer**| $20 / mo | 5,000,000 tokens | All Gemini, Grok, DeepSeek models | 1 |
| **Team Hub** | $50 / mo | 15,000,000 tokens| All models + Cowork pair copilot | 5 |
| **Enterprise** | Custom | Unlimited | Dedicated routing, BYOK, custom SLAs | Unlimited |

- **Usage Logging:** Every AI request records token consumption in `token_usage_logs` and `UsageLog` with exact model names (defaulting to `gemini-3.8-flash`).

---

## 4. Test Verification Evidence

- `backend/tests/integration/test_phase8_payments.py`:
  - `test_unconfigured_providers_fail_closed_in_production` (**PASS**).
  - Stripe checkout session creation and customer portal redirect (**PASS**).
  - Safepay tracker creation and webhook signature validation (**PASS**).
  - Webhook idempotency (duplicate webhook events do not double-credit users) (**PASS**).
  - Overall suite: **19 integration tests passing**.
- `backend/tests/integration/test_phase8_finance_usage_billing.py`: Usage summary aggregation, quota exhaustion alerts, invoice generation (**PASS**).
