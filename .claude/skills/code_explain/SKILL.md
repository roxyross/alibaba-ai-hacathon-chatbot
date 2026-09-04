---
name: code_explain
description: Explain what a code snippet, function, or file does in plain language. Used by the Coding Agent as its primary read path.
---

# code_explain

## Purpose

Walk a user through code they want to understand, at the level they asked for.

## Inputs

- `code` (string, required) — the snippet to explain, or a path to a file.
- `scope` (enum, optional) — `line` (a specific line), `block` (a function/block), `file` (whole file), `module` (whole module/file with imports and call graph). Default `block`.
- `level` (enum, optional) — `eli5`, `beginner`, `intermediate` (default), `expert`.
- `focus` (string, optional) — what to emphasize, e.g. "performance", "security", "error handling".

## Outputs

- `explanation`: prose explanation at the requested level.
- `key_lines`: list of `{line_number, note}` for lines worth flagging.
- `followups`: short list of things the user might want to know next.

## Steps

1. If `code` is a path, read the file.
2. If `scope` is a specific line/block, locate it.
3. Walk the code in execution order, or top-to-bottom for declarative code.
4. Adjust vocabulary and depth to `level`.
5. If `focus` is set, emphasize it; otherwise give a balanced explanation.

## Failure modes

- The code is too long to explain in one go → ask which part to start with, or break into a multi-turn explanation.
- The user asked for `line` scope but didn't give a line number → ask.
- The code has syntax errors or is incomplete → say so; explain what's there and ask for the rest.
- The user is on `expert` level but the code is trivial → don't over-explain; a one-line summary is enough.
