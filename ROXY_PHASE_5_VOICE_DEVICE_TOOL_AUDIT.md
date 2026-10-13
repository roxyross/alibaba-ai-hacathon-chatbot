# Roxy-AI — Phase 5 Voice, Device & Tool Audit

**Audited Services:**  
- Voice Pipeline: `backend/src/app/api/v1/voice.py`, `app/voice/service.py`, `app/skills/speech_to_text.py`, `app/skills/text_to_speech.py`  
- Device Automation: `backend/src/app/api/v1/device/`, `app/device/orchestrator.py`, `app/device/scanner.py`  
- Tool Registry: `backend/src/app/tools/registry.py` & `builtin.py`  
**Date:** October 13, 2026  

---

## 1. Voice & Multilingual Intelligence Pipeline Audit

### Complete Pipeline Trace
```
Microphone Audio (Web/Mobile/Desktop)
    │
    ▼
Base64 Audio Ingestion: POST /api/v1/voice/transcribe
    │
    ▼
Speech-to-Text Skill (app.skills.speech_to_text)
    ├── Primary: Groq Whisper (whisper-large-v3-turbo)
    ├── Secondary: OpenAI Whisper (whisper-1)
    └── Unconfigured Fallback: Returns empty string (triggers client Web Speech API)
    │
    ▼
Multilingual Normalization Layer (app.multilingual.service)
    ├── Detection: English, Urdu (اردو), Roman Urdu, Hindi
    └── Canonical Intent & Query Normalization
    │
    ▼
Intent Resolution & Execution Gate (ConfirmationGate)
    │
    ▼
Text-to-Speech Synthesis (app.skills.text_to_speech)
    ├── Primary: Google Gemini Multimodal Audio (voices: Kore, Puck, Fenrir, Aoede)
    ├── Secondary: OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)
    └── Tertiary: ElevenLabs
    │
    ▼
Spoken Audio (WAV/MP3) Delivered to Client Speaker
```

### Multilingual Support Matrix
| Language | Script / Modality | Ingestion Status | Intent Extraction | Voice Synthesis | Audit Evidence Level |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **English** | Latin / Typed + Spoken | Full Support | High precision | Gemini / OpenAI TTS | **VERIFIED** |
| **Urdu** | Arabic (اردو) / Spoken | Full Support | Recognized via Whisper prompt hints | Multilingual TTS | **VERIFIED** (`test_multilingual_input_layer.py`) |
| **Roman Urdu** | Latin / Typed + Spoken | Full Support | Normalized by regex lexicon map | English/Hindi phonetic TTS | **VERIFIED** (`test_multilingual_input_layer.py`) |
| **Hindi** | Devanagari / Spoken | Full Support | Recognized via Whisper vocabulary | Multilingual TTS | **VERIFIED** (`test_multilingual_input_layer.py`) |

### Provider Configuration & Offline Reality
- When cloud STT/TTS keys (`GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) are missing, the skills return empty audio/transcripts instead of fabricating fake conversations. The client gracefully falls back to the native Web Speech API (`webkitSpeechRecognition` / `speechSynthesis`).
- Physical microphone hardware and on-device speaker verification on live production phones are recorded as **BLOCKED** due to absence of attached mobile hardware in test execution environments.

---

## 2. Real Tools, Web Research & Browser Reality

| Tool / Connector | Execution Engine | Real Operation Evidence | Fallback Behavior | Audit Finding & Classification |
| :--- | :--- | :--- | :--- | :--- |
| **Calculator** | Python AST `_safe_eval_math` | Real evaluation without `eval()` | Syntax error on malformed input | **VERIFIED** — safe operator whitelist |
| **Web Search** | DuckDuckGo HTML / Tavily API | Real HTTP queries | Returns empty list with error notice (remediated in Phase J) | **VERIFIED** — fake snippet removed |
| **Headless Browser** | Playwright Chromium / httpx DOM parser | Real navigation, DOM tree extraction | Falls back to HTTP text scraping if Playwright unavailable | **VERIFIED** (`test_phase10_browser_automation.py`) |
| **Email Dispatch** | SMTP / SendGrid | Real SMTP delivery or mock | In-memory outbox during tests | **VERIFIED** (`test_phase1_auth_session.py`) |
| **Document Search** | Vector cosine similarity in pgvector | Real embeddings via `ai_gateway` | Returns empty matches if threshold unmet | **VERIFIED** (`test_file_folder_intelligence.py`) |

---

## 3. Device & App Control Surface

The device control architecture was audited across Desktop, Android, and iOS surfaces:

| Surface | Supported Capabilities | Discovery Mechanism | Security & Confirmation Gate | Audit Classification |
| :--- | :--- | :--- | :--- | :--- |
| **Windows Desktop** | App launch, window focus, process kill, UI automation via `pywinauto` | Windows Registry + Process Table (`scanner.py`) | Critical actions (kill, destructive) require server-issued ConfirmationGate token | **VERIFIED** (`test_phase4_windows_automation.py`) |
| **macOS Desktop** | App launch, window focus, AppleScript dispatch | Application bundle scanner | Confirmation challenge gate | **SOURCE-VERIFIED** |
| **Linux Desktop** | Process launch, desktop file inspection (`.desktop`) | FreeDesktop specification scan | Confirmation challenge gate | **SOURCE-VERIFIED** |
| **Android Bridge** | App intent launch via Capacitor plugin | Android PackageManager query | Permission request prompt | **BLOCKED** on physical device; **SOURCE-VERIFIED** in Capacitor bridge |
| **iOS Bridge** | URL scheme launching via Capacitor | Registered URL schemes | System confirmation dialog | **BLOCKED** on physical device; **SOURCE-VERIFIED** in Capacitor bridge |

### Destructive Action Confirmation Enforcement
- In `test_case_01` through `test_case_06` of `test_p0_security_reaudit.py`, all attempts to execute destructive commands (e.g., process termination, high-risk tools) with `bypass_confirmation=true` or without an unconsumed server-issued token were **strictly neutralized and rejected** (**VERIFIED**).
