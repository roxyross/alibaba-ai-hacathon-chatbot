---
name: speech_to_text
description: Transcribe an audio stream to text in real time, with partial transcripts as the user speaks. Used by the Voice Agent as its input.
---

# speech_to_text

## Purpose

Stream an audio input (microphone, phone call, audio file) and emit partial and final transcripts.

## Inputs

- `audio_source` (object, required) — the audio stream or file. Streaming sources emit partial results; file sources emit a single final result.
- `language` (string, optional) — BCP-47 code, e.g. `en-US`. Default: auto-detect.
- `interim_results` (bool, optional, default true) — emit partial transcripts as the user speaks.

## Outputs

- Streaming: a sequence of `partial` and `final` transcript events.
- File: a single `final` transcript with timing info per word.

## Steps

1. Open the audio source.
2. Send chunks to the runtime's STT provider.
3. Emit `partial` events as partials arrive.
4. On end-of-utterance, emit a `final` event with the full transcript.
5. Close the stream.

## Failure modes

- Provider down → surface a clear error; the Voice Agent should tell the user.
- Low-confidence transcript → mark the final with `confidence: low`; the agent should restate its understanding.
- Audio is silent or below noise floor → emit empty partials; do not invent words.
- Long pause → emit a `silence` event so the agent can decide to prompt the user or end the session.
