/**
 * VoiceManager — Centralized, Production-Grade Voice Lifecycle Orchestration
 * 
 * Provides unified, isolated, and strictly controlled voice architecture across:
 * - Chat
 * - Calendar
 * - Calculator
 * - Email
 * - Image Studio
 * - Video Studio
 * - Deep Research
 * - Browser Studio
 * 
 * Architecture:
 * VoiceManager
 * ├── STTController (Live streaming interim + final transcription, explicit manual controls)
 * ├── TTSController (Independent speech synthesis, explicit Listen / Stop Speaking)
 * ├── PlaybackController (Audio resource management & clean release)
 * └── SessionLifecycleManager (Route change cleanup, single-session guarantee, tool isolation)
 */

export interface STTStartOptions {
  toolId?: string;
  lang?: string;
  onInterim?: (interimText: string) => void;
  onFinal: (finalText: string) => void;
  onError?: (error: string) => void;
  onStateChange?: (state: 'idle' | 'listening' | 'transcribing') => void;
}

export interface TTSSpeakOptions {
  toolId?: string;
  voiceLang?: string;
  rate?: number;
  pitch?: number;
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (error: string) => void;
}

const rawApiBase =
  (typeof import.meta !== 'undefined' && (import.meta as { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE) ||
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

// Safe detection of Web Speech API
const SpeechRecognitionClass =
  typeof window !== 'undefined'
    ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    : null;

class STTController {
  private activeRecognition: any = null;
  private activeMediaRecorder: MediaRecorder | null = null;
  private activeMediaStream: MediaStream | null = null;
  private activeAudioChunks: Blob[] = [];
  private accumulatedFinalText = '';
  private currentInterimText = '';
  private activeToolId: string | null = null;
  private stateChangeCallback?: (state: 'idle' | 'listening' | 'transcribing') => void;
  private onFinalCallback?: (text: string) => void;
  private onInterimCallback?: (text: string) => void;
  private onErrorCallback?: (err: string) => void;
  private activeLang: string = 'en-US';
  private silenceTimeout: any = null;
  private isListeningState = false;

  get isListening(): boolean {
    return this.isListeningState;
  }

  get currentToolId(): string | null {
    return this.activeToolId;
  }

  async startListening(options: STTStartOptions): Promise<void> {
    // 1. Clean up any existing active voice session first
    this.stopListening(false);

    this.activeToolId = options.toolId || 'global';
    this.onFinalCallback = options.onFinal;
    this.onInterimCallback = options.onInterim;
    this.onErrorCallback = options.onError;
    this.stateChangeCallback = options.onStateChange;
    this.accumulatedFinalText = '';
    this.currentInterimText = '';
    this.activeLang = options.lang || 'en-US';

    this.isListeningState = true;
    this.stateChangeCallback?.('listening');

    // 2. Try Web Speech API for real-time live interim streaming
    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = this.activeLang;

        recognition.onresult = (event: any) => {
          let interim = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              this.accumulatedFinalText += (this.accumulatedFinalText ? ' ' : '') + transcript.trim();
            } else {
              interim += transcript;
            }
          }
          this.currentInterimText = interim;

          const liveCombined = (this.accumulatedFinalText + (interim ? ' ' + interim : '')).trim();
          this.onInterimCallback?.(liveCombined || interim);

          // Reset generous inactivity timeout (12 seconds of complete silence)
          if (this.silenceTimeout) clearTimeout(this.silenceTimeout);
          this.silenceTimeout = setTimeout(() => {
            if (this.isListeningState) {
              this.stopListening(true);
            }
          }, 12000);
        };

        recognition.onerror = (event: any) => {
          if (event.error === 'no-speech') {
            return;
          }
          if (event.error === 'aborted') {
            return;
          }
          const errDetail = event.error || 'Speech recognition encountered an issue';
          this.onErrorCallback?.(errDetail);
          this.stopListening(false);
        };

        recognition.onend = () => {
          if (this.isListeningState) {
            // Unexpected stop or stream completed: finalize transcript
            this.finishSTT();
          }
        };

        this.activeRecognition = recognition;
        recognition.start();
        return;
      } catch (err) {
        console.warn('VoiceManager: WebSpeech failed to start, falling back to MediaRecorder:', err);
      }
    }

    // 3. Fallback: HTML5 MediaRecorder + Backend STT Skill
    if (typeof navigator !== 'undefined' && navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.activeMediaStream = stream;
        this.activeAudioChunks = [];

        const recorder = new MediaRecorder(stream);
        this.activeMediaRecorder = recorder;

        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            this.activeAudioChunks.push(e.data);
          }
        };

        recorder.onstop = async () => {
          const tracks = stream.getTracks();
          tracks.forEach((t) => t.stop());
          this.activeMediaStream = null;

          if (this.activeAudioChunks.length > 0) {
            this.stateChangeCallback?.('transcribing');
            const blob = new Blob(this.activeAudioChunks, { type: 'audio/webm' });
            await this.transcribeAudioBlob(blob);
          } else {
            this.stateChangeCallback?.('idle');
          }
        };

        recorder.start(250);
      } catch (err: any) {
        this.isListeningState = false;
        this.stateChangeCallback?.('idle');
        this.onErrorCallback?.(err.message || 'Microphone access denied or unavailable');
      }
    } else {
      this.isListeningState = false;
      this.stateChangeCallback?.('idle');
      this.onErrorCallback?.('Speech recognition is not supported in this browser');
    }
  }

  stopListening(deliverFinal = true): void {
    if (this.silenceTimeout) {
      clearTimeout(this.silenceTimeout);
      this.silenceTimeout = null;
    }

    const wasListening = this.isListeningState;
    this.isListeningState = false;

    if (this.activeRecognition) {
      try {
        this.activeRecognition.stop();
      } catch {
        // ignore
      }
      this.activeRecognition = null;
    }

    if (this.activeMediaRecorder && this.activeMediaRecorder.state !== 'inactive') {
      try {
        this.activeMediaRecorder.stop();
      } catch {
        // ignore
      }
      this.activeMediaRecorder = null;
    }

    if (this.activeMediaStream) {
      this.activeMediaStream.getTracks().forEach((t) => t.stop());
      this.activeMediaStream = null;
    }

    if (wasListening && deliverFinal) {
      this.finishSTT();
    } else {
      this.stateChangeCallback?.('idle');
    }
  }

  private finishSTT(): void {
    const finalResult = (this.accumulatedFinalText + (this.currentInterimText ? ' ' + this.currentInterimText : '')).trim();
    this.stateChangeCallback?.('idle');
    if (finalResult && this.onFinalCallback) {
      this.onFinalCallback(finalResult);
    }
    this.accumulatedFinalText = '';
    this.currentInterimText = '';
  }

  private async transcribeAudioBlob(blob: Blob): Promise<void> {
    if (blob.size < 200) {
      this.stateChangeCallback?.('idle');
      return;
    }
    try {
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve, reject) => {
        reader.onloadend = () => {
          const res = reader.result as string;
          resolve(res.includes(',') ? res.split(',')[1] : res);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
      const audio_data = await base64Promise;
      const token = typeof localStorage !== 'undefined' ? localStorage.getItem('roxy.access_token') : null;

      const resp = await fetch(`${API_BASE}/skills/speech_to_text`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          audio_data,
          language: this.activeLang !== 'auto' ? this.activeLang : null,
          model: 'gemini',
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        const text = (data.text || '').trim();
        if (text && this.onFinalCallback) {
          this.onFinalCallback(text);
        }
      } else {
        const errJson = await resp.json().catch(() => null);
        this.onErrorCallback?.(errJson?.detail || 'Transcription service error');
      }
    } catch (err: any) {
      this.onErrorCallback?.(err.message || 'Audio transcription network error');
    } finally {
      this.stateChangeCallback?.('idle');
    }
  }
}

