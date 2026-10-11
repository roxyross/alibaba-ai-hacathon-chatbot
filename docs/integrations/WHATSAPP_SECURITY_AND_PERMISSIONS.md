# ROXY-AI Universal WhatsApp Security & Permissions Architecture
**Document ID:** `docs/integrations/WHATSAPP_SECURITY_AND_PERMISSIONS.md`  
**Security Classification:** Authoritative Security Policy  
**Scope:** ConfirmationGate Integration, HMAC Binding, Anti-Replay, PII Redaction & Webhook Verification

---

## 1. Zero Simulation Doctrine (E0–E5 Hierarchy)

ROXY-AI operates under the strict **Zero Simulation Doctrine**:
- **E0 (Zero Simulation):** Never simulate real external actions. No fake screenshots, mock delivery receipts described as real, or hardcoded successes.
- **E1 (Truthful Telemetry):** Every state returned by an adapter corresponds to verified physical reality (e.g. DOM query selector match, OS window handle, or Meta HTTP 200 with `wamid`).
- **E2 (Fail Closed):** If any credential, session, allowlist match, or HMAC challenge token is missing, expired, or invalid, the operation immediately halts in `BLOCKED` or `FAILED`.
- **E3 (Explicit Approval):** An AI agent runtime cannot autonomously send a message without a human-in-the-loop cryptographic challenge resolution.
- **E4 (Anti-Spam & Zero Bulk Send):** Outbound sending is limited to strictly 1 recipient and 1 approved message text per challenge. Automated loops, contact enumeration, and bulk broadcasting are technically forbidden.
- **E5 (Auditable Provenance):** Every execution generates a structured `WhatsAppOperationResult` with sanitized telemetry, timestamp, and audit trail.

---

## 2. Cryptographic Approval Binding (ConfirmationGate)

Outbound WhatsApp sending is classified as `RiskTier.HIGH` (risk score 80) in ROXY's security architecture.

### 2.1 Challenge Generation
Before any dispatch, `WhatsAppService.create_send_challenge()` generates a `ConfirmationChallengeResponse`:
```python
token_seed = f"{challenge_id}:{user_id}:{action_type}:{int(expires_at.timestamp())}".encode()
challenge_token = hmac.new(_SECRET_KEY, token_seed, hashlib.sha256).hexdigest()
```

The challenge payload binds:
- `recipient_normalized`: Target E.164 phone number
- `message_hash`: SHA-256 digest of exact message body (`hashlib.sha256(message.encode("utf-8")).hexdigest()`)
- `route`: Selected route (`desktop`, `web`, `cloud_api`)
- `run_id`: Unique operation execution ID
- `ttl_seconds`: Maximum challenge lifetime (default 180 seconds)

### 2.2 Tamper-Proof Invalidation
Prior to executing the send action, `WhatsAppService.validate_send_approval()` strictly revalidates:
1. Challenge status == `ConfirmationStatus.APPROVED`
2. Challenge `user_id` == executing `user_id`
3. Challenge `run_id` == active `run_id`
4. Challenge `recipient_normalized` == active recipient
5. Challenge `message_hash` == active `SHA-256(message)`
6. Challenge `route` == active route

If the user or an autonomous subagent attempts to alter the message text, change the phone number, or switch from Web to Desktop, the validation fails immediately with `REJECTED: Outbound message text was altered after user approval`.

### 2.3 Single-Use Token & Replay Prevention
Every approved challenge token can only be consumed once.
Upon successful validation, the `challenge_id` is permanently added to `_consumed_challenge_tokens`. Any subsequent attempt to replay the token (e.g., from an automated retry loop or duplicate agent call) fails with:
`REJECTED: Send challenge token has already been consumed (replay / duplicate send prevented).`

---

## 3. Privacy, PII Protection & Secret Redaction

1. **Phone Number Masking:**
   - Phone numbers are never written in plain text to standard logs, audit records, or frontend notification payloads.
   - All logs use `WhatsAppBaseAdapter.redact_phone_number()`:
     - `+14155552671` $\to$ `+14*****671`
     - Numbers with $\le 6$ characters $\to$ `+XXXXXXX`
2. **Secret Isolation:**
   - Meta `WHATSAPP_ACCESS_TOKEN` is loaded purely server-side. It is never included in frontend bundles, never serialized to API responses, and never logged.
   - If an HTTP request fails, error logs print only HTTP status codes and redacted error messages.
3. **Non-Invasive Browser Automation:**
   - The Playwright web adapter never exports or dumps WhatsApp cookies or IndexedDB sessions.
   - No scripts are injected into `web.whatsapp.com` DOM.
   - User sessions reside strictly in local user profile directories with standard OS file permissions.

---

## 4. Webhook Security (Meta Cloud API)

For incoming delivery receipts and status notifications:
1. **Signature Verification:**
   Every POST request to `/api/v1/integrations/whatsapp/webhook` is verified against the `X-Hub-Signature-256` header:
   ```python
   computed_sig = hmac.new(app_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
   is_valid = hmac.compare_digest(expected_sig, computed_sig)
   ```
   Requests failing signature verification are rejected with HTTP 403.
2. **Untrusted Content Doctrine:**
   Incoming webhook payloads are treated strictly as untrusted data. Incoming message bodies are never evaluated as privileged agent commands, shell scripts, or workspace modifications.
   Only delivery statuses (`sent`, `delivered`, `read`, `failed`) linked to valid `wamid` records are processed.

---

## 5. Desktop Automation Isolation (Windows 11)

1. **Bounded Timeouts:**
   All Windows UI Automation interactions are wrapped in strict 5-second to 10-second deadlines.
2. **Interactive Desktop Attachment:**
   `WindowsUIAutomationEngine.ensure_interactive_desktop()` connects worker threads to `OpenDesktopW("Default")`, preventing sandbox hangs while respecting Windows desktop isolation.
3. **Process Ownership Boundary:**
   Roxy automation never terminates unrelated applications (e.g. existing Chrome instances, IDEs, or user windows).
