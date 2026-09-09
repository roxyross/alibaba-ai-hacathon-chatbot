import React, { useState, useRef, useCallback, useEffect } from 'react';
import './VoiceInputControl.css';

export interface VoiceLanguageOption {
  code: string;
  name: string;
  flag: string;
  speechLang: string;
}

export const VOICE_LANGS: VoiceLanguageOption[] = [
  { code: 'auto', name: 'Auto', flag: '🌐', speechLang: '' },
  { code: 'ur', name: 'Urdu', flag: '🇵🇰', speechLang: 'ur-PK' },
  { code: 'hi', name: 'Hindi', flag: '🇮🇳', speechLang: 'hi-IN' },
  { code: 'en', name: 'English', flag: '🇬🇧', speechLang: 'en-US' },
  { code: 'ar', name: 'Arabic', flag: '🇸🇦', speechLang: 'ar-SA' },
  { code: 'es', name: 'Spanish', flag: '🇪🇸', speechLang: 'es-ES' },
];

export interface VoiceInputControlProps {
  onTranscript: (text: string) => void;
  readAloudText?: string;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  showLangPicker?: boolean;
  showReadAloud?: boolean;
  className?: string;
  disabled?: boolean;
  voiceModulation?: 'whispering' | 'shouting' | 'excited' | 'dramatic' | 'calm' | 'normal';
}

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export const VoiceInputControl: React.FC<VoiceInputControlProps> = ({
  onTranscript,
  readAloudText,
  label = 'Voice dictation',
  size = 'md',
  showLangPicker = false,
  showReadAloud = true,
  className = '',
  disabled = false,
  voiceModulation = 'normal',
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [lang, setLang] = useState<string>(() => localStorage.getItem('roxy_voice_lang') || 'auto');

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const transcriptBufferRef = useRef<string>('');
  const audioElemRef = useRef<HTMLAudioElement | null>(null);

  // Stop recording cleanup
  const stopAll = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
      mediaRecorderRef.current = null;
    }
    setIsRecording(false);
  }, []);

  useEffect(() => {
    return () => {
      stopAll();
      if (audioElemRef.current) {
        audioElemRef.current.pause();
        audioElemRef.current = null;
      }
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, [stopAll]);

  const sendAudioToBackendSTT = async (blob: Blob) => {
    if (blob.size < 200) return;
    setIsTranscribing(true);
    try {
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve) => {
        reader.onloadend = () => {
          const res = reader.result as string;
          resolve(res.includes(',') ? res.split(',')[1] : res);
        };
        reader.readAsDataURL(blob);
      });
      const audio_data = await base64Promise;
      const resp = await fetch(`${API_BASE}/skills/speech_to_text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_data,
          language: lang !== 'auto' ? lang : null,
          model: 'gemini',
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        const text = (data.text || '').trim();
        if (text) {
          onTranscript(text);
        }
      }
    } catch {
      // Backend STT fallback failed silently
    } finally {
      setIsTranscribing(false);
    }
  };

  const startListening = async () => {
    if (disabled || isRecording || isTranscribing) return;
    transcriptBufferRef.current = '';
    audioChunksRef.current = [];

    // 1. Try Web Speech API if supported
    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = false;
        recognition.interimResults = true;
        const activeOpt = VOICE_LANGS.find((l) => l.code === lang);
        recognition.lang = activeOpt?.speechLang || navigator.language || 'en-US';

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        recognition.onresult = (event: any) => {
          let full = '';
          for (let i = 0; i < event.results.length; i++) {
            full += event.results[i][0].transcript;
          }
          if (full) {
            transcriptBufferRef.current = full;
          }
        };

        recognition.onend = () => {
          setIsRecording(false);
          if (transcriptBufferRef.current.trim()) {
            onTranscript(transcriptBufferRef.current.trim());
          }
        };

        recognition.onerror = () => {
          setIsRecording(false);
        };

        recognitionRef.current = recognition;
        recognition.start();
        setIsRecording(true);
      } catch {
        // Fallback to MediaRecorder
      }
    }

    // 2. Also record MediaRecorder as backup for multimodal STT
    if (navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const recorder = new MediaRecorder(stream);
        mediaRecorderRef.current = recorder;
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data);
        };
        recorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          const finalBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
          if (!transcriptBufferRef.current.trim()) {
            sendAudioToBackendSTT(finalBlob);
          }
        };
        recorder.start();
        setIsRecording(true);
      } catch {
        // mic permission denied
      }
    }
  };

  const toggleListen = () => {
    if (isRecording) {
      stopAll();
    } else {
      startListening();
    }
  };

  // Read Aloud / TTS function
  const handleReadAloud = async () => {
    const textToSpeak = (readAloudText || '').trim();
    if (!textToSpeak || isPlayingAudio) {
      if (isPlayingAudio) {
        if (audioElemRef.current) {
          audioElemRef.current.pause();
          audioElemRef.current = null;
        }
        if ('speechSynthesis' in window) {
          window.speechSynthesis.cancel();
        }
        setIsPlayingAudio(false);
      }
      return;
    }

    setIsPlayingAudio(true);

    const fallbackBrowserSpeech = () => {
      if (!('speechSynthesis' in window)) {
        setIsPlayingAudio(false);
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(textToSpeak.replace(/[*#`_\[\]()]/g, ''));
      if (/[\u0600-\u06FF]/.test(textToSpeak)) {
        utterance.lang = 'ur-PK';
      } else if (/[\u0900-\u097F]/.test(textToSpeak)) {
        utterance.lang = 'hi-IN';
      } else if (lang !== 'auto') {
        const active = VOICE_LANGS.find((l) => l.code === lang);
        if (active?.speechLang) utterance.lang = active.speechLang;
      }
      utterance.onend = () => setIsPlayingAudio(false);
      utterance.onerror = () => setIsPlayingAudio(false);
      window.speechSynthesis.speak(utterance);
    };

    try {
      const resp = await fetch(`${API_BASE}/skills/text_to_speech`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: textToSpeak,
          speed: 1.0,
          model: 'gemini-3.8-flash',
          voice: 'Kore',
          voice_modulation: voiceModulation !== 'normal' ? voiceModulation : undefined,
        }),
      });

      if (!resp.ok) throw new Error('TTS failed');
      const data = await resp.json();
      if (!data.audio_data) throw new Error('No audio returned');

      const byteChars = atob(data.audio_data);
      const byteNumbers = new Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) {
        byteNumbers[i] = byteChars.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: `audio/${data.format || 'mp3'}` });
      const url = URL.createObjectURL(blob);

      const audio = new Audio(url);
      audioElemRef.current = audio;
      audio.onended = () => {
        setIsPlayingAudio(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        fallbackBrowserSpeech();
      };
      await audio.play();
    } catch {
      fallbackBrowserSpeech();
    }
  };

  return (
    <div className={`voice-input-control voice-input-control--${size} ${className}`}>
      {/* Optional language selector */}
      {showLangPicker && (
        <select
          className="voice-input-control__lang"
          value={lang}
          onChange={(e) => {
            const val = e.target.value;
            setLang(val);
            localStorage.setItem('roxy_voice_lang', val);
          }}
          title="Voice Language"
          aria-label="Voice Language"
          disabled={disabled || isRecording}
        >
          {VOICE_LANGS.map((l) => (
            <option key={l.code} value={l.code}>
              {l.flag} {l.name}
            </option>
          ))}
        </select>
      )}

      {/* Dictation / Microphone button */}
      <button
        type="button"
        className={`voice-input-control__btn voice-input-control__btn--mic ${
          isRecording ? 'voice-input-control__btn--recording' : ''
        } ${isTranscribing ? 'voice-input-control__btn--transcribing' : ''}`}
        onClick={toggleListen}
        disabled={disabled || isTranscribing}
        title={isRecording ? 'Listening… Click to stop' : isTranscribing ? 'Transcribing with Gemini STT…' : `${label} (Speak now)`}
        aria-label={label}
      >
        {isTranscribing ? (
          <span className="voice-input-control__spinner" />
        ) : isRecording ? (
          <span className="voice-input-control__pulse">⏹️</span>
        ) : (
          <span>🎙️</span>
        )}
      </button>

      {/* Optional Read Aloud button */}
      {showReadAloud && (
        <button
          type="button"
          className={`voice-input-control__btn voice-input-control__btn--tts ${
            isPlayingAudio ? 'voice-input-control__btn--speaking' : ''
          }`}
          onClick={handleReadAloud}
          disabled={disabled || !readAloudText || isRecording}
          title={isPlayingAudio ? 'Stop speaking' : 'Read aloud with Gemini voice (Gemini 3.8 Flash)'}
          aria-label="Read aloud"
        >
          {isPlayingAudio ? '🔊' : '🔈'}
        </button>
      )}
    </div>
  );
};
