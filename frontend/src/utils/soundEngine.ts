/**
 * ROXY Universal Sound & Ringtone Engine (Part B).
 *
 * Implements 100% legal procedural harmonic audio synthesis using the Web Audio API
 * (zero external sound files, zero copyright risks, instant playback, zero network latency)
 * plus support for custom uploaded audio formats (mp3/wav/ogg).
 */

export interface BuiltinSoundDef {
  id: string;
  name: string;
  description: string;
  category: 'gentle' | 'calm' | 'classic' | 'modern' | 'cheerful' | 'professional' | 'urgent' | 'minimal' | 'custom';
  durationSeconds: number;
  isBuiltin: boolean;
  synthPreset: string;
  dataUri?: string;
}

export const BUILTIN_SOUNDS: BuiltinSoundDef[] = [
  {
    id: 'roxy_harmonic',
    name: 'Roxy Harmonic Chime',
    description: 'Signature dual-tone soft chime with warm harmonic resonance.',
    category: 'gentle',
    durationSeconds: 2.4,
    isBuiltin: true,
    synthPreset: 'harmonic_dual',
  },
  {
    id: 'soft_zen',
    name: 'Soft Zen Bell',
    description: 'Deep calming singing-bowl chime for focused, peaceful reminders.',
    category: 'calm',
    durationSeconds: 3.0,
    isBuiltin: true,
    synthPreset: 'zen_bowl',
  },
  {
    id: 'crystal_chime',
    name: 'Gentle Crystal Chime',
    description: 'High-register crystal bell with decaying shimmer.',
    category: 'gentle',
    durationSeconds: 2.2,
    isBuiltin: true,
    synthPreset: 'crystal_ping',
  },
  {
    id: 'classic_brass',
    name: 'Classic Brass Bell',
    description: 'Warm retro acoustic desktop chime.',
    category: 'classic',
    durationSeconds: 1.8,
    isBuiltin: true,
    synthPreset: 'brass_strike',
  },
  {
    id: 'digital_pulse',
    name: 'Modern Digital Pulse',
    description: 'Clean FM synthesized double-tap notification.',
    category: 'modern',
    durationSeconds: 1.5,
    isBuiltin: true,
    synthPreset: 'digital_tap',
  },
  {
    id: 'morning_sunrise',
    name: 'Morning Sunrise',
    description: 'Ascending major triad with uplifting sustain.',
    category: 'cheerful',
    durationSeconds: 2.8,
    isBuiltin: true,
    synthPreset: 'sunrise_arpeggio',
  },
  {
    id: 'executive_tone',
    name: 'Executive Tone',
    description: 'Crisp professional chime suited for corporate and client meetings.',
    category: 'professional',
    durationSeconds: 2.0,
    isBuiltin: true,
    synthPreset: 'executive_triad',
  },
  {
    id: 'urgent_alert',
    name: 'Priority Urgent Alert',
    description: 'Dual frequency alert tone for critical deadlines and high-priority alarms.',
    category: 'urgent',
    durationSeconds: 2.5,
    isBuiltin: true,
    synthPreset: 'urgent_pulse',
  },
  {
    id: 'radiant_pulsar',
    name: 'Radiant Pulsar',
    description: 'Rhythmic pulsing chime for ambient task completion.',
    category: 'modern',
    durationSeconds: 2.6,
    isBuiltin: true,
    synthPreset: 'pulsar_loop',
  },
  {
    id: 'whisper_pop',
    name: 'Soft Whisper Pop',
    description: 'Low-impact wooden pop for subtle non-intrusive pings.',
    category: 'minimal',
    durationSeconds: 1.1,
    isBuiltin: true,
    synthPreset: 'wood_pop',
  },
];

class SoundEngine {
  private audioCtx: AudioContext | null = null;
  private currentAudioElement: HTMLAudioElement | null = null;
  private currentlyPlayingId: string | null = null;
  private masterVolume: number = 0.85;
  private isMuted: boolean = false;
  private listeners: Set<(soundId: string | null) => void> = new Set();

