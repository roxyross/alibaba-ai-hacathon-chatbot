# ROXY-AI — NEXT PHASE (ROXY 2.0) BACKLOG & EXTERNAL LAUNCH GATES

**Document ID:** `ROXY-NPB-01`  
**Date:** October 16, 2026  
**Scope:** Post-Merge Feature Enhancements & External Production Infrastructure Gates  
**Status:** **NON-BLOCKING FOR MASTER MERGE**

---

## 1. Executive Summary

This backlog defines planned future enhancements for Roxy 2.0 and distinguishes them cleanly from the current production release scope. None of the items listed below are repository code defects or merge blockers; all repository-controlled blockers for the core release have been remediated and verified.

---

## 2. External Launch Gates (Owner Action Items at Cutover)

The following 5 gates require external credentials, domain control, or physical hardware and will be executed by the repository owner immediately prior to public launch:

### GATE-01: Physical iOS & Android Device Smoke-Testing
- **Description:** Run end-to-end smoke testing on physical iPhone and Android devices to verify biometric unlock, microphone hardware permissions, and native push notifications.
- **Why Not a Code Blocker:** All responsive layouts (all 11 viewports), touch target constraints (>= 44px), and PWA manifests are 100% verified via automated Vitest and Playwright suites.
- **Owner Action:** Deploy PWA/mobile client to physical testing devices and conduct manual audio/touch smoke test.

### GATE-02: Production Domain DNS & Google OAuth Verification
- **Description:** Point custom DNS records (`app.roxy.ai`, `api.roxy.ai`) to Cloud Run / Vercel and submit the Google Cloud OAuth Consent Screen for production verification.
- **Why Not a Code Blocker:** Token encryption at rest, tenant isolation, CSRF state verification, and redirect allowlists are 100% verified on real PostgreSQL.
- **Owner Action:** Add DNS A/CNAME records and complete Google OAuth verification checklist in GCP console.

### GATE-03: Production Payment Merchant Provisioning (Stripe & Safepay)
- **Description:** Inject live Stripe (`sk_live_...`, `whsec_...`) and Safepay live production API keys into Cloud Run Secret Manager upon merchant approval.
- **Why Not a Code Blocker:** Fail-closed billing configuration gate, two-phase webhook idempotency, and wallet credit/debit logic are 100% verified on real PostgreSQL.
- **Owner Action:** Add approved production merchant keys to Google Secret Manager.

### GATE-04: Dedicated Transactional Email Provider (AWS SES / Resend)
- **Description:** Configure production SPF, DKIM, and DMARC DNS records for automated welcome and billing invoice emails.
- **Why Not a Code Blocker:** Gmail OAuth skill and fallback SMTP transport are verified in integration suites.
- **Owner Action:** Complete SES/Resend domain validation in DNS.

### GATE-05: Google AI Studio Dedicated Production Quota
- **Description:** Attach a payment profile to Google AI Studio for production tier Gemini API rate limits (`gemini-4-argon` and `gemini-3.8-flash`).
- **Why Not a Code Blocker:** Model provider gateway, automatic retry, and fallback failover are 100% verified.
- **Owner Action:** Enable pay-as-you-go billing tier in Google AI Studio.

---

## 3. Post-Merge Roxy 2.0 Feature Roadmap

| Feature ID | Roadmap Item | Description | Dependencies | Scope Estimate |
| :--- | :--- | :--- | :--- | :--- |
| **R2-FEAT-01** | ElevenLabs Advanced Voice Presets | Expand the voice studio with ultra-realistic ElevenLabs neural voices alongside Gemini 3.8 Flash TTS. | ElevenLabs API key | Small |
| **R2-FEAT-02** | Multilingual Urdu & Roman Urdu Tuning | Fine-tune intent classification and transliteration for colloquial Roman Urdu and Hindi voice interactions. | Model fine-tuning data | Medium |
| **R2-FEAT-03** | Custom MCP Connector Marketplace | Public portal for users to register and share external Model Context Protocol (MCP) tool servers. | MCP SDK | Medium |
| **R2-FEAT-04** | Collaborative Multi-Agent Canvas | Real-time multi-agent canvas where multiple specialized agents collaborate visually on software architecture. | WebSocket cluster | Large |
