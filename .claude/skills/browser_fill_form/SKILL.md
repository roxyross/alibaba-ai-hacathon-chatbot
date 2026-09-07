---
name: browser_fill_form
description: "Fill and submit a form in a real browser. **Sensitive**: requires explicit user confirmation before submission, especially for payment, deletion, message-send, or account-setting changes."
sensitive: true
requires_confirmation: true
---

# browser_fill_form

## Purpose

Open a form on a page, fill specified fields with provided values, and (with confirmation) submit it.

## Inputs

- `url` (string, required) — the URL of the page with the form.
- `fields` (list of object, required) — `{selector, value, type}` per field. `type` can be `text`, `select`, `checkbox`, `radio`, `file`.
- `submit_selector` (string, optional) — selector for the submit button. If omitted, the form is filled but not submitted.
- `confirm` (bool, required) — `true` only after the user has explicitly confirmed the submission in plain language.

## Outputs

- `filled_fields`: which fields were filled, with the values used.
- `submitted`: bool.
- `post_submit_state`: `{url, title, text_excerpt}` after submission.
- `confirmation_required`: bool — if the form is sensitive and the user hasn't confirmed, the skill returns this and does nothing.

## Steps

1. Open the URL.
2. For each field: locate the element, fill it per `type`. For `file` uploads, use the provided file path; the runtime must confirm the file is what the user intended.
3. If `submit_selector` is provided AND `confirm: true`:
   - Detect whether the form is sensitive (payment, deletion, message, account settings). If yes, the runtime must have obtained explicit user confirmation *for this exact submission* (recipients, amounts, message body, etc.) before this skill is invoked.
   - Click the submit selector.
   - Capture the post-submit state.
4. If `submit_selector` is provided but `confirm: false` → return `filled_fields` and `confirmation_required: true`. Do not submit.
5. Return.

## Safety notes

- **`confirm: true` is not a substitute for user confirmation.** The runtime must obtain the user's explicit "yes, submit" for the exact data being submitted. The skill re-checks: if the form is sensitive and the runtime didn't surface the data to the user, refuse to submit regardless of the `confirm` flag.
- The user saying "just do it" once does not extend to a different submission. Re-confirm each new sensitive submission.
- File uploads: confirm the file path and name with the user before uploading.
- Multi-step forms: confirm at each step that requires user data, not just the final submit.
