---
name: flashcard_generate
description: Generate a deck of flashcards from source material. Used by the Study Agent as its primary retention-aid writer.
---

# flashcard_generate

## Purpose

Convert source material (text, a topic, a document, a chapter) into a deck of high-quality flashcards.

## Inputs

- `source` (string, required) — the source material. Plain text, a topic description, or a document ID.
- `count` (int, optional, default 20) — desired deck size.
- `level` (enum, optional) — `beginner`, `intermediate` (default), `expert`. Affects vocabulary and depth.
- `format` (enum, optional) — `qa` (default; question/answer), `cloze` (fill-in-the-blank), `term-def` (term/definition).
- `existing_deck_id` (string, optional) — if provided, append to this deck; otherwise create a new one.

## Outputs

- `deck_id`: the deck's ID.
- `cards`: list of `{front, back, source_ref, tags}`.
- `quality_report`: how many cards passed the quality bar; how many were dropped and why.

## Steps

1. If `source` is a document ID, fetch its content.
2. Extract the key facts/terms/definitions (LLM-driven; bounded by `count`).
3. Generate cards in the requested `format`.
4. Apply the quality bar (one thing per card, unambiguous answer, no giveaway questions).
5. Drop cards that fail the quality bar; report in `quality_report`.
6. If `existing_deck_id`, append; otherwise create a new deck.
7. Return.

## Failure modes

- Source is too short to support `count` cards → return as many as possible; surface the gap.
- Cards consistently fail the quality bar → reduce difficulty or surface to the caller; don't ship bad cards.
- Source contains information the LLM is uncertain about → mark those cards as `inferred` (caller decides whether to keep).
- Existing deck is full (quota) → surface to the caller.
