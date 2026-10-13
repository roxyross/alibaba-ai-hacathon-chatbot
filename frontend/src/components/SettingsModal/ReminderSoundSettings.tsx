import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Play,
  Square,
  Upload,
  Trash2,
  Volume2,
  VolumeX,
  Smartphone,
  Laptop,
  Tablet,
  Bell,
  Sparkles,
  Check,
  AlertCircle,
} from 'lucide-react';
import { soundEngine, BUILTIN_SOUNDS, BuiltinSoundDef } from '../../utils/soundEngine';
import './ReminderSoundSettings.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface ReminderSettingsData {
  default_sound_id: string;
  volume: number;
  muted: boolean;
  vibrate: boolean;
  default_snooze_minutes: number;
  per_device_sounds: Record<string, string>;
  per_event_sounds: Record<string, string>;
}

export interface CustomSoundItem {
  id: string;
  name: string;
  filename: string;
  url: string;
  size_bytes: number;
  created_at: string;
}

interface ReminderSoundSettingsProps {
  accessToken?: string | null;
}

export const ReminderSoundSettings: React.FC<ReminderSoundSettingsProps> = ({
  accessToken,
}) => {
  const [settings, setSettings] = useState<ReminderSettingsData>({
    default_sound_id: 'roxy_harmonic',
    volume: 85,
    muted: false,
    vibrate: true,
    default_snooze_minutes: 10,
    per_device_sounds: {
      desktop_windows: 'roxy_harmonic',
      android_phone: 'crystal_chime',
      ios_tablet: 'soft_zen',
    },
    per_event_sounds: {
      meeting: 'executive_tone',
      task: 'soft_zen',
      urgent_reminder: 'urgent_alert',
      personal: 'crystal_chime',
    },
  });

  const [customSounds, setCustomSounds] = useState<CustomSoundItem[]>([]);
  const [playingSoundId, setPlayingSoundId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync sound playing state from soundEngine
  useEffect(() => {
    return soundEngine.onPlaybackChange((id) => {
      setPlayingSoundId(id);
    });
  }, []);

  // Fetch initial settings & custom sounds
  const fetchSettings = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/reminders/settings`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const rawVol = typeof data.volume === 'number' ? data.volume : 85;
        const normalizedVol = rawVol <= 1.0 && rawVol > 0 ? Math.round(rawVol * 100) : rawVol;
        const parsedSettings: ReminderSettingsData = {
          default_sound_id: data.default_sound_id || 'roxy_harmonic',
          volume: normalizedVol,
          muted: data.muted ?? data.mute ?? false,
          vibrate: data.vibrate ?? data.vibration ?? true,
          default_snooze_minutes: data.default_snooze_minutes ?? 10,
          per_device_sounds: data.per_device_sounds || data.device_overrides || {},
          per_event_sounds: data.per_event_sounds || data.event_overrides || {},
        };
        setSettings(parsedSettings);
        soundEngine.setVolume(normalizedVol);
        soundEngine.setMute(parsedSettings.muted);
      }

      const soundsRes = await fetch(`${API_BASE}/reminders/sounds`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (soundsRes.ok) {
        const soundsData = await soundsRes.json();
        const list = soundsData.custom_sounds || (soundsData.sounds ? soundsData.sounds.filter((s: any) => !s.is_builtin) : []);
        setCustomSounds(list);
      }
    } catch {
      // Offline fallback
    }
  }, [accessToken]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // Handle Play/Stop Preview
  const handleTogglePreview = (soundId: string, customUrl?: string) => {
    if (playingSoundId === soundId) {
      soundEngine.stop();
    } else {
      soundEngine.setVolume(settings.volume);
      soundEngine.play(soundId, customUrl);
    }
  };

  // Select Default Sound
  const handleSelectSound = async (soundId: string) => {
    const updated = { ...settings, default_sound_id: soundId };
    setSettings(updated);
    saveSettingsToBackend({ default_sound_id: soundId });
  };

  // Update Settings in Backend
  const saveSettingsToBackend = async (patch: Partial<ReminderSettingsData>) => {
    if (!accessToken) return;
    setIsSaving(true);
    try {
      const payload: Record<string, any> = { ...patch };
      if (typeof payload.volume === 'number') {
        payload.volume = payload.volume > 1.0 ? payload.volume / 100.0 : payload.volume;
      }
      if ('muted' in payload) {
        payload.mute = payload.muted;
      }
      if ('vibrate' in payload) {
        payload.vibration = payload.vibrate;
      }
      if ('per_device_sounds' in payload) {
        payload.device_overrides = payload.per_device_sounds;
      }
      if ('per_event_sounds' in payload) {
        payload.event_overrides = payload.per_event_sounds;
      }

      const res = await fetch(`${API_BASE}/reminders/settings`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = await res.json();
        const rawVol = typeof data.volume === 'number' ? data.volume : 85;
        const normalizedVol = rawVol <= 1.0 && rawVol > 0 ? Math.round(rawVol * 100) : rawVol;
        setSettings((prev) => ({
          ...prev,
          default_sound_id: data.default_sound_id || prev.default_sound_id,
          volume: normalizedVol,
          muted: data.muted ?? data.mute ?? prev.muted,
          vibrate: data.vibrate ?? data.vibration ?? prev.vibrate,
          default_snooze_minutes: data.default_snooze_minutes ?? prev.default_snooze_minutes,
          per_device_sounds: data.per_device_sounds || data.device_overrides || prev.per_device_sounds,
          per_event_sounds: data.per_event_sounds || data.event_overrides || prev.per_event_sounds,
        }));
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 2000);
      }
    } catch {
      // Error handling
    } finally {
      setIsSaving(false);
    }
  };

  // Handle Volume Slider
  const handleVolumeChange = (vol: number) => {
    setSettings((prev) => ({ ...prev, volume: vol }));
    soundEngine.setVolume(vol);
  };

  const handleVolumeCommit = () => {
    saveSettingsToBackend({ volume: settings.volume });
  };

  // Handle Mute Toggle
  const handleToggleMute = () => {
    const nextMuted = !settings.muted;
    setSettings((prev) => ({ ...prev, muted: nextMuted }));
    soundEngine.setMute(nextMuted);
    saveSettingsToBackend({ muted: nextMuted });
  };

  // Handle Per-Device Sound Override
  const handleDeviceSoundChange = (deviceKey: string, soundId: string) => {
    const nextDeviceSounds = {
      ...settings.per_device_sounds,
      [deviceKey]: soundId,
    };
    setSettings((prev) => ({ ...prev, per_device_sounds: nextDeviceSounds }));
    saveSettingsToBackend({ per_device_sounds: nextDeviceSounds });
  };

  // Handle Per-Event Sound Override
  const handleEventSoundChange = (eventKey: string, soundId: string) => {
    const nextEventSounds = {
      ...settings.per_event_sounds,
      [eventKey]: soundId,
    };
    setSettings((prev) => ({ ...prev, per_event_sounds: nextEventSounds }));
    saveSettingsToBackend({ per_event_sounds: nextEventSounds });
  };

  // Handle Custom Sound Upload
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !accessToken) return;

    if (file.size > 5 * 1024 * 1024) {
      setUploadError('File exceeds 5MB size limit.');
      return;
    }

    setUploadError(null);
    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('name', file.name.replace(/\.[^/.]+$/, ''));

      const res = await fetch(`${API_BASE}/reminders/sounds/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      });

      if (res.ok) {
        const json = await res.json();
        const item: CustomSoundItem = json.sound || json;
        setCustomSounds((prev) => [...prev, item]);
        if (item.id) {
          handleSelectSound(item.id);
        }
      } else {
        const err = await res.json();
        setUploadError(err.detail || 'Upload failed');
      }
    } catch {
      setUploadError('Network error uploading sound asset');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Handle Delete Custom Sound
  const handleDeleteCustomSound = async (soundId: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/reminders/sounds/${soundId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        setCustomSounds((prev) => prev.filter((s) => s.id !== soundId));
        if (settings.default_sound_id === soundId) {
          handleSelectSound('roxy_harmonic');
        }
      }
    } catch {
      // Delete failure
    }
  };

  // Trigger Live Test Alarm
  const handleTestAlarm = () => {
    const activeSound = settings.default_sound_id;
    window.dispatchEvent(
      new CustomEvent('roxy:reminder-triggered', {
        detail: {
          id: `test-${Date.now()}`,
          user_id: 'usr-current',
          title: 'Review System Architecture & Next Milestones',
          body: 'Scheduled high-priority calendar review with ROXY Autonomous Coordinator.',
          category: 'meeting',
          sound_id: activeSound,
          target_devices: ['Windows Desktop (Current)', 'Android Mobile'],
          status: 'delivered',
          scheduled_at: new Date().toISOString(),
          delivered_at: new Date().toISOString(),
        },
      })
    );
  };

  return (
    <div className="reminder-sound-settings">
      <div className="rss-header">
        <div className="rss-header-title">
          <Bell size={18} className="rss-bell-icon" />
          <h4>Reminder Sounds &amp; Universal Ringtones</h4>
        </div>
        <div className="rss-header-actions">
          <button
            type="button"
            className="btn-test-alarm"
            onClick={handleTestAlarm}
            title="Dispatch a real test reminder alarm to experience ringtone & snooze"
          >
            <Sparkles size={14} /> Test Live Alarm
          </button>
          {isSaving ? (
            <span className="rss-saved-badge" style={{ color: '#0d9488' }}>
              Saving...
            </span>
          ) : saveSuccess ? (
            <span className="rss-saved-badge">
              <Check size={12} /> Saved
            </span>
          ) : null}
        </div>
      </div>

      <p className="rss-desc">
        Select procedural harmonic ringtones or upload custom alert audio.
        Synthesized in real-time via the Web Audio API with zero copyrighted dependencies.
      </p>

      {/* ─── 1. VOLUME & MUTE CONTROLS ───────────────────────────────── */}
      <div className="rss-audio-controls">
        <div className="rss-volume-row">
          <button
            type="button"
            className={`btn-mute-toggle ${settings.muted ? 'is-muted' : ''}`}
            onClick={handleToggleMute}
            title={settings.muted ? 'Unmute Reminders' : 'Mute Reminders'}
          >
            {settings.muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>
          <div className="rss-slider-wrap">
            <div className="rss-slider-labels">
              <span>Volume</span>
              <span className="rss-vol-val">{settings.muted ? 'Muted' : `${settings.volume}%`}</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={settings.muted ? 0 : settings.volume}
              onChange={(e) => handleVolumeChange(parseInt(e.target.value, 10))}
              onMouseUp={handleVolumeCommit}
              onTouchEnd={handleVolumeCommit}
              className="rss-slider"
            />
          </div>
        </div>

        <div className="rss-snooze-config">
          <label className="rss-sub-label">Default Snooze Interval</label>
          <select
            value={settings.default_snooze_minutes}
            onChange={(e) => {
              const mins = parseInt(e.target.value, 10);
              setSettings((prev) => ({ ...prev, default_snooze_minutes: mins }));
              saveSettingsToBackend({ default_snooze_minutes: mins });
            }}
            className="rss-select"
          >
            <option value="5">5 Minutes</option>
            <option value="10">10 Minutes (Standard)</option>
            <option value="15">15 Minutes</option>
            <option value="30">30 Minutes</option>
            <option value="60">1 Hour</option>
          </select>
        </div>
      </div>

      {/* ─── 2. BUILT-IN HARMONIC SOUND PRESETS ────────────────────────── */}
      <div className="rss-section-title">Built-In Harmonic Sound Library</div>
      <div className="rss-sound-grid">
        {BUILTIN_SOUNDS.map((sound: BuiltinSoundDef) => {
          const isSelected = settings.default_sound_id === sound.id;
          const isPlaying = playingSoundId === sound.id;

          return (
            <div
              key={sound.id}
              className={`rss-sound-card ${isSelected ? 'is-selected' : ''}`}
              onClick={() => handleSelectSound(sound.id)}
            >
              <div className="rss-card-top">
                <button
                  type="button"
                  className={`btn-preview-audio ${isPlaying ? 'is-playing' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleTogglePreview(sound.id);
                  }}
                  title={isPlaying ? 'Stop' : `Preview ${sound.name}`}
                >
                  {isPlaying ? <Square size={13} fill="currentColor" /> : <Play size={13} fill="currentColor" />}
                </button>
                <div className="rss-sound-meta">
                  <span className="rss-sound-name">{sound.name}</span>
                  <span className="rss-sound-desc">{sound.description}</span>
                </div>
              </div>

              <div className="rss-card-bottom">
                {isPlaying && (
                  <div className="rss-sound-wave" aria-label="Playing Audio Wave">
                    <span className="wave-bar bar-1" />
                    <span className="wave-bar bar-2" />
                    <span className="wave-bar bar-3" />
                    <span className="wave-bar bar-4" />
                  </div>
                )}
                {isSelected && (
                  <span className="rss-selected-pill">
                    <Check size={11} /> Default
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ─── 3. CUSTOM UPLOADED SOUNDS ────────────────────────────────── */}
      <div className="rss-custom-section">
        <div className="rss-section-header-row">
          <div className="rss-section-title">Custom Ringtone Uploads</div>
          <button
            type="button"
            className="btn-upload-sound"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            <Upload size={13} /> {isUploading ? 'Uploading...' : 'Upload Audio (.mp3, .wav)'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/mp3,audio/wav,audio/ogg"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
          />
        </div>

        {uploadError && (
          <div className="rss-upload-error">
            <AlertCircle size={14} /> {uploadError}
          </div>
        )}

        {customSounds.length > 0 ? (
          <div className="rss-sound-grid">
            {customSounds.map((cs) => {
              const isSelected = settings.default_sound_id === cs.id;
              const isPlaying = playingSoundId === cs.id;

              return (
                <div
                  key={cs.id}
                  className={`rss-sound-card ${isSelected ? 'is-selected' : ''}`}
                  onClick={() => handleSelectSound(cs.id)}
                >
                  <div className="rss-card-top">
                    <button
                      type="button"
                      className={`btn-preview-audio ${isPlaying ? 'is-playing' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleTogglePreview(cs.id, cs.url);
                      }}
                    >
                      {isPlaying ? <Square size={13} fill="currentColor" /> : <Play size={13} fill="currentColor" />}
                    </button>
                    <div className="rss-sound-meta">
                      <span className="rss-sound-name">{cs.name}</span>
                      <span className="rss-sound-desc">Uploaded Audio File</span>
                    </div>
                  </div>
                  <div className="rss-card-bottom">
                    <button
                      type="button"
                      className="btn-delete-custom-sound"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteCustomSound(cs.id);
                      }}
                      title="Delete audio"
                    >
                      <Trash2 size={12} />
                    </button>
                    {isSelected && (
                      <span className="rss-selected-pill">
                        <Check size={11} /> Default
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="rss-empty-custom">
            No custom sounds uploaded yet. Supported formats: MP3, WAV, OGG (Max 5MB).
          </p>
        )}
      </div>

      {/* ─── 4. PER-DEVICE SOUND OVERRIDES ────────────────────────────── */}
      <div className="rss-overrides-section">
        <div className="rss-section-title">Per-Device Ringtone Routing</div>
        <p className="rss-desc">Assign distinct audio alerts across your authorized hardware devices.</p>

        <div className="rss-override-grid">
          <div className="rss-override-item">
            <div className="rss-device-label">
              <Laptop size={15} />
              <span>Windows Desktop (Host)</span>
            </div>
            <select
              value={settings.per_device_sounds.desktop_windows || settings.default_sound_id}
              onChange={(e) => handleDeviceSoundChange('desktop_windows', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
              {customSounds.map((cs) => (
                <option key={cs.id} value={cs.id}>
                  {cs.name} (Custom)
                </option>
              ))}
            </select>
          </div>

          <div className="rss-override-item">
            <div className="rss-device-label">
              <Smartphone size={15} />
              <span>Android Smartphone</span>
            </div>
            <select
              value={settings.per_device_sounds.android_phone || settings.default_sound_id}
              onChange={(e) => handleDeviceSoundChange('android_phone', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
              {customSounds.map((cs) => (
                <option key={cs.id} value={cs.id}>
                  {cs.name} (Custom)
                </option>
              ))}
            </select>
          </div>

          <div className="rss-override-item">
            <div className="rss-device-label">
              <Tablet size={15} />
              <span>iPad / iOS Tablet</span>
            </div>
            <select
              value={settings.per_device_sounds.ios_tablet || settings.default_sound_id}
              onChange={(e) => handleDeviceSoundChange('ios_tablet', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
              {customSounds.map((cs) => (
                <option key={cs.id} value={cs.id}>
                  {cs.name} (Custom)
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ─── 5. PER-EVENT SOUND OVERRIDES ────────────────────────────── */}
      <div className="rss-overrides-section">
        <div className="rss-section-title">Per-Event &amp; Severity Sound Overrides</div>
        <p className="rss-desc">Customize sound profiles depending on meeting importance or task urgency.</p>

        <div className="rss-override-grid">
          <div className="rss-override-item">
            <div className="rss-device-label">
              <span className="rss-event-dot meeting" />
              <span>Calendar &amp; Client Meetings</span>
            </div>
            <select
              value={settings.per_event_sounds.meeting || 'executive_tone'}
              onChange={(e) => handleEventSoundChange('meeting', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="rss-override-item">
            <div className="rss-device-label">
              <span className="rss-event-dot task" />
              <span>Task &amp; Todo Deadlines</span>
            </div>
            <select
              value={settings.per_event_sounds.task || 'soft_zen'}
              onChange={(e) => handleEventSoundChange('task', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="rss-override-item">
            <div className="rss-device-label">
              <span className="rss-event-dot urgent" />
              <span>High-Priority &amp; Urgent Alarms</span>
            </div>
            <select
              value={settings.per_event_sounds.urgent_reminder || 'urgent_alert'}
              onChange={(e) => handleEventSoundChange('urgent_reminder', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="rss-override-item">
            <div className="rss-device-label">
              <span className="rss-event-dot personal" />
              <span>Personal &amp; Routine Reminders</span>
            </div>
            <select
              value={settings.per_event_sounds.personal || 'crystal_chime'}
              onChange={(e) => handleEventSoundChange('personal', e.target.value)}
              className="rss-select"
            >
              {BUILTIN_SOUNDS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
};
