---
name: quiz_generate
description: Generate a quiz (multiple choice, short answer, fill-in-the-blank) from a deck of cards or source material. Used by the Study Agent.
---

# quiz_generate

## Purpose

Build a self-test quiz from existing flashcards or from source material.

## Inputs

- `source` (string or deck_id, required) — a deck ID, a document ID, or raw text.
- `count` (int, optional, default 10) — number of questions.
- `types` (list of enum, optional) — `mcq` (multiple choice), `short_answer`, `fill_blank`. Default: all three in proportion.
- `difficulty` (enum, optional) — `easy`, `medium` (default), `hard`, or `mixed`.

## Outputs

- `quiz_id`: the quiz's ID.
- `questions`: list of `{id, type, prompt, choices (for mcq), answer, source_ref}`.
- `answer_key_hidden`: answers are returned in a separate field so the user can self-grade.

## Steps

1. If `source` is a deck ID, load the cards; if a document ID, load the doc.
2. Pick `count` facts to test, weighted by importance and recency.
3. Generate each question in the requested `type`.
4. For multiple choice: write 3 plausible distractors per question.
5. Hide the answers in a separate field; do not include them in the prompt.
6. Return.

## Failure modes

- Source has too few facts to support `count` questions → return as many as possible; surface the gap.
- A question ends up ambiguous (multiple defensible answers) → drop it and regenerate.
- Source is a deck the user already aced → surface the fact and suggest a different source.
- User asks for the answer key too early → return it; the quiz is for self-testing, not cheating prevention.
