---
name: email_draft
description: Compose an email — subject, body, recipients — and return a draft for the user to review. Does NOT send. Used by user-facing agents when the user wants to write an email.
---

# email_draft

## Purpose

Compose a draft email and return it for the user to review before any send action.

## Inputs

- `to` (list of string, required) — recipient email addresses.
- `cc` (list of string, optional) — CC addresses.
- `bcc` (list of string, optional) — BCC addresses.
- `subject` (string, required) — the subject line.
- `body` (string, required) — the body. Plain text or HTML.
- `reply_to_message_id` (string, optional) — if this is a reply, the message ID being replied to.
- `attachments` (list of `{name, path}`, optional) — files to attach.

## Outputs

- `draft_id`: the draft's ID (for later `email_send`).
- `preview`: rendered preview of the email.
- `warnings`: any concerns (e.g. "this is the first time you're emailing this recipient", "the body has a placeholder still in it").

## Steps

1. Validate all email addresses (basic shape check; full validation at send time).
2. Render the body to a preview (text or HTML → displayable form).
3. Sanity-check the body for common issues: unfilled placeholders, accidental internal notes, missing attachment references.
4. Persist the draft.
5. Return the draft ID + preview + warnings.

## Failure modes

- Recipient address is malformed → reject with a clear error; don't auto-correct.
- Body is empty or only placeholders → warn the user.
- Attachment file doesn't exist → reject the draft.
- Draft store is full → surface to the user; ask them to delete old drafts.