  private getContext(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    if (!this.audioCtx) {
      const AudioContextClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (AudioContextClass) {
        this.audioCtx = new AudioContextClass();
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
    return this.audioCtx;
  }

  public setVolume(vol: number): void {
    const normalized = vol > 1 ? vol / 100 : vol;
    this.masterVolume = Math.max(0, Math.min(1, normalized));
  }

  public getVolume(): number {
    return Math.round(this.masterVolume * 100);
  }

  public setMute(muted: boolean): void {
    this.isMuted = muted;
    if (muted) {
      this.stop();
    }
  }

  public getMute(): boolean {
    return this.isMuted;
  }

  public getCurrentlyPlaying(): string | null {
    return this.currentlyPlayingId;
  }

  public onPlaybackChange(listener: (soundId: string | null) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(soundId: string | null): void {
    this.currentlyPlayingId = soundId;
    this.listeners.forEach((l) => l(soundId));
  }

  public stop(): void {
    if (this.currentAudioElement) {
      this.currentAudioElement.pause();
      this.currentAudioElement.currentTime = 0;
      this.currentAudioElement = null;
    }
    this.notify(null);
  }

  /**
   * Play any sound by id or custom dataUri.
   */
  public async play(soundId: string, customDataUri?: string): Promise<void> {
    if (this.isMuted) return;

    this.stop();

    // 1. Check if custom dataUri or custom sound
    if (customDataUri || soundId.startsWith('custom_')) {
      if (customDataUri) {
        try {
          const audio = new Audio(customDataUri);
          audio.volume = this.masterVolume;
          this.currentAudioElement = audio;
          this.notify(soundId);
          audio.onended = () => {
            this.currentAudioElement = null;
            this.notify(null);
          };
          await audio.play();
          return;
        } catch {
          // Fallback to procedural synth if audio playback fails
        }
      }
    }

    // 2. Procedural harmonic synthesis
    const ctx = this.getContext();
    if (!ctx) return;

    this.notify(soundId);
    const now = ctx.currentTime;
    const gainNode = ctx.createGain();
    gainNode.gain.setValueAtTime(this.masterVolume, now);
    gainNode.connect(ctx.destination);

    switch (soundId) {
      case 'soft_zen':
        this.synthZenBowl(ctx, gainNode, now);
        break;
      case 'crystal_chime':
        this.synthCrystalChime(ctx, gainNode, now);
        break;
      case 'classic_brass':
        this.synthBrassBell(ctx, gainNode, now);
        break;
      case 'digital_pulse':
        this.synthDigitalPulse(ctx, gainNode, now);
        break;
      case 'morning_sunrise':
        this.synthMorningSunrise(ctx, gainNode, now);
        break;
      case 'executive_tone':
        this.synthExecutiveTone(ctx, gainNode, now);
        break;
      case 'urgent_alert':
        this.synthUrgentAlert(ctx, gainNode, now);
        break;
      case 'radiant_pulsar':
        this.synthRadiantPulsar(ctx, gainNode, now);
        break;
      case 'whisper_pop':
        this.synthWhisperPop(ctx, gainNode, now);
        break;
      case 'roxy_harmonic':
      default:
        this.synthRoxyHarmonic(ctx, gainNode, now);
        break;
    }

    // Reset notification state after duration
    const def = BUILTIN_SOUNDS.find((s) => s.id === soundId) || BUILTIN_SOUNDS[0];
    window.setTimeout(() => {
      if (this.currentlyPlayingId === soundId) {
        this.notify(null);
      }
    }, def.durationSeconds * 1000);
  }

  // --- Procedural Synthesizer Implementations ---

  private synthRoxyHarmonic(ctx: AudioContext, dest: GainNode, t: number): void {
    // Dual tone 528Hz (Solfeggio love frequency) & 792Hz harmonic fifth
    [528, 792].forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, t + idx * 0.08);

      gain.gain.setValueAtTime(0, t + idx * 0.08);
      gain.gain.linearRampToValueAtTime(0.4, t + idx * 0.08 + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + idx * 0.08 + 2.0);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t + idx * 0.08);
      osc.stop(t + idx * 0.08 + 2.1);
    });
  }

  private synthZenBowl(ctx: AudioContext, dest: GainNode, t: number): void {
    // Low singing bowl with gentle overtones (216Hz, 432Hz, 648Hz)
    [216, 432, 648].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, t);

      const amp = i === 0 ? 0.5 : 0.2 / i;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(amp, t + 0.1);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 2.8);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t);
      osc.stop(t + 2.9);
    });
  }

  private synthCrystalChime(ctx: AudioContext, dest: GainNode, t: number): void {
    // High crystal bell triad C6-E6-G6
    [1046.5, 1318.5, 1568.0].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, t + i * 0.05);

      gain.gain.setValueAtTime(0, t + i * 0.05);
      gain.gain.linearRampToValueAtTime(0.3, t + i * 0.05 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.05 + 1.9);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t + i * 0.05);
      osc.stop(t + i * 0.05 + 2.0);
    });
  }

  private synthBrassBell(ctx: AudioContext, dest: GainNode, t: number): void {
    // Retro brass strike bell
    const freqs = [440, 880, 1320, 1760];
    freqs.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = i % 2 === 0 ? 'sine' : 'triangle';
      osc.frequency.setValueAtTime(freq, t);

      gain.gain.setValueAtTime(0.4 / (i + 1), t);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 1.6);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t);
      osc.stop(t + 1.7);
    });
  }

  private synthDigitalPulse(ctx: AudioContext, dest: GainNode, t: number): void {
    // Modern double digital tap
    [0, 0.12].forEach((offset) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.setValueAtTime(987.77, t + offset); // B5

      gain.gain.setValueAtTime(0, t + offset);
      gain.gain.linearRampToValueAtTime(0.25, t + offset + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + offset + 0.35);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t + offset);
      osc.stop(t + offset + 0.4);
    });
  }

  private synthMorningSunrise(ctx: AudioContext, dest: GainNode, t: number): void {
    // Ascending arpeggio C5 -> E5 -> G5 -> C6
    const notes = [523.25, 659.25, 783.99, 1046.5];
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, t + idx * 0.14);

      gain.gain.setValueAtTime(0, t + idx * 0.14);
      gain.gain.linearRampToValueAtTime(0.35, t + idx * 0.14 + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + idx * 0.14 + 1.6);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t + idx * 0.14);
      osc.stop(t + idx * 0.14 + 1.7);
    });
  }

  private synthExecutiveTone(ctx: AudioContext, dest: GainNode, t: number): void {
    // Professional double chime (587Hz D5 & 880Hz A5)
    [
      { freq: 587.33, offset: 0 },
      { freq: 880.0, offset: 0.1 },
    ].forEach(({ freq, offset }) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, t + offset);

      gain.gain.setValueAtTime(0, t + offset);
      gain.gain.linearRampToValueAtTime(0.4, t + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + offset + 1.6);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t + offset);
      osc.stop(t + offset + 1.7);
    });
  }

  private synthUrgentAlert(ctx: AudioContext, dest: GainNode, t: number): void {
    // Urgent dual frequency pulsing alert
    [0, 0.22, 0.44].forEach((offset) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(880, t + offset);
      osc.frequency.linearRampToValueAtTime(988, t + offset + 0.1);

      gain.gain.setValueAtTime(0.45, t + offset);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + offset + 0.18);

      osc.connect(gain);
      gain.connect(dest);
      osc.start(t + offset);
      osc.stop(t + offset + 0.2);
    });
  }

  private synthRadiantPulsar(ctx: AudioContext, dest: GainNode, t: number): void {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(440, t);
    osc.frequency.exponentialRampToValueAtTime(880, t + 0.8);

    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.35, t + 0.1);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 2.4);

    osc.connect(gain);
    gain.connect(dest);
    osc.start(t);
    osc.stop(t + 2.5);
  }

  private synthWhisperPop(ctx: AudioContext, dest: GainNode, t: number): void {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(320, t);
    osc.frequency.exponentialRampToValueAtTime(80, t + 0.08);

    gain.gain.setValueAtTime(0.5, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);

    osc.connect(gain);
    gain.connect(dest);
    osc.start(t);
    osc.stop(t + 0.1);
  }

  /**
   * Request native browser notifications permission.
   */
  public async requestNotificationPermission(): Promise<boolean> {
    if (typeof window === 'undefined' || !('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission !== 'denied') {
      const perm = await Notification.requestPermission();
      return perm === 'granted';
    }
    return false;
  }

  /**
   * Display native system notification and play reminder sound.
   */
  public async showSystemNotification(
    title: string,
    options?: { body?: string; soundId?: string; icon?: string }
  ): Promise<void> {
    const soundId = options?.soundId || 'roxy_harmonic';
    await this.play(soundId);

    if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification(title, {
          body: options?.body || 'ROXY Reminder Triggered',
          icon: options?.icon || '/roxy-icon.png',
          silent: true, // We handle our own audio synthesis
        });
      } catch {
        // Fallback gracefully
      }
    }
  }
}

export const soundEngine = new SoundEngine();
