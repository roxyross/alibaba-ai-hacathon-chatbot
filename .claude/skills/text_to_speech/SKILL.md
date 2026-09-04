---
name: text_to_speech
description: Convert text to spoken audio in real time, streaming sentences as they're ready. Used by the Voice Agent as its output.
---

# text_to_speech

## Purpose

Synthesize speech from text and stream the audio to the user's speaker / phone.

## Inputs

- `text` (string, required) — the text to speak. Plain prose; SSML is supported if the provider supports it.
- `voice` (string, optional) — voice ID; default is the user's preferred voice.
- `speed` (float, optional, default 1.0).
- `interruptible` (bool, optional, default true) — if true, allow the user to interrupt mid-utterance.

## Outputs

- An audio stream (chunked).
- A `completed: bool` event when finished (or interrupted).

## Steps

1. Tokenize the input into sentences (or smaller chunks for low-latency streaming).
2. Synthesize each chunk and stream the audio as it becomes available.
3. If interrupted by the user, stop emitting and return `completed: false`.
4. Return `completed: true` when the last chunk finishes.

## Failure modes

- Provider down → surface a clear error; the agent should fall back to text output.
- Text is empty → no-op; return `completed: true` immediately.
- Voice ID unknown → fall back to the default voice; surface the fallback.
- Long text → chunk and stream; do not buffer the whole reply before starting to speak.
