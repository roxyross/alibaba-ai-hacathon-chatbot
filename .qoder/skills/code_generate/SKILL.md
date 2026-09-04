---
name: code_generate
description: Generate new code in a specified language and style. Used by the Coding Agent as its primary write path.
---

# code_generate

## Purpose

Produce new source code that matches the user's stated requirements and the surrounding project's conventions.

## Inputs

- `task` (string, required) — what the code should do.
- `language` (string, required) — e.g. `python`, `typescript`, `rust`.
- `context_files` (list of path, optional) — files to read for style/conventions.
- `constraints` (list of string, optional) — e.g. `no new deps`, `match existing error-handling pattern`.
- `output_path` (path, optional) — if provided, write directly. Otherwise return the code as a string.

## Outputs

- `code`: the generated source.
- `language`: the language it was written in.
- `explanation`: a short note on key decisions.
- `warnings`: any deviations from the user's constraints and why.

## Steps

1. Read `context_files` to learn the project's style and conventions.
2. Draft the code, matching conventions.
3. Run any linters/type-checkers the project uses, if available locally.
4. If the code is runnable, run it in a sandbox to verify behavior.
5. Return the code + explanation + any warnings.

## Failure modes

- The task is ambiguous → ask the user to clarify before writing; don't guess.
- The code can't be verified (no sandbox, no test runner) → say so; let the user verify.
- A new dependency is the cleanest solution but the user said "no new deps" → surface the trade-off, offer a workaround, let the user decide.
- Generated code matches an existing function in the project → surface the duplication, ask if the user wants a refactor.
