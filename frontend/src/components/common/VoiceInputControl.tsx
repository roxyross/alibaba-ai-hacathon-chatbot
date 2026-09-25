import React, { useState, useCallback, useEffect } from 'react';
import { voiceManager } from '../../utils/VoiceManager';
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
  onInterim?: (interim: string) => void;
  readAloudText?: string;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  showLangPicker?: boolean;
  showReadAloud?: boolean;
  className?: string;
  disabled?: boolean;
  toolId?: string;
  voiceModulation?: 'whispering' | 'shouting' | 'excited' | 'dramatic' | 'calm' | 'normal';
}

/**
 * Ensures an audio byte array has a valid container header (WAV or MP3).
 * If raw PCM is detected, wraps it into a standard 44-byte RIFF/WAV container.
 */
export function ensureWavHeader(bytes: Uint8Array, sampleRate: number = 24000): { data: Uint8Array; mime: string } {
  if (bytes.length >= 12 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46) {
    return { data: bytes, mime: 'audio/wav' };
  }
  if (bytes.length >= 3 && bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x43) {
    return { data: bytes, mime: 'audio/mp3' };
  }
  if (bytes.length >= 2 && bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0) {
    return { data: bytes, mime: 'audio/mp3' };
  }

  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = bytes.length;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  view.setUint8(0, 0x52); view.setUint8(1, 0x49); view.setUint8(2, 0x46); view.setUint8(3, 0x46);
  view.setUint32(4, 36 + dataSize, true);
  view.setUint8(8, 0x57); view.setUint8(9, 0x41); view.setUint8(10, 0x56); view.setUint8(11, 0x45);
  view.setUint8(12, 0x66); view.setUint8(13, 0x6d); view.setUint8(14, 0x74); view.setUint8(15, 0x20);
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  view.setUint8(36, 0x64); view.setUint8(37, 0x61); view.setUint8(38, 0x74); view.setUint8(39, 0x61);
  view.setUint32(40, dataSize, true);

  new Uint8Array(buffer, 44).set(bytes);
  return { data: new Uint8Array(buffer), mime: 'audio/wav' };
}

