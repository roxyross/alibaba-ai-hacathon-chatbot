// VoiceSession — push-to-talk + hands-free voice interaction
// Records audio, transcribes via speech_to_text skill, speaks response via text_to_speech skill.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import './VoiceSession.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

type VoiceMode = 'ptt'; // push-to-talk; 'handsfree' can be added later

interface TranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
  audioUrl?: string;
}

interface SpeechToTextResponse {
  text: string;
  language: string | null;
  confidence: number | null;
  duration_seconds: number | null;
}

interface TextToSpeechResponse {
  audio_data: string;
  format: string;
  duration_seconds: number | null;
  model: string;
}

async function fetchJSON<T>(
  url: string,
  accessToken: string | null | undefined,
  options?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function audioToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64 = (reader.result as string).split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// Browser speech recognition support
interface IWindowWithSpeech extends Window {
  SpeechRecognition?: any;
  webkitSpeechRecognition?: any;
}
const SpeechRecognitionClass =
  typeof window !== 'undefined'
    ? (window as unknown as IWindowWithSpeech).SpeechRecognition ||
      (window as unknown as IWindowWithSpeech).webkitSpeechRecognition
    : null;

export const VoiceSession: React.FC<{ accessToken?: string | null; onBack?: () => void }> = ({
  accessToken,
  onBack,
}) => {
  const [mode, setMode] = useState<VoiceMode>('ptt');
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [micPermission, setMicPermission] = useState<boolean | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const speakingAudioRef = useRef<HTMLAudioElement | null>(null);
  const speechRecognitionRef = useRef<any>(null);
  const recognizedSpeechRef = useRef<string>('');

  // Request mic permission on mount
  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then(() => setMicPermission(true))
      .catch(() => setMicPermission(false));
    return () => {
      // Cleanup any ongoing playback or recognition
      speakingAudioRef.current?.pause();
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      try {
        speechRecognitionRef.current?.stop();
      } catch {
        // ignore
      }
    };
  }, []);

  // ─── Recording ──────────────────────────────────────────────────────

  const startRecording = useCallback(() => {
    if (!micPermission) return;
    audioChunksRef.current = [];
    recognizedSpeechRef.current = '';

    // Also start browser speech recognition in parallel if available
    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = navigator.language || 'en-US';
        recognition.onresult = (e: any) => {
          let text = '';
          for (let i = e.resultIndex; i < e.results.length; i++) {
            text += e.results[i][0].transcript;
          }
          if (text) {
            recognizedSpeechRef.current = text.trim();
          }
        };
        recognition.onerror = () => {
          // ignore browser speech errors and rely on audio recording
        };
        recognition.start();
        speechRecognitionRef.current = recognition;
      } catch {
        // ignore
      }
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      const recorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
      });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await transcribeAndRespond(blob);
      };

      recorder.start();
      setIsRecording(true);
      setError(null);
    }).catch((err) => {
      setError(`Microphone access denied: ${err.message}`);
    });
  }, [micPermission]); // eslint-disable-line react-hooks/exhaustive-deps

  const stopRecording = useCallback(() => {
    if (speechRecognitionRef.current) {
      try {
        speechRecognitionRef.current.stop();
      } catch {
        // ignore
      }
    }
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setIsProcessing(true);
    }
  }, [isRecording]);

  // ─── Speech-to-text → Runtime → Text-to-speech ──────────────────────

  const transcribeAndRespond = async (audioBlob: Blob) => {
    try {
      const base64Audio = await audioToBase64(audioBlob);

      // 1. Transcribe (via backend Groq Whisper)
      let userText = '';
      try {
        const sttResp = await fetchJSON<SpeechToTextResponse>(
          `${API_BASE}/skills/speech_to_text`,
          accessToken,
          {
            method: 'POST',
            body: JSON.stringify({
              audio_data: base64Audio,
              language: null,
              model: 'whisper',
            }),
          },
        );
        userText = (sttResp.text || '').trim();
      } catch {
        // Backend STT fallback
      }

      // If backend STT returned empty, fall back to browser recognition
      if (!userText && recognizedSpeechRef.current) {
        userText = recognizedSpeechRef.current.trim();
      }

      if (!userText) {
        setTranscripts((prev) => [
          ...prev,
          { role: 'user', text: '(No voice detected — please ensure microphone is unmuted and speak clearly)' },
        ]);
        setIsProcessing(false);
        return;
      }

      setTranscripts((prev) => [...prev, { role: 'user', text: userText }]);

      // 2. Call the Runtime Coordinator to get a voice-friendly response
      // Use streaming=false for voice to get full text response first
      const chatResp = await fetchJSON<{
        response: string;
        agent_slug: string;
      }>(`${API_BASE}/runtime/chat`, accessToken, {
        method: 'POST',
        body: JSON.stringify({
          message: userText,
          stream: false,
        }),
      });

      const assistantText = chatResp.response;
      setTranscripts((prev) => [
        ...prev,
        { role: 'assistant', text: assistantText },
      ]);

      // 3. Synthesize speech
      await speakText(assistantText);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  };

  const speakText = async (text: string) => {
    const playWithBrowserSpeech = (cleanText: string) => {
      if ('speechSynthesis' in window) {
        try {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(cleanText);
          utterance.rate = 1.0;
          utterance.onstart = () => setIsSpeaking(true);
          utterance.onend = () => setIsSpeaking(false);
          utterance.onerror = () => setIsSpeaking(false);
          window.speechSynthesis.speak(utterance);
          return true;
        } catch {
          // ignore
        }
      }
      return false;
    };

    try {
      setIsSpeaking(true);
      const ttsResp = await fetchJSON<TextToSpeechResponse>(
        `${API_BASE}/skills/text_to_speech`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({
            text,
            speed: 1.0,
            model: 'openai',
          }),
        },
      );

      // Decode base64 audio and play it
      const audioBytes = Uint8Array.from(
        atob(ttsResp.audio_data),
        (c) => c.charCodeAt(0),
      );
      const audioBlob = new Blob([audioBytes], { type: `audio/${ttsResp.format}` });
      const audioUrl = URL.createObjectURL(audioBlob);

      speakingAudioRef.current?.pause();
      const audio = new Audio(audioUrl);
      speakingAudioRef.current = audio;

      audio.onended = () => {
        setIsSpeaking(false);
        URL.revokeObjectURL(audioUrl);
      };
      audio.onerror = () => {
        setIsSpeaking(false);
        URL.revokeObjectURL(audioUrl);
        const clean = text.replace(/[*#`_\[\]()]/g, '').trim();
        playWithBrowserSpeech(clean);
      };

      await audio.play();
    } catch (err) {
      setIsSpeaking(false);
      const clean = text.replace(/[*#`_\[\]()]/g, '').trim();
      const spoke = playWithBrowserSpeech(clean);
      if (!spoke) {
        setError(`TTS failed: ${(err as Error).message}`);
      }
    }
  };

  const handleMicMouseDown = () => {
    if (!isRecording && !isProcessing && !isSpeaking) {
      startRecording();
    }
  };

  const handleMicMouseUp = () => {
    if (isRecording) {
      stopRecording();
    }
  };

  // Keyboard support: spacebar to push-to-talk
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (
      e.code === 'Space' &&
      !e.repeat &&
      !isRecording &&
      !isProcessing &&
      !isSpeaking
    ) {
      e.preventDefault();
      startRecording();
    }
  };
  const handleKeyUp = (e: React.KeyboardEvent) => {
    if (e.code === 'Space' && isRecording) {
      e.preventDefault();
      stopRecording();
    }
  };

  const clearTranscripts = () => setTranscripts([]);

  // ─── Render ─────────────────────────────────────────────────────────

  return (
    <div
      className="vs"
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      tabIndex={0}
      aria-label="Voice session"
    >
      {/* Header */}
      <div className="vs__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {onBack && (
            <button type="button" className="view-back-btn" onClick={onBack} title="Back to Chat">
              ← Back to Chat
            </button>
          )}
          <h2 className="vs__title">🎙️ <span>Voice</span></h2>
        </div>
        {transcripts.length > 0 && (
          <button
            className="vs__clear"
            onClick={clearTranscripts}
            title="Clear transcripts"
          >
            Clear
          </button>
        )}
      </div>

      {/* Mic permission warning */}
      {micPermission === false && (
        <div className="vs__warning">
          🎤 Microphone access is required for voice interaction. Please allow
          microphone access in your browser settings and reload the page.
        </div>
      )}

      {/* Transcript list */}
      <div className="vs__transcripts" aria-label="Transcripts" aria-live="polite">
        {transcripts.length === 0 && !isProcessing && (
          <div className="vs__empty">
            <p>👆 Hold the microphone button and speak</p>
            <p className="vs__empty-hint">
              or press and hold <kbd>Space</kbd>
            </p>
          </div>
        )}

        {isProcessing && (
          <div className="vs__processing">
            <span className="vs__processing-dot" />
            <span>Transcribing…</span>
          </div>
        )}

        {transcripts.map((entry, i) => (
          <div
            key={i}
            className={`vs__entry vs__entry--${entry.role}`}
          >
            <span className="vs__entry-role">
              {entry.role === 'user' ? '🗣️ You' : '🤖 ROXY'}
            </span>
            <p className="vs__entry-text">{entry.text}</p>
          </div>
        ))}
      </div>

      {/* Error display */}
      {error && (
        <div className="vs__error" role="alert">
          {error}
          <button
            className="vs__error-dismiss"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* Bottom controls */}
      <div className="vs__controls">
        {/* Mode selector */}
        <div className="vs__mode-group" role="group" aria-label="Voice mode">
          <button
            className={`vs__mode-btn${mode === 'ptt' ? ' vs__mode-btn--active' : ''}`}
            onClick={() => setMode('ptt')}
            type="button"
          >
            🎯 Push-to-talk
          </button>
        </div>

        {/* Mic button */}
        <div className="vs__mic-wrap">
          <button
            className={`vs__mic${isRecording ? ' vs__mic--recording' : ''}${isProcessing || isSpeaking ? ' vs__mic--busy' : ''}${!micPermission ? ' vs__mic--disabled' : ''}`}
            onMouseDown={handleMicMouseDown}
            onMouseUp={handleMicMouseUp}
            onMouseLeave={isRecording ? handleMicMouseUp : undefined}
            onTouchStart={handleMicMouseDown}
            onTouchEnd={handleMicMouseUp}
            disabled={!micPermission || isProcessing || isSpeaking}
            aria-label={
              isRecording
                ? 'Release to send'
                : 'Hold to record'
            }
            type="button"
          >
            {isRecording ? (
              <span className="vs__mic-icon">⏹</span>
            ) : isProcessing ? (
              <span className="vs__mic-spinner" />
            ) : isSpeaking ? (
              <span className="vs__mic-icon">🔊</span>
            ) : (
              <span className="vs__mic-icon">🎤</span>
            )}
          </button>
          {isRecording && (
            <span className="vs__recording-label" aria-live="polite">
              Recording…
            </span>
          )}
          {isSpeaking && (
            <span className="vs__recording-label" aria-live="polite">
              Speaking…
            </span>
          )}
        </div>

        {/* Hint */}
        <div className="vs__hint">
          {micPermission
            ? 'Hold to talk · Release to send'
            : 'Mic access required'}
        </div>
      </div>
    </div>
  );
};
