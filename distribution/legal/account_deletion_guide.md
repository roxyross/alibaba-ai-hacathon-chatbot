# Account & Data Deletion Guide
**Roxy AI — Apple App Store & Google Play Data Safety Compliance**

---

### In-App Deletion Workflow
Users can permanently delete their Roxy AI account and all associated telemetry directly inside the mobile and desktop apps:
1. Open **Settings** (Click Settings cog or navigate to `roxy://settings`).
2. Select the **Account & Privacy** tab.
3. Scroll to the **Danger Zone** section and click **Delete Account & Data**.
4. A security confirmation dialog explains that this action will irreversibly remove:
   - All session histories and chat logs
   - Knowledge Vault documents and vector embeddings
   - Registered device identities and push notification tokens
   - Active billing subscriptions (canceled immediately)
5. Enter account confirmation email and click **Permanently Delete Account**.

---

### External Web Deletion Request
In compliance with Apple Guideline 5.1.1(v) and Google Play Data Safety standards, users who no longer have the app installed can request account and data erasure via our web portal:
- **Deletion URL:** `https://app.roxy.ai/account/delete`
- **Email Request:** Send an email from the registered account address to `privacy@roxy.ai` with the subject `Request Account Erasure`.

---

### Data Purging Timelines & Verification
- **Immediate (0 seconds):** Access tokens and sessions are invalidated; active WebSocket connections are terminated.
- **Synchronous Database Purge (< 1 minute):** All database rows in `users`, `chat_sessions`, `chat_messages`, `device_registrations`, and `knowledge_vault` are hard-deleted.
- **Search Indices & Caches (< 2 hours):** Redis cache keys and in-memory embeddings are purged.
- **Audit Compliance:** An irreversible cryptographically hashed tombstone audit record is retained for 30 days solely for regulatory fraud prevention before permanent expungement.
