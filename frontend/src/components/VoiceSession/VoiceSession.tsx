// VoiceSession — push-to-talk + hands-free voice interaction
// Records audio, transcribes via speech_to_text skill, speaks response via text_to_speech skill.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { VOICE_LANGUAGES } from '../ChatInput/ChatInput';
import { ensureWavHeader } from '../common/VoiceInputControl';
import './VoiceSession.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

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

interface VoiceRecordingItem {
  id: string;
  user_id: string;
  title: string;
  transcript: string;
  summary?: string | null;
  language?: string | null;
  audio_url?: string | null;
  duration_seconds?: number | null;
  voice_model?: string | null;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
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
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [micPermission, setMicPermission] = useState<boolean | null>(null);
  const [voiceLang, setVoiceLang] = useState<string>(() => {
    return localStorage.getItem('roxy_voice_lang') || 'auto';
  });
  const [liveCaption, setLiveCaption] = useState<string>('');
  const [audioLevels, setAudioLevels] = useState<number[]>([15, 25, 35, 20, 12]);
  const [voiceModulation, setVoiceModulation] = useState<string>('normal');
  const [geminiVoice, setGeminiVoice] = useState<string>('Kore');
  const [voiceModel, setVoiceModel] = useState<string>('gemini-3.8-flash');
  const [activeTab, setActiveTab] = useState<'live' | 'library'>('live');
  const [savedRecordings, setSavedRecordings] = useState<VoiceRecordingItem[]>([]);
  const [loadingRecordings, setLoadingRecordings] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [isSavingNote, setIsSavingNote] = useState<boolean>(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchSavedRecordings = useCallback(async (search?: string) => {
    if (!accessToken) return;
    setLoadingRecordings(true);
    try {
      const q = search ? `?search=${encodeURIComponent(search)}` : '';
      const data = await fetchJSON<{ recordings: VoiceRecordingItem[]; total: number }>(
        `${API_BASE}/voice/recordings${q}`,
        accessToken,
      );
      setSavedRecordings(data.recordings || []);
    } catch {
      // ignore
    } finally {
      setLoadingRecordings(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (activeTab === 'library') {
      void fetchSavedRecordings(searchQuery);
    }
  }, [activeTab, searchQuery, fetchSavedRecordings]);

  useEffect(() => {
    if (accessToken) {
      void fetchSavedRecordings();
    }
  }, [accessToken, fetchSavedRecordings]);


  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const speakingAudioRef = useRef<HTMLAudioElement | null>(null);
  const speechRecognitionRef = useRef<any>(null);
  const recognizedSpeechRef = useRef<string>('');
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const activeStreamRef = useRef<MediaStream | null>(null);
  const silenceTimerRef = useRef<any>(null);
  const hasSpokenRef = useRef<boolean>(false);
  const isTranscribingRef = useRef<boolean>(false);
  const vadActiveRef = useRef<boolean>(false);
  const vadSilenceStartRef = useRef<number>(0);

  // Request mic permission on mount
  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        setMicPermission(true);
        // Release immediate test stream
        stream.getTracks().forEach((t) => t.stop());
      })
      .catch(() => setMicPermission(false));

    return () => {
      // Cleanup any ongoing playback, stream, animation or recognition
      speakingAudioRef.current?.pause();
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      try {
        speechRecognitionRef.current?.stop();
      } catch {
        // ignore
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(() => {});
      }
      if (activeStreamRef.current) {
        activeStreamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  // Audio level visualizer loop + Acoustic Voice Activity Detection (VAD)
  const startAudioVisualizer = (stream: MediaStream) => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      audioContextRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 32;
      analyserRef.current = analyser;
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      vadActiveRef.current = false;
      vadSilenceStartRef.current = 0;

      const updateVisualizer = () => {
        analyser.getByteFrequencyData(dataArray);

        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;

        // Acoustic VAD: detects voice energy vs silence directly from mic input
        if (avg > 14) {
          vadActiveRef.current = true;
          hasSpokenRef.current = true;
          vadSilenceStartRef.current = 0;
        } else if (vadActiveRef.current) {
          const now = Date.now();
          if (!vadSilenceStartRef.current) {
            vadSilenceStartRef.current = now;
          } else if (now - vadSilenceStartRef.current > 700) {
            // User finished speaking! Stop recording immediately.
            vadActiveRef.current = false;
            vadSilenceStartRef.current = 0;
            stopRecording();
            return;
          }
        }

        // Pick 5 frequency bands for UI wave visualizer
        const levels = [
          Math.max(12, (dataArray[1] || 0) * 0.4),
          Math.max(16, (dataArray[3] || 0) * 0.48),
          Math.max(20, (dataArray[5] || 0) * 0.55),
          Math.max(14, (dataArray[7] || 0) * 0.44),
          Math.max(10, (dataArray[9] || 0) * 0.35),
        ];
        setAudioLevels(levels);
        animFrameRef.current = requestAnimationFrame(updateVisualizer);
      };
      updateVisualizer();
    } catch {
      // ignore
    }
  };

  const stopAudioVisualizer = () => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setAudioLevels([15, 25, 35, 20, 12]);
  };

