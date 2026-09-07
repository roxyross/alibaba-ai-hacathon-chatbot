---
name: bank_connect
description: Connect to a bank account via Plaid OAuth and retrieve account data — balances, transactions, and spending summaries. Sensitive — requires explicit user confirmation before connecting. Data is never stored raw; tokens are ephemeral.
sensitive: true
inputs:
  op: '"connect" | "disconnect" | "list_accounts" | "get_transactions" | "get_balance"'
  institution: Bank name (e.g. "Chase", "Bank of America")
  access_token: Ephemeral Plaid access token (from OAuth callback)
  account_ids: List of account IDs to query (optional, defaults to all)
  start_date: Start date for transactions (YYYY-MM-DD, default 90 days ago)
  end_date: End date for transactions (YYYY-MM-DD, default today)
---

# bank_connect

Connect to a user's bank account using Plaid's OAuth 2.0 flow. This skill handles the secure token exchange, account listing, and transaction retrieval. Raw credentials are never handled — only short-lived OAuth tokens.

## Operations

### `connect`
Initiates a Plaid Link OAuth flow. Returns a `link_token` for the frontend to render the Plaid Link modal. After the user completes the flow, the frontend passes the `public_token` back via `exchange_token`.

### `exchange_token`
Exchanges a `public_token` from Plaid Link for a persistent `access_token`. Stores the mapping in the backend's secure token store.

### `list_accounts`
Returns all accounts for the connected institution — checking, savings, credit cards, loans — with current balances.

### `get_transactions`
Returns transactions for the specified date range (default: last 90 days), categorized by Plaid's automatic categorization engine.

### `get_balance`
Returns the current balance for specified accounts.

### `disconnect`
Revokes the Plaid access token and removes the institution connection.

## Data handling

- Access tokens are stored in the backend's encrypted token store, not in memory or the database.
- Transactions are returned but not persistently stored by the runtime — the user can ask to summarize them, but the raw data is ephemeral.
- Account numbers are masked by Plaid (e.g. "••••1234") — we never expose full account numbers.
- The `bank_connect` skill itself does not store financial data; it retrieves and returns.

## Error responses

- If Plaid is not configured: returns a clear error with setup instructions.
- If the access token is expired: returns a re-authentication prompt.
- If the institution is not supported by Plaid: lists supported alternatives.

## Privacy

- This skill is `sensitive: true`. The Coordinator always confirms with the user before connecting a new institution.
- Transaction data is shown to the user in-context only; it is not stored in memory unless the user explicitly asks to remember a summary.
