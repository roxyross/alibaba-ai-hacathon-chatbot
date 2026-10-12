import { describe, it, expect, beforeEach, vi } from 'vitest';
import { soundEngine, BUILTIN_SOUNDS } from '../soundEngine';

describe('ROXY Universal Sound & Ringtone Engine Suite', () => {
  beforeEach(() => {
    soundEngine.stop();
    soundEngine.setMute(false);
    soundEngine.setVolume(80);
  });

  it('exposes exactly 10 legal built-in procedural harmonic sound presets', () => {
    expect(BUILTIN_SOUNDS).toHaveLength(10);

    const soundIds = BUILTIN_SOUNDS.map((s) => s.id);
    expect(soundIds).toContain('roxy_harmonic');
    expect(soundIds).toContain('soft_zen');
    expect(soundIds).toContain('crystal_chime');
    expect(soundIds).toContain('classic_brass');
    expect(soundIds).toContain('digital_pulse');
    expect(soundIds).toContain('morning_sunrise');
    expect(soundIds).toContain('executive_tone');
    expect(soundIds).toContain('urgent_alert');
    expect(soundIds).toContain('radiant_pulsar');
    expect(soundIds).toContain('whisper_pop');

    for (const sound of BUILTIN_SOUNDS) {
      expect(sound.isBuiltin).toBe(true);
      expect(sound.name.length).toBeGreaterThan(0);
      expect(sound.durationSeconds).toBeGreaterThan(0);
      expect(sound.synthPreset).toBeDefined();
    }
  });

  it('handles volume configuration and clamps within bounds (0..100)', () => {
    soundEngine.setVolume(50);
    expect(soundEngine.getVolume()).toBe(50);

    soundEngine.setVolume(150);
    expect(soundEngine.getVolume()).toBe(100);

    soundEngine.setVolume(-20);
    expect(soundEngine.getVolume()).toBe(0);
  });

  it('handles mute toggle correctly', () => {
    expect(soundEngine.getMute()).toBe(false);

    soundEngine.setMute(true);
    expect(soundEngine.getMute()).toBe(true);

    soundEngine.setMute(false);
    expect(soundEngine.getMute()).toBe(false);
  });

  it('notifies subscribers on playback state changes', () => {
    const listener = vi.fn();
    const unsubscribe = soundEngine.onPlaybackChange(listener);

    soundEngine.stop();
    expect(listener).toHaveBeenCalledWith(null);

    unsubscribe();
  });
});
