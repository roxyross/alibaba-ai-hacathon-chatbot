---
name: code_debug
description: Diagnose why code isn't behaving as expected. Read the error, trace the logic, propose a fix. Used by the Coding Agent as its primary diagnose path.
---

# code_debug

## Purpose

Help the user find and fix a bug. Reproduce, form a hypothesis, propose a minimal change, verify.

## Inputs

- `code` (string, required) — the snippet or file with the bug.
- `error` (string, optional) — the error message or stack trace.
- `expected_behavior` (string, optional) — what the user expected to happen.
- `actual_behavior` (string, optional) — what actually happened.
- `reproduction_steps` (list of string, optional) — how to reproduce.

## Outputs

- `hypothesis`: the most likely cause, stated as a single sentence.
- `evidence`: which lines / inputs / outputs support the hypothesis.
- `fix`: the minimal code change.
- `verification`: how to confirm the fix (test, manual repro, type-check).
- `alternatives`: 1–2 other plausible causes the user should rule out.

## Steps

1. **Bash** — reproduce: run the code with the user's input and confirm the failure.
2. Read the error literally: most bugs are in the first stack frame or the most recent log line. Use **Read** to fetch referenced files for call-stack tracing.
3. Form a hypothesis *before* editing. State it.
4. Identify the minimal change that would fix it without refactoring unrelated code.
5. **Edit** — apply the minimal fix.
6. **Bash** — re-run to verify the fix resolves the failure.

## Failure modes

- Can't reproduce → say so; ask the user for environment details (OS, library versions, exact input).
- The error is in a dependency, not the user's code → surface that; offer to look at the dependency if the user wants.
- Multiple plausible causes → list them in order of likelihood; let the user rule them out.
- The fix would change behavior the user relies on → surface the trade-off, don't silently change semantics.
