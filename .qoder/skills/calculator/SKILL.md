---
name: calculator
description: Evaluate a math expression safely and return the result. Used by user-facing agents when the user asks for a numerical answer that should not be estimated.
---

# calculator

## Purpose

Evaluate a math expression with high precision and return the result. Strictly sandboxed — no I/O, no side effects.

## Inputs

- `expression` (string, required) — the math expression. Standard infix notation: `+ - * / **`, parentheses, common functions (`sin`, `cos`, `log`, `sqrt`, etc.).
- `precision` (int, optional, default 10) — decimal places.
- `units` (string, optional) — if provided, the expression is interpreted in those units; result returned in SI.

## Outputs

- `result`: the numerical result.
- `expression_evaluated`: the canonical form that was evaluated (after parsing).
- `unit`: the unit the result is in (if `units` was given).

## Steps

1. Parse the expression with a math parser (not Python `eval`).
2. Reject anything outside the math grammar — no function calls, no attribute access, no imports.
3. Evaluate with arbitrary precision.
4. Round to `precision` decimal places.
5. Return.

## Failure modes

- Parse error → return a clear error with the location of the syntax issue.
- Math domain error (e.g. `sqrt(-1)`) → return a clear error; offer the complex-number variant if appropriate.
- Unreasonable result (overflow, NaN, infinity) → return a clear error; don't paper over it.
- Unit conversion error (unknown unit) → return a clear error; do not guess.
