---
name: browser_navigate
description: Drive a real browser to a URL and perform a sequence of read-only actions (navigate, click, scroll, extract). Read-only variant of browser form-filling. Used by the Browser Agent.
---

# browser_navigate

## Purpose

Open a URL and perform a planned sequence of read-only browser actions: navigate, click links/buttons, scroll, hover, extract text/tables/links. Does not fill forms or submit.

## Inputs

- `url` (string, required) — the starting URL.
- `actions` (list of object, required) — ordered actions: `{type: navigate|click|scroll|hover|extract_text|extract_table|extract_links|wait_for, ...}`.
- `timeout_seconds` (int, optional, default 60) — total wall-clock cap for the flow.
- `extract_selectors` (object, optional) — CSS selectors to extract on each page.

## Outputs

- `pages_visited`: list of URLs in order.
- `extractions`: per-action extraction results (text, table rows, links).
- `screenshot_paths`: optional screenshots at key points.
- `final_state`: `{url, title, text_excerpt}`.

## Steps

1. Open the browser session (or reuse one from a prior `browser_navigate` / `browser_fill_form` in the same user session).
2. For each action in order:
   - `navigate(url)` → go to the URL.
   - `click(selector)` → click an element.
   - `scroll(direction|position)` → scroll the page.
   - `hover(selector)` → hover an element.
   - `extract_*` → pull content per selector.
   - `wait_for(selector|condition)` → wait up to N seconds.
3. Capture a final state and any requested screenshots.
4. Close the session if it was opened for this flow and not part of a longer session.
5. Return.

## Failure modes

- Page doesn't load → retry up to 2×; then surface the error with the URL and last-known state.
- Selector not found → retry briefly (in case of slow render); then surface; don't guess.
- Page navigates off-domain unexpectedly → stop; surface the redirect to the user.
- CAPTCHA appears → stop; the user must solve it (or approve a CAPTCHA service).
- Timeout → return whatever state was reached; surface the partial result.