export const VoiceInputControl: React.FC<VoiceInputControlProps> = ({
  onTranscript,
  onInterim,
  readAloudText,
  label = 'Voice dictation',
  size = 'md',
  showLangPicker = false,
  showReadAloud = true,
  className = '',
  disabled = false,
  toolId = 'common_voice',
}) => {
  const [sttState, setSttState] = useState<'idle' | 'listening' | 'transcribing'>('idle');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [lang, setLang] = useState<string>(() => localStorage.getItem('roxy_voice_lang') || 'auto');
  const [interimDisplay, setInterimDisplay] = useState('');

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      voiceManager.cleanupVoiceSession(toolId);
    };
  }, [toolId]);

  const handleStartListening = useCallback(async () => {
    if (disabled || sttState !== 'idle') return;
    setInterimDisplay('');

    const activeOpt = VOICE_LANGS.find((l) => l.code === lang);
    const speechLang = activeOpt?.speechLang || (typeof navigator !== 'undefined' ? navigator.language : 'en-US');

    await voiceManager.stt.startListening({
      toolId,
      lang: speechLang,
      onStateChange: (newState) => {
        setSttState(newState);
      },
      onInterim: (interim) => {
        setInterimDisplay(interim);
        onInterim?.(interim);
      },
      onFinal: (finalText) => {
        setInterimDisplay('');
        if (finalText.trim()) {
          onTranscript(finalText.trim());
        }
      },
      onError: (err) => {
        setInterimDisplay('');
        console.warn('VoiceInputControl STT error:', err);
      },
    });
  }, [disabled, sttState, lang, toolId, onInterim, onTranscript]);

  const handleStopListening = useCallback(() => {
    if (sttState === 'listening') {
      voiceManager.stt.stopListening(true);
    }
  }, [sttState]);

  const toggleListening = useCallback(() => {
    if (sttState === 'listening') {
      handleStopListening();
    } else if (sttState === 'idle') {
      void handleStartListening();
    }
  }, [sttState, handleStopListening, handleStartListening]);

  const handleToggleReadAloud = useCallback(() => {
    if (!readAloudText) return;

    if (isSpeaking) {
      voiceManager.tts.stopSpeaking();
      setIsSpeaking(false);
    } else {
      const activeOpt = VOICE_LANGS.find((l) => l.code === lang);
      const voiceLang = activeOpt?.code !== 'auto' ? activeOpt?.code : 'en';

      void voiceManager.tts.speak(readAloudText, {
        toolId,
        voiceLang,
        onStart: () => setIsSpeaking(true),
        onEnd: () => setIsSpeaking(false),
        onError: () => setIsSpeaking(false),
      });
    }
  }, [readAloudText, isSpeaking, lang, toolId]);

  const handleLangChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value;
    setLang(next);
    localStorage.setItem('roxy_voice_lang', next);
  };

  const isRecording = sttState === 'listening';
  const isTranscribing = sttState === 'transcribing';

  return (
    <div
      className={`voice-input-control voice-input-control--${size} ${className}`}
      role="group"
      aria-label={label}
    >
      {/* Explicit STT Microphone Button */}
      <button
        type="button"
        className={`voice-input-control__btn ${isRecording ? 'voice-input-control__btn--recording' : ''}`}
        onClick={toggleListening}
        disabled={disabled || isTranscribing}
        title={isRecording ? '🛑 Stop Listening' : '🎙 Start Listening'}
        aria-label={isRecording ? 'Stop Listening' : 'Start Listening'}
        aria-pressed={isRecording}
      >
        {isTranscribing ? (
          <span className="voice-input-control__spinner" aria-hidden="true" />
        ) : isRecording ? (
          <span aria-hidden="true">🛑</span>
        ) : (
          <span aria-hidden="true">🎙️</span>
        )}
      </button>

      {/* Live Interim Transcript Pill (when speaking) */}
      {isRecording && interimDisplay && (
        <span
          className="voice-input-control__live-interim"
          style={{
            fontSize: '0.75rem',
            color: '#38bdf8',
            maxWidth: '180px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            fontStyle: 'italic',
            marginLeft: '4px',
          }}
          title={interimDisplay}
        >
          "{interimDisplay}"
        </span>
      )}

      {/* Language Picker (optional) */}
      {showLangPicker && (
        <select
          className="voice-input-control__lang"
          value={lang}
          onChange={handleLangChange}
          title="Voice input language"
          aria-label="Voice input language"
          disabled={disabled || isRecording}
        >
          {VOICE_LANGS.map((opt) => (
            <option key={opt.code} value={opt.code}>
              {opt.flag} {opt.name}
            </option>
          ))}
        </select>
      )}

      {/* Explicit Independent TTS Button */}
      {showReadAloud && readAloudText && (
        <button
          type="button"
          className={`voice-input-control__btn ${isSpeaking ? 'voice-input-control__btn--speaking' : ''}`}
          onClick={handleToggleReadAloud}
          disabled={disabled || isRecording}
          title={isSpeaking ? '⏹ Stop Speaking' : '🔊 Listen / Read Aloud'}
          aria-label={isSpeaking ? 'Stop Speaking' : 'Read Aloud'}
        >
          {isSpeaking ? (
            <span aria-hidden="true">⏹</span>
          ) : (
            <span aria-hidden="true">🔊</span>
          )}
        </button>
      )}
    </div>
  );
};

/**
 * Global helper: Speaks text ONLY if the user has explicitly enabled Auto-Play Voice Responses
 * in Settings. Never automatically starts speech if Auto-Play is OFF.
 */
export async function speakVoiceText(text: string, lang = 'en-US'): Promise<void> {
  if (!voiceManager.isAutoPlayAllowed()) {
    // Auto-play is disabled by policy. Do NOT speak automatically.
    return;
  }
  const clean = text.replace(/[*#`_\[\]()]/g, '').trim();
  if (!clean) return;
  await voiceManager.tts.speak(clean, { voiceLang: lang });
}

/**
 * Global helper: Stops all active voice speech immediately.
 */
export function stopVoiceText(): void {
  voiceManager.tts.stopSpeaking();
}