  const stopSpeaking = useCallback(() => {
    speakingAudioRef.current?.pause();
    if (speakingAudioRef.current) {
      speakingAudioRef.current.currentTime = 0;
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }, []);

  // ─── Spoken text dispatch (Instant 0ms path) ─────────────────────────
  const processSpokenText = useCallback(
    async (rawText: string) => {
      if (isTranscribingRef.current) return;
      const text = rawText.trim();
      if (!text) return;

      // Filter out silence hallucinations
      const silencePhrases = [
        'thank you',
        'thank you.',
        'thank you very much',
        'thank you very much.',
        'thanks for watching',
        'thanks for watching.',
        'thank you for watching',
        'thank you for watching.',
        'subtitles by',
        'you',
        'you.',
        'bye',
        'bye.',
      ];
      const norm = text.toLowerCase().replace(/[.,!?]/g, '').trim();
      if (silencePhrases.includes(norm) || text.startsWith('[STT not configured')) {
        setIsProcessing(false);
        setLiveCaption('');
        return;
      }

      isTranscribingRef.current = true;
      setIsProcessing(true);
      setLiveCaption('');
      setError(null);
      setTranscripts((prev) => [...prev, { role: 'user', text }]);

      try {
        const chatResp = await fetchJSON<{
          response: string;
          agent_slug: string;
        }>(`${API_BASE}/runtime/chat`, accessToken, {
          method: 'POST',
          body: JSON.stringify({
            message: text,
            stream: false,
          }),
        });

        const assistantText = chatResp.response;
        setTranscripts((prev) => [
          ...prev,
          { role: 'assistant', text: assistantText },
        ]);

        await speakText(assistantText);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setIsProcessing(false);
        isTranscribingRef.current = false;
      }
    },
    [accessToken], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ─── Recording ──────────────────────────────────────────────────────

  const startRecording = useCallback(() => {
    if (isSpeaking) {
      stopSpeaking();
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    hasSpokenRef.current = false;
    isTranscribingRef.current = false;
    vadActiveRef.current = false;
    vadSilenceStartRef.current = 0;
    audioChunksRef.current = [];
    recognizedSpeechRef.current = '';
    setLiveCaption('');
    setError(null);

    // 1. Browser Speech Recognition (Web Speech API)
    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = true;
        recognition.interimResults = true;
        const activeLangObj = VOICE_LANGUAGES.find((l) => l.code === voiceLang);
        recognition.lang = (activeLangObj && activeLangObj.speechLang) ? activeLangObj.speechLang : (navigator.language || 'en-US');

        recognition.onresult = (e: any) => {
          let finalTranscript = '';
          let interimTranscript = '';
          for (let i = 0; i < e.results.length; i++) {
            const res = e.results[i];
            if (res && res[0]) {
              if (res.isFinal) {
                finalTranscript += res[0].transcript + ' ';
              } else {
                interimTranscript += res[0].transcript;
              }
            }
          }
          const combined = (finalTranscript + interimTranscript).trim();
          if (combined) {
            recognizedSpeechRef.current = combined;
            setLiveCaption(combined);
            hasSpokenRef.current = true;

            // Auto-detect end of speech: trigger stop & instant AI response after 700ms of silence
            if (silenceTimerRef.current) {
              clearTimeout(silenceTimerRef.current);
            }
            silenceTimerRef.current = setTimeout(() => {
              if (recognizedSpeechRef.current.trim().length > 0) {
                stopRecording();
              }
            }, 700);
          }
        };

        recognition.onend = () => {
          if (hasSpokenRef.current && recognizedSpeechRef.current.trim().length > 0) {
            stopRecording();
          }
        };

        recognition.onerror = () => {
          // ignore web speech errors; fallback to audio recording
        };

        recognition.start();
        speechRecognitionRef.current = recognition;
      } catch {
        // ignore
      }
    }

    // 2. MediaRecorder for backend STT fallback
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        activeStreamRef.current = stream;
        setMicPermission(true);

        startAudioVisualizer(stream);

        let mimeType = 'audio/webm;codecs=opus';
        if (typeof MediaRecorder !== 'undefined') {
          if (!MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
            if (MediaRecorder.isTypeSupported('audio/webm')) {
              mimeType = 'audio/webm';
            } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
              mimeType = 'audio/mp4';
            } else {
              mimeType = '';
            }
          }
        }

        const options: MediaRecorderOptions = mimeType ? { mimeType } : {};
        const recorder = new MediaRecorder(stream, options);
        mediaRecorderRef.current = recorder;

        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            audioChunksRef.current.push(e.data);
          }
        };