class TTSController {
  private activeUtterance: SpeechSynthesisUtterance | null = null;
  private activeAudioElement: HTMLAudioElement | null = null;
  private isSpeakingState = false;
  private activeToolId: string | null = null;

  get isSpeaking(): boolean {
    return this.isSpeakingState;
  }

  get currentToolId(): string | null {
    return this.activeToolId;
  }

  get currentUtterance(): SpeechSynthesisUtterance | null {
    return this.activeUtterance;
  }

  async speak(text: string, options: TTSSpeakOptions = {}): Promise<void> {
    // 1. Immediately cancel any currently playing TTS
    this.stopSpeaking();

    const cleanText = text
      .replace(/```[\s\S]*?```/g, 'Code block omitted.')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/[*#_~>\[\]]/g, '')
      .replace(/\(http[^\)]+\)/g, '')
      .trim();

    if (!cleanText) return;

    this.activeToolId = options.toolId || 'global';
    this.isSpeakingState = true;

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.resume();

      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = options.rate ?? 1.0;
      utterance.pitch = options.pitch ?? 1.0;

      // Select high quality voice matching requested language if available
      const voices = window.speechSynthesis.getVoices();
      if (voices.length > 0) {
        const langCode = options.voiceLang || 'en';
        const match = voices.find(
          (v) => v.lang.startsWith(langCode) || v.name.toLowerCase().includes(langCode)
        );
        if (match) {
          utterance.voice = match;
        }
      }

      utterance.onstart = () => {
        this.isSpeakingState = true;
        options.onStart?.();
      };

      utterance.onend = () => {
        this.isSpeakingState = false;
        this.activeUtterance = null;
        options.onEnd?.();
      };

      utterance.onerror = (e) => {
        this.isSpeakingState = false;
        this.activeUtterance = null;
        if (e.error !== 'canceled') {
          options.onError?.(e.error || 'Speech synthesis error');
        }
      };

      this.activeUtterance = utterance;
      window.speechSynthesis.speak(utterance);
    } else {
      this.isSpeakingState = false;
      options.onError?.('Text-to-speech is not supported in this browser.');
    }
  }

  stopSpeaking(): void {
    this.isSpeakingState = false;
    this.activeToolId = null;

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {
        // ignore
      }
    }
    this.activeUtterance = null;

    if (this.activeAudioElement) {
      try {
        this.activeAudioElement.pause();
        this.activeAudioElement.currentTime = 0;
      } catch {
        // ignore
      }
      this.activeAudioElement = null;
    }
  }
}

