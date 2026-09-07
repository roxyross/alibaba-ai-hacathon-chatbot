---
name: email_send
description: "Send an email — either a previously composed draft or a one-shot message. **Sensitive**: requires explicit user confirmation before dispatch."
sensitive: true
requires_confirmation: true
---

# email_send

## Purpose

Send an email through the user's connected mail provider. Sensitive — irreversible once sent.

## Inputs

- `draft_id` (string, optional) — ID of a draft from `email_draft`. If provided, the draft is sent as-is.
- OR a one-shot message: `to`, `subject`, `body` (same shape as `email_draft`).
- `confirm` (bool, required) — the caller must have already obtained explicit user confirmation. Setting `confirm: false` is a no-op that returns the would-be-send for review.

## Outputs

- `message_id`: the provider's ID for the sent message.
- `sent_at`: timestamp.
- `delivery_status`: `queued`, `sent`, or `failed`.

## Steps

1. If `draft_id` is provided, load the draft.
2. Render the final message (recipients, subject, body, attachments).
3. Re-validate: addresses, attachment existence, body not empty.
4. **Pre-send confirmation gate**: the runtime must have already surfaced this message to the user in plain language and received explicit confirmation. The skill refuses to run without it.
5. Send via the provider.
6. Mark the draft as sent (do not delete — the user may want to refer to it).
7. Return.

## Safety notes

- The `confirm` flag is **not** a substitute for the runtime's confirmation gate. The runtime must obtain the user's explicit "yes, send it" before this skill is invoked at all.
- The skill does not retry aggressively. One attempt; if it fails, surface the error to the user.
- "Reply all" is treated as a sensitive action even if the original message used "reply all" — recipients change between threads.
- Bcc is preserved as specified; do not silently promote Bcc recipients to To or Cc.