        recorder.onstop = async () => {
          stopAudioVisualizer();
          stream.getTracks().forEach((t) => t.stop());
          // Only use backend STT fallback if text was not already processed
          if (!isTranscribingRef.current) {
            const finalBlob = new Blob(audioChunksRef.current, {
              type: mimeType || 'audio/webm',
            });
            await transcribeAndRespond(finalBlob);
          }
        };

        recorder.start(250);
        setIsRecording(true);
      })
      .catch((err) => {
        setError(`Microphone access error: ${err.message}`);
        setMicPermission(false);
      });
  }, [isSpeaking]); // eslint-disable-line react-hooks/exhaustive-deps

  const stopRecording = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (speechRecognitionRef.current) {
      try {
        speechRecognitionRef.current.stop();
      } catch {
        // ignore
      }
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
    setIsRecording(false);

    // Instant dispatch: if text was already transcribed by Web Speech, start AI call immediately!
    const directText = recognizedSpeechRef.current ? recognizedSpeechRef.current.trim() : '';
    if (directText && !isTranscribingRef.current) {
      processSpokenText(directText);
    } else if (!isTranscribingRef.current) {
      setIsProcessing(true);
    }
  }, [processSpokenText]);

  const toggleRecording = useCallback(() => {
    if (isSpeaking) {
      stopSpeaking();
      return;
    }
    if (isRecording) {
      stopRecording();
    } else if (!isProcessing) {
      startRecording();
    }
  }, [isSpeaking, isRecording, isProcessing, stopSpeaking, startRecording, stopRecording]);

  // ─── Speech-to-text → Runtime → Text-to-speech ──────────────────────

  const transcribeAndRespond = async (audioBlob: Blob) => {
    try {
      // 1. FAST PATH: If browser already transcribed speech, use it directly (0ms delay)
      let userText = recognizedSpeechRef.current ? recognizedSpeechRef.current.trim() : '';

      // 2. FALLBACK PATH: If Web Speech was empty, send audio to backend STT
      if (!userText && audioBlob.size > 200) {
        try {
          const base64Audio = await audioToBase64(audioBlob);
          const whisperLang = voiceLang && voiceLang !== 'auto' ? voiceLang : null;
          const sttResp = await fetchJSON<SpeechToTextResponse>(
            `${API_BASE}/skills/speech_to_text`,
            accessToken,
            {
              method: 'POST',
              body: JSON.stringify({
                audio_data: base64Audio,
                language: whisperLang,
                model: 'gemini',
              }),
            },
          );

          userText = (sttResp.text || '').trim();
        } catch {
          // Backend STT error
        }
      }

      // Filter out silence hallucinations or unconfigured mocks
      const silencePhrases = [
        'thank you',
        'thank you.',
        'thank you very much',
        'thank you very much.',
        'thanks for watching',
        'thanks for watching.',
        'thank you for watching',
        'thank you for watching.',
        'subtitles by',
        'you',
        'you.',
        'bye',
        'bye.',
      ];
      const normText = userText.toLowerCase().replace(/[.,!?]/g, '').trim();
      if (silencePhrases.includes(normText) || userText.startsWith('[STT not configured')) {
        userText = '';
      }

      // If backend STT returned empty or failed, use recognized speech from Web Speech API
      if (!userText && recognizedSpeechRef.current) {
        userText = recognizedSpeechRef.current.trim();
      }

      if (!userText) {
        setError('No voice detected. Please speak clearly and tap the mic again to retry.');
        setIsProcessing(false);
        setLiveCaption('');
        return;
      }

      setLiveCaption('');
      setTranscripts((prev) => [...prev, { role: 'user', text: userText }]);

      // 2. Call the AI Runtime Coordinator for voice response
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
          window.speechSynthesis.resume();
          const utterance = new SpeechSynthesisUtterance(cleanText);
          utterance.rate = 1.0;

          // Detect language to set proper voice
          if (/[\u0600-\u06FF]/.test(cleanText)) {
            utterance.lang = 'ur-PK';
          } else if (/[\u0900-\u097F]/.test(cleanText)) {
            utterance.lang = 'hi-IN';
          } else if (/[\u4e00-\u9fff]/.test(cleanText)) {
            utterance.lang = 'zh-CN';
          } else if (/[\u3040-\u30ff]/.test(cleanText)) {
            utterance.lang = 'ja-JP';
          } else if (/[\u0400-\u04FF]/.test(cleanText)) {
            utterance.lang = 'ru-RU';
          } else if (voiceLang && voiceLang !== 'auto') {
            const active = VOICE_LANGUAGES.find((l) => l.code === voiceLang);
            if (active?.speechLang) utterance.lang = active.speechLang;
          }

          const voices = window.speechSynthesis.getVoices();
          if (voices.length > 0) {
            const prefix = utterance.lang.split('-')[0].toLowerCase();
            const matchedVoice = voices.find((v) => v.lang.toLowerCase().startsWith(prefix));
            if (matchedVoice) {
              utterance.voice = matchedVoice;
            }
          }

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
            model: voiceModel || 'gemini',
            voice: geminiVoice,
            voice_modulation: voiceModulation !== 'normal' ? voiceModulation : undefined,
          }),
        },
      );

      if (!ttsResp.audio_data || ttsResp.audio_data.length < 50) {
        throw new Error('Empty audio returned by TTS');
      }

      // Decode base64 audio and ensure valid WAV header if raw PCM
      const byteChars = atob(ttsResp.audio_data);
      const rawBytes = new Uint8Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) {
        rawBytes[i] = byteChars.charCodeAt(i);
      }
      const { data: audioBytes, mime } = ensureWavHeader(rawBytes, 24000);
      const audioBlob = new Blob([audioBytes as unknown as BlobPart], { type: mime });
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

  // Keyboard support: spacebar to toggle recording or interrupt speaking
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.code === 'Space' && !e.repeat && (e.target as HTMLElement).tagName !== 'INPUT' && (e.target as HTMLElement).tagName !== 'TEXTAREA') {
      e.preventDefault();
      toggleRecording();
    }
  };

  const clearTranscripts = () => {
    setTranscripts([]);
    setError(null);
    setLiveCaption('');
  };

  const handleSaveAsVoiceNote = async () => {
    if (transcripts.length === 0 || !accessToken) return;
    setIsSavingNote(true);
    try {
      const fullTranscript = transcripts
        .map((t) => `${t.role === 'user' ? 'User' : 'Roxy'}: ${t.text}`)
        .join('\n\n');
      const firstUserTurn = transcripts.find((t) => t.role === 'user')?.text || 'Voice Session';
      const defaultTitle = firstUserTurn.length > 50 ? `${firstUserTurn.slice(0, 50)}…` : firstUserTurn;

      const created = await fetchJSON<{ recording: VoiceRecordingItem }>(
        `${API_BASE}/voice/recordings`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({
            title: defaultTitle,
            transcript: fullTranscript,
            language: voiceLang !== 'auto' ? voiceLang : 'en',
            voice_model: voiceModel,
          }),
        },
      );

      setSavedRecordings((prev) => [created.recording, ...prev]);
      setToastMessage('✅ Saved note to Voice Notes Library!');
      setTimeout(() => setToastMessage(null), 3000);
    } catch (err) {
      setError(`Failed to save note: ${(err as Error).message}`);
    } finally {
      setIsSavingNote(false);
    }
  };

  const handleDeleteRecording = async (recId: string) => {
    if (!accessToken) return;
    if (!window.confirm('Delete this voice recording note?')) return;
    try {
      await fetchJSON(`${API_BASE}/voice/recordings/${recId}`, accessToken, {
        method: 'DELETE',
      });
      setSavedRecordings((prev) => prev.filter((r) => r.id !== recId));
      setToastMessage('🗑️ Voice note deleted');
      setTimeout(() => setToastMessage(null), 2500);
    } catch (err) {
      setError(`Failed to delete recording: ${(err as Error).message}`);
    }
  };

  const handleCopyTranscript = (text: string) => {
    navigator.clipboard.writeText(text);
    setToastMessage('📋 Transcript copied to clipboard');
    setTimeout(() => setToastMessage(null), 2500);
  };

  // ─── Render ─────────────────────────────────────────────────────────

  return (
    <div
      className="vs"
      onKeyDown={handleKeyDown}
      tabIndex={0}
      aria-label="Voice session"
    >
      {/* Header */}
      <div className="vs__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {onBack && (
            <button type="button" className="view-back-btn" onClick={onBack} title="Back to Chat">
              ← Back to Chat
            </button>
          )}
          <h2 className="vs__title">🎙️ <span>Voice Session</span></h2>

          {/* Tab navigation */}
          <div className="vs__tabs" role="tablist" aria-label="Voice Session Views">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'live'}
              className={`vs__tab-btn ${activeTab === 'live' ? 'vs__tab-btn--active' : ''}`}
              onClick={() => setActiveTab('live')}
            >
              🎙️ Live Voice
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'library'}
              className={`vs__tab-btn ${activeTab === 'library' ? 'vs__tab-btn--active' : ''}`}
              onClick={() => setActiveTab('library')}
            >
              📁 Voice Notes {savedRecordings.length > 0 && `(${savedRecordings.length})`}
            </button>
          </div>
        </div>

        {activeTab === 'live' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {/* Voice Model Picker */}
            <select
              className="vs__lang-select"
              value={voiceModel}
              onChange={(e) => setVoiceModel(e.target.value)}
              title="Multimodal Voice Model"
              aria-label="Multimodal Voice Model"
            >
              <option value="gemini-3.8-flash">✨ Gemini 3.8 Flash (Multimodal Audio)</option>
              <option value="gemini-3.7-flash">⚡ Gemini 3.7 Flash</option>
              <option value="gemini-3.1-flash">⚡ Gemini 3.1 Flash</option>
              <option value="openai">OpenAI TTS</option>
            </select>

            {/* Steerable Voice Modulation / Tone */}
            <select
              className="vs__lang-select"
              value={voiceModulation}
              onChange={(e) => setVoiceModulation(e.target.value)}
              title="Voice Modulation & Tone"
              aria-label="Voice Modulation & Tone"
            >
              <option value="normal">🗣️ Normal Tone</option>
              <option value="whispering">🤫 Whispering</option>
              <option value="excited">🤩 Excited</option>
              <option value="dramatic">🎭 Dramatic</option>
              <option value="calm">🧘 Calm</option>
              <option value="shouting">📢 Shouting</option>
            </select>

            {/* Gemini Voice */}
            <select
              className="vs__lang-select"
              value={geminiVoice}
              onChange={(e) => setGeminiVoice(e.target.value)}
              title="AI Voice Persona"
              aria-label="AI Voice Persona"
            >
              <option value="Kore">Kore (Warm)</option>
              <option value="Puck">Puck (Energetic)</option>
              <option value="Fenrir">Fenrir (Deep)</option>
              <option value="Aoede">Aoede (Expressive)</option>
              <option value="Zephyr">Zephyr (Calm)</option>
            </select>

            {/* Spoken Language */}
            <select
              className="vs__lang-select"
              value={voiceLang}
              onChange={(e) => {
                const nextLang = e.target.value;
                setVoiceLang(nextLang);
                localStorage.setItem('roxy_voice_lang', nextLang);
                if (speechRecognitionRef.current) {
                  const active = VOICE_LANGUAGES.find((l) => l.code === nextLang);
                  speechRecognitionRef.current.lang = active?.speechLang || (navigator.language || 'en-US');
                }
              }}
              title="Speech recognition & voice language"
              aria-label="Speech recognition & voice language"
            >
              {VOICE_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.flag} {l.name}
                </option>
              ))}
            </select>

            {transcripts.length > 0 && (
              <>
                <button
                  type="button"
                  className="vs__save-note-btn"
                  onClick={handleSaveAsVoiceNote}
                  disabled={isSavingNote}
                  title="Save current spoken session to Voice Notes Library"
                >
                  💾 {isSavingNote ? 'Saving…' : 'Save Note'}
                </button>
                <button
                  type="button"
                  className="vs__clear"
                  onClick={clearTranscripts}
                  title="Clear transcripts"
                >
                  Clear
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Mic permission warning */}
      {activeTab === 'live' && micPermission === false && (
        <div className="vs__warning">
          🎤 Microphone access is required for voice interaction. Please allow
          microphone access in your browser settings and reload the page.
        </div>
      )}

      {/* VIEW 1: LIVE VOICE SESSION */}
      {activeTab === 'live' && (
        <>
          {/* Transcript list */}
          <div className="vs__transcripts" aria-label="Transcripts" aria-live="polite">
            {transcripts.length === 0 && !isProcessing && !isRecording && (
              <div className="vs__empty">
                <p>👆 Tap the microphone button and start speaking</p>
                <p className="vs__empty-hint">
                  or press <kbd>Space</kbd> to toggle listening
                </p>
              </div>
            )}

            {isProcessing && (
              <div className="vs__processing">
                <span className="vs__processing-dot" />
                <span>Transcribing and processing with AI…</span>
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

          {/* Live spoken preview while user is speaking */}
          {isRecording && (
            <div className="vs__live-caption" aria-live="polite">
              <div className="vs__live-caption-header">
                <span className="vs__live-caption-dot" />
                <span className="vs__live-caption-status">Listening…</span>
              </div>
              <p className="vs__live-caption-text">
                {liveCaption ? `“${liveCaption}”` : 'Speak now into your microphone…'}
              </p>
            </div>
          )}

          {/* Error display */}
          {error && (
            <div className="vs__error" role="alert">
              <span>{error}</span>
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
            {/* Dynamic audio waveform visualizer when recording */}
            {isRecording && (
              <div className="vs__waveform" aria-label="Microphone volume">
                {audioLevels.map((lvl, idx) => (
                  <span
                    key={idx}
                    className="vs__waveform-bar"
                    style={{ height: `${Math.min(48, Math.max(8, lvl))}px` }}
                  />
                ))}
              </div>
            )}

            {/* Mic toggle button */}
            <div className="vs__mic-wrap">
              <button
                className={`vs__mic${isRecording ? ' vs__mic--recording' : ''}${isProcessing ? ' vs__mic--busy' : ''}${isSpeaking ? ' vs__mic--speaking' : ''}${!micPermission ? ' vs__mic--disabled' : ''}`}
                onClick={toggleRecording}
                disabled={!micPermission || isProcessing}
                aria-label={
                  isSpeaking
                    ? 'Stop AI voice'
                    : isRecording
                      ? 'Stop and send'
                      : 'Tap to speak'
                }
                title={
                  isSpeaking
                    ? 'Stop AI speaking'
                    : isRecording
                      ? 'Tap to stop & send'
                      : 'Tap to speak'
                }
                type="button"
              >
                {isRecording ? (
                  <span className="vs__mic-icon">■</span>
                ) : isProcessing ? (
                  <span className="vs__mic-spinner" />
                ) : isSpeaking ? (
                  <span className="vs__mic-icon">⏹</span>
                ) : (
                  <span className="vs__mic-icon">🎤</span>
                )}
              </button>
              {isRecording && (
                <span className="vs__recording-label" aria-live="polite">
                  Recording… Tap to send
                </span>
              )}
              {isSpeaking && (
                <span className="vs__recording-label" aria-live="polite">
                  Speaking… (click to interrupt)
                </span>
              )}
            </div>

            {/* Dedicated Stop Speaking Button */}
            {isSpeaking && (
              <button
                type="button"
                className="vs__stop-speaking-btn"
                onClick={stopSpeaking}
                title="Stop AI speaking"
                aria-label="Stop AI speaking"
              >
                ⏹ Stop Speaking
              </button>
            )}

            {/* Hint */}
            <div className="vs__hint">
              {isSpeaking
                ? 'Speaking · Tap button or space to interrupt'
                : isRecording
                  ? 'Listening · Tap again or hit Space to finish'
                  : micPermission
                    ? 'Tap mic to talk · Hit Space to toggle'
                    : 'Mic access required'}
            </div>
          </div>
        </>
      )}

      {/* VIEW 2: VOICE NOTES & TRANSCRIPTS LIBRARY */}
      {activeTab === 'library' && (
        <div className="vs__library" aria-label="Voice Notes Library">
          <div className="vs__library-toolbar">
            <input
              type="search"
              className="vs__library-search"
              placeholder="Search voice notes by keyword, title, or transcript..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search voice notes"
            />
            <button
              type="button"
              className="vs__note-action-btn"
              onClick={() => void fetchSavedRecordings(searchQuery)}
              title="Refresh voice notes list"
            >
              🔄 Refresh
            </button>
          </div>

          {loadingRecordings && (
            <div className="vs__processing">
              <span className="vs__processing-dot" />
              <span>Loading saved voice notes…</span>
            </div>
          )}

          {!loadingRecordings && savedRecordings.length === 0 && (
            <div className="vs__library-empty">
              <span className="vs__library-empty-icon">🎙️</span>
              <h3 className="vs__library-empty-title">
                {searchQuery ? 'No matching voice notes found' : 'No Voice Recordings Yet'}
              </h3>
              <p className="vs__library-empty-sub">
                {searchQuery
                  ? `No voice notes matched "${searchQuery}". Try a different search term.`
                  : 'Your voice library is clean and ready. Record memos in a Live Voice Session or ask Roxy to transcribe your meetings.'}
              </p>
              {!searchQuery && (
                <button
                  type="button"
                  className="vs__library-start-btn"
                  onClick={() => setActiveTab('live')}
                >
                  🎙️ Start Live Voice Session
                </button>
              )}
            </div>
          )}

          {!loadingRecordings && savedRecordings.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {savedRecordings.map((rec) => {
                const isExpanded = expandedId === rec.id;
                return (
                  <div key={rec.id} className="vs__note-card">
                    <div className="vs__note-card-header">
                      <div>
                        <h4 className="vs__note-title">{rec.title}</h4>
                        <div className="vs__note-meta">
                          {rec.created_at && (
                            <span className="vs__note-badge">
                              📅 {new Date(rec.created_at).toLocaleDateString()} {new Date(rec.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          )}
                          {rec.duration_seconds ? (
                            <span className="vs__note-badge">⏱️ {Math.round(rec.duration_seconds)}s</span>
                          ) : null}
                          {rec.language && (
                            <span className="vs__note-badge">🌐 {rec.language.toUpperCase()}</span>
                          )}
                          {rec.voice_model && (
                            <span className="vs__note-badge">⚡ {rec.voice_model}</span>
                          )}
                          {rec.tags?.map((t) => (
                            <span key={t} className="vs__note-badge">🏷️ {t}</span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {rec.summary && (
                      <div className="vs__note-summary-box">
                        <strong>AI Summary:</strong> {rec.summary}
                      </div>
                    )}

                    <div className="vs__note-transcript">
                      {isExpanded
                        ? rec.transcript
                        : rec.transcript.length > 220
                          ? `${rec.transcript.slice(0, 220)}…`
                          : rec.transcript}
                    </div>

                    <div className="vs__note-actions">
                      {rec.transcript.length > 220 && (
                        <button
                          type="button"
                          className="vs__note-action-btn"
                          onClick={() => setExpandedId(isExpanded ? null : rec.id)}
                        >
                          {isExpanded ? 'Show Less' : 'Read Full Transcript'}
                        </button>
                      )}
                      <button
                        type="button"
                        className="vs__note-action-btn"
                        onClick={() => handleCopyTranscript(rec.transcript)}
                        title="Copy transcript to clipboard"
                      >
                        📋 Copy
                      </button>
                      {rec.summary && (
                        <button
                          type="button"
                          className="vs__note-action-btn"
                          onClick={() => speakText(rec.summary!)}
                          title="Speak executive summary"
                        >
                          🔊 Read Summary
                        </button>
                      )}
                      <button
                        type="button"
                        className="vs__note-action-btn vs__note-action-btn--delete"
                        onClick={() => handleDeleteRecording(rec.id)}
                        title="Delete voice note"
                      >
                        🗑️ Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Toast Feedback */}
      {toastMessage && (
        <div className="vs__toast" role="status">
          {toastMessage}
        </div>
      )}
    </div>
  );
};