class PlaybackController {
  private activeElements: Set<HTMLAudioElement | HTMLVideoElement> = new Set();

  registerMedia(el: HTMLAudioElement | HTMLVideoElement): void {
    this.activeElements.add(el);
  }

  unregisterMedia(el: HTMLAudioElement | HTMLVideoElement): void {
    this.activeElements.delete(el);
  }

  stopAllPlayback(): void {
    this.activeElements.forEach((el) => {
      try {
        el.pause();
        el.currentTime = 0;
      } catch {
        // ignore
      }
    });
    this.activeElements.clear();
  }
}

class SessionLifecycleManager {
  private stt: STTController;
  private tts: TTSController;
  private playback: PlaybackController;

  constructor(stt: STTController, tts: TTSController, playback: PlaybackController) {
    this.stt = stt;
    this.tts = tts;
    this.playback = playback;

    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => this.cleanupVoiceSession());
      window.addEventListener('popstate', () => this.cleanupVoiceSession());
      window.addEventListener('hashchange', () => this.cleanupVoiceSession());
    }
  }

  cleanupVoiceSession(toolId?: string): void {
    // If toolId is provided and different from current tool, ignore unless global
    if (toolId && this.stt.currentToolId && this.stt.currentToolId !== toolId && toolId !== 'global') {
      return;
    }
    this.stt.stopListening(false);
    this.tts.stopSpeaking();
    this.playback.stopAllPlayback();
  }
}

export class VoiceManager {
  readonly stt = new STTController();
  readonly tts = new TTSController();
  readonly playback = new PlaybackController();
  readonly lifecycle: SessionLifecycleManager;

  constructor() {
    this.lifecycle = new SessionLifecycleManager(this.stt, this.tts, this.playback);
  }

  /**
   * Evaluates whether Auto-Play Voice Responses is explicitly enabled by the user in Settings.
   * If false, NO tool may start speech automatically.
   */
  isAutoPlayAllowed(): boolean {
    if (typeof localStorage === 'undefined') return false;
    try {
      const explicit = localStorage.getItem('roxy_auto_play_voice');
      if (explicit !== null) {
        return explicit === 'true';
      }
      const settingsRaw = localStorage.getItem('roxy_guest_settings');
      if (settingsRaw) {
        const s = JSON.parse(settingsRaw);
        return Boolean(s.auto_play_voice_responses || s.voice_auto_play);
      }
    } catch {
      // fallback safe default: false
    }
    return false;
  }

  /**
   * Clean up all active audio, STT listeners, and pending speech playback.
   */
  cleanupVoiceSession(toolId?: string): void {
    this.lifecycle.cleanupVoiceSession(toolId);
  }
}

export const voiceManager = new VoiceManager();
