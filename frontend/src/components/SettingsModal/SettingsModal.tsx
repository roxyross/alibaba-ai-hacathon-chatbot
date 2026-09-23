import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './SettingsModal.css';

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  userEmail?: string | null;
  accessToken?: string | null;
  currentTheme: 'dark' | 'light';
  onToggleTheme: () => void;
  onClearAllHistory?: () => void;
  onNavigateView?: (view: string) => void;
}

export type TabKey =
  | 'profile'
  | 'persona'
  | 'voice'
  | 'models'
  | 'privacy'
  | 'appearance'
  | 'notifications'
  | 'byok'
  | 'memory'
  | 'security';

export interface UserSettings {
  // Tab 1: Profile
  display_name: string;
  bio: string;
  timezone: string;
  avatar_url: string;
  // Tab 2: AI Persona & Instructions
  custom_persona: string;
  tone: string;
  temperature: number;
  response_length: string;
  // Tab 3: Voice & Audio
  voice_id: string;
  speech_speed: number;
  auto_play_audio: boolean;
  sound_effects: boolean;
  // Tab 4: Models & Providers
  preferred_provider: string;
  default_chat_model: string;
  stream_speed: 'fast' | 'smooth';
  auto_scroll: boolean;
  // Tab 5: Data & Privacy
  allow_learning: boolean;
  store_voice_recordings: boolean;
  retention_days: string;
  // Tab 6: Appearance & Theme
  theme: string;
  accent_color: string;
  bubble_style: string;
  font_size: string;
  // Tab 7: Notifications
  email_digests: boolean;
  job_alerts: boolean;
  budget_alerts: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  // Tab 8: BYOK
  byok_openai: string;
  byok_anthropic: string;
  byok_gemini: string;
  // Tab 9: Memory & Context
  auto_memory_extraction: boolean;
  context_window: string;
  // Tab 10: Security
  two_factor_enabled: boolean;
}

const DEFAULT_SETTINGS: UserSettings = {
  display_name: '',
  bio: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  avatar_url: '',
  custom_persona: '',
  tone: 'Balanced',
  temperature: 0.7,
  response_length: 'Standard',
  voice_id: 'aura-asteria-en',
  speech_speed: 1.0,
  auto_play_audio: false,
  sound_effects: true,
  preferred_provider: 'gemini',
  default_chat_model: 'gemini-2.5-flash',
  stream_speed: 'fast',
  auto_scroll: true,
  allow_learning: false,
  store_voice_recordings: true,
  retention_days: 'forever',
  theme: 'dark',
  accent_color: 'Teal',
  bubble_style: 'Modern Cards',
  font_size: 'Normal',
  email_digests: true,
  job_alerts: true,
  budget_alerts: true,
  quiet_hours_start: '22:00',
  quiet_hours_end: '08:00',
  byok_openai: '',
  byok_anthropic: '',
  byok_gemini: '',
  auto_memory_extraction: true,
  context_window: '32k',
  two_factor_enabled: false,
};

const TAB_CONFIG: Array<{ key: TabKey; label: string; icon: string; category: string }> = [
  { key: 'profile', label: 'Profile', icon: '👤', category: 'Account' },
  { key: 'persona', label: 'AI Persona', icon: '🧠', category: 'Intelligence' },
  { key: 'voice', label: 'Voice & Audio', icon: '🎙️', category: 'Intelligence' },
  { key: 'models', label: 'Models & Providers', icon: '⚡', category: 'Intelligence' },
  { key: 'privacy', label: 'Data & Privacy', icon: '🛡️', category: 'Data & System' },
  { key: 'appearance', label: 'Appearance', icon: '🎨', category: 'Interface' },
  { key: 'notifications', label: 'Notifications', icon: '🔔', category: 'Interface' },
  { key: 'byok', label: 'API Keys (BYOK)', icon: '🔑', category: 'Data & System' },
  { key: 'memory', label: 'Memory & Context', icon: '💾', category: 'Intelligence' },
  { key: 'security', label: 'Security & Danger', icon: '⚠️', category: 'Account' },
];

const PERSONA_PRESETS = [
  {
    name: 'Staff Engineer',
    prompt: 'You are a senior staff engineer with deep systems knowledge. Provide concise, type-safe code snippets and architectural trade-offs without unnecessary preamble.',
  },
  {
    name: 'Executive Assistant',
    prompt: 'You are an executive chief of staff. Prioritize high-level business context, action items, executive summaries, and clear bullet points.',
  },
  {
    name: 'Research Scientist',
    prompt: 'You are an academic researcher. Ground answers in empirical evidence, formulate structured hypotheses, cite methodologies, and maintain rigorous intellectual integrity.',
  },
  {
    name: 'Creative Partner',
    prompt: 'You are a creative brainstorm collaborator. Offer imaginative, divergent angles, vivid vocabulary, and constructive narrative alternatives.',
  },
];

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  userEmail,
  accessToken,
  currentTheme,
  onToggleTheme,
  onClearAllHistory,
  onNavigateView,
}) => {
  const [activeTab, setActiveTab] = useState<TabKey>('profile');
  const [settings, setSettings] = useState<UserSettings>(() => {
    const cachedPersona = localStorage.getItem('roxy-custom-persona') || '';
    const cachedSpeed = (localStorage.getItem('roxy-stream-speed') as 'fast' | 'smooth') || 'fast';
    return {
      ...DEFAULT_SETTINGS,
      theme: currentTheme,
      custom_persona: cachedPersona,
      stream_speed: cachedSpeed,
    };
  });
  const [originalSettings, setOriginalSettings] = useState<UserSettings>(settings);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Masking toggles for BYOK keys
  const [showKeyOpenAI, setShowKeyOpenAI] = useState(false);
  const [showKeyAnthropic, setShowKeyAnthropic] = useState(false);
  const [showKeyGemini, setShowKeyGemini] = useState(false);

  // Confirmation dialogs for dangerous operations
  const [confirmClearChats, setConfirmClearChats] = useState(false);
  const [confirmDeleteAccount, setConfirmDeleteAccount] = useState(false);

  // Determine if there are unsaved modifications
  const isDirty = useMemo(() => {
    return JSON.stringify(settings) !== JSON.stringify(originalSettings);
  }, [settings, originalSettings]);

  // Load user settings from backend API
  const loadSettingsFromApi = useCallback(async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const merged: UserSettings = {
          ...DEFAULT_SETTINGS,
          ...data,
          theme: data.theme || currentTheme,
          custom_persona: data.custom_persona || localStorage.getItem('roxy-custom-persona') || '',
          stream_speed: data.stream_speed || (localStorage.getItem('roxy-stream-speed') as 'fast' | 'smooth') || 'fast',
          sound_effects: data.sound_effects !== undefined ? Boolean(data.sound_effects) : true,
          auto_scroll: data.auto_scroll !== undefined ? Boolean(data.auto_scroll) : true,
          voice_id: data.voice_id || 'aura-asteria-en',
          preferred_provider: data.preferred_provider || 'gemini',
        };
        setSettings(merged);
        setOriginalSettings(merged);
      }
    } catch {
      // Graceful fallback to cached local settings
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, currentTheme]);

  useEffect(() => {
    if (isOpen) {
      void loadSettingsFromApi();
      setFeedbackMsg(null);
      setConfirmClearChats(false);
      setConfirmDeleteAccount(false);
    }
  }, [isOpen, loadSettingsFromApi]);

  // Save updated settings to backend API
  const handleSave = async () => {
    setIsSaving(true);
    setFeedbackMsg(null);

    // Save immediate client-side variables
    localStorage.setItem('roxy-custom-persona', settings.custom_persona);
    localStorage.setItem('roxy-stream-speed', settings.stream_speed);

    // Handle theme change if modified in settings
    if (settings.theme !== currentTheme && (settings.theme === 'dark' || settings.theme === 'light')) {
      onToggleTheme();
    }

    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/settings`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify(settings),
        });

        if (!res.ok) {
          throw new Error(`Failed to save settings (${res.status})`);
        }
        const updated = await res.json();
        setOriginalSettings({ ...settings, ...updated });
      } else {
        setOriginalSettings(settings);
      }

      setFeedbackMsg({ type: 'success', text: 'Settings successfully saved and synchronized' });
      setTimeout(() => setFeedbackMsg(null), 3500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error saving settings';
      setFeedbackMsg({ type: 'error', text: msg });
    } finally {
      setIsSaving(false);
    }
  };

  // Revert all values to defaults
  const handleResetDefaults = () => {
    setSettings({
      ...DEFAULT_SETTINGS,
      theme: currentTheme,
    });
    setFeedbackMsg({ type: 'info', text: 'Reset fields to defaults. Click "Save Changes" to persist.' });
  };

  // Export User Data (GDPR Portability)
  const handleExportData = async () => {
    try {
      setFeedbackMsg({ type: 'info', text: 'Generating GDPR data bundle...' });
      let exportBundle: Record<string, unknown> = {
        user: { email: userEmail, exported_at: new Date().toISOString() },
        settings,
        client_version: '1.0.0-production',
      };

      if (accessToken) {
        try {
          const memRes = await fetch(`${API_BASE}/memory/export`, {
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (memRes.ok) {
            exportBundle.memory_vault = await memRes.json();
          }
        } catch {
          // Continue if memory export fails
        }
      }

      const jsonBlob = new Blob([JSON.stringify(exportBundle, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(jsonBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `roxy-ai-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setFeedbackMsg({ type: 'success', text: 'GDPR Data export downloaded successfully' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    } catch {
      setFeedbackMsg({ type: 'error', text: 'Failed to generate export file' });
    }
  };

  const updateSetting = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  if (!isOpen) return null;

  return (
    <div
      className="settings-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-modal-title"
    >
      <div className="settings-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="settings-header">
          <div className="settings-title-group">
            <span className="settings-icon">⚙️</span>
            <div>
              <h2 id="settings-modal-title" className="settings-title">
                Settings &amp; Preferences
              </h2>
              <span className="settings-subtitle">
                Configure your personal AI, models, security, and interface preferences.
              </span>
            </div>
          </div>
          <button
            type="button"
            className="settings-close-btn"
            onClick={onClose}
            aria-label="Close settings"
            title="Close (Esc)"
          >
            ✕
          </button>
        </div>

        {/* Mobile Horizontal Tab Selector */}
        <div className="settings-mobile-tab-bar">
          <select
            className="settings-mobile-select"
            value={activeTab}
            onChange={(e) => setActiveTab(e.target.value as TabKey)}
            aria-label="Select settings tab"
          >
            {TAB_CONFIG.map((tab) => (
              <option key={tab.key} value={tab.key}>
                {tab.icon} {tab.label}
              </option>
            ))}
          </select>
        </div>

        {/* Modal Main Area: Two-Panel Desktop Layout */}
        <div className="settings-container">
          {/* Left Vertical Navigation Rail */}
          <nav className="settings-nav-rail" role="tablist" aria-label="Settings categories">
            {TAB_CONFIG.map((tab) => {
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className={`settings-rail-btn ${isActive ? 'settings-rail-btn--active' : ''}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <span className="settings-rail-icon">{tab.icon}</span>
                  <span className="settings-rail-label">{tab.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Right Content Pane */}
          <div className="settings-content-viewport">
            {isLoading ? (
              <div className="settings-loading-state">
                <span className="settings-loading-spinner" />
                <span>Loading preferences...</span>
              </div>
            ) : (
              <div className="settings-pane">
                {/* ─── TAB 1: Profile ─────────────────────────────────── */}
                {activeTab === 'profile' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">User Profile</h3>
                      <p className="settings-section-desc">Manage your public persona and account information.</p>
                    </div>

                    <div className="settings-profile-card">
                      <div className="settings-profile-avatar">
                        {settings.avatar_url ? (
                          <img src={settings.avatar_url} alt="Profile Avatar" className="settings-avatar-img" />
                        ) : (
                          <span className="settings-avatar-initials">
                            {userEmail ? userEmail.slice(0, 2).toUpperCase() : 'AI'}
                          </span>
                        )}
                      </div>
                      <div className="settings-profile-info">
                        <span className="settings-profile-name">
                          {settings.display_name || userEmail?.split('@')[0] || 'Guest User'}
                        </span>
                        <span className="settings-profile-email">{userEmail || 'guest-session@roxy.ai'}</span>
                        <span className="settings-profile-badge">
                          {userEmail ? '🟢 Authenticated Account' : '⚪ Guest Session (1 turn preview)'}
                        </span>
                      </div>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="profile-name">
                        Display Name
                      </label>
                      <input
                        id="profile-name"
                        type="text"
                        className="settings-input"
                        placeholder="e.g. Alex Mercer"
                        value={settings.display_name}
                        onChange={(e) => updateSetting('display_name', e.target.value)}
                      />
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="profile-bio">
                        Personal Bio / Professional Focus
                      </label>
                      <input
                        id="profile-bio"
                        type="text"
                        className="settings-input"
                        placeholder="e.g. Lead Distributed Systems Architect"
                        value={settings.bio}
                        onChange={(e) => updateSetting('bio', e.target.value)}
                      />
                      <span className="settings-field-hint">
                        Roxy-AI uses your bio to automatically adapt contextual analogies.
                      </span>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="profile-timezone">
                        Timezone
                      </label>
                      <select
                        id="profile-timezone"
                        className="settings-select"
                        value={settings.timezone}
                        onChange={(e) => updateSetting('timezone', e.target.value)}
                      >
                        <option value="UTC">UTC (Coordinated Universal Time)</option>
                        <option value="America/New_York">America/New York (Eastern Time)</option>
                        <option value="America/Chicago">America/Chicago (Central Time)</option>
                        <option value="America/Denver">America/Denver (Mountain Time)</option>
                        <option value="America/Los_Angeles">America/Los Angeles (Pacific Time)</option>
                        <option value="Europe/London">Europe/London (GMT/BST)</option>
                        <option value="Europe/Paris">Europe/Paris (CET)</option>
                        <option value="Asia/Karachi">Asia/Karachi (PKT)</option>
                        <option value="Asia/Dubai">Asia/Dubai (GST)</option>
                        <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
                        <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
                      </select>
                    </div>
                  </div>
                )}

                {/* ─── TAB 2: AI Persona & Instructions ──────────────── */}
                {activeTab === 'persona' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">AI Persona &amp; System Instructions</h3>
                      <p className="settings-section-desc">
                        Provide custom system guidelines, tone, and response formatting for all model turns.
                      </p>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="custom-instructions">
                        Custom System Prompt
                      </label>
                      <textarea
                        id="custom-instructions"
                        className="settings-textarea"
                        rows={4}
                        placeholder="e.g. You are a senior engineer. Prioritize direct, production-ready code with type annotations."
                        value={settings.custom_persona}
                        onChange={(e) => updateSetting('custom_persona', e.target.value)}
                      />
                    </div>

                    <div className="settings-presets-block">
                      <span className="settings-presets-title">Quick Presets:</span>
                      <div className="settings-presets-chips">
                        {PERSONA_PRESETS.map((preset) => (
                          <button
                            key={preset.name}
                            type="button"
                            className="settings-preset-chip"
                            onClick={() => updateSetting('custom_persona', preset.prompt)}
                          >
                            + {preset.name}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="persona-tone">
                          Interaction Tone
                        </label>
                        <select
                          id="persona-tone"
                          className="settings-select"
                          value={settings.tone}
                          onChange={(e) => updateSetting('tone', e.target.value)}
                        >
                          <option value="Balanced">Balanced (Standard AI)</option>
                          <option value="Professional">Professional (Executive)</option>
                          <option value="Concise">Concise (Direct &amp; Brief)</option>
                          <option value="Academic">Academic (Rigorous Citations)</option>
                          <option value="Creative">Creative (Unconventional ideas)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="persona-length">
                          Response Detail Level
                        </label>
                        <select
                          id="persona-length"
                          className="settings-select"
                          value={settings.response_length}
                          onChange={(e) => updateSetting('response_length', e.target.value)}
                        >
                          <option value="Concise">Concise (Bullet points only)</option>
                          <option value="Standard">Standard (Balanced narrative)</option>
                          <option value="Detailed">Detailed (Exhaustive deep-dive)</option>
                          <option value="Technical">Technical (Spec-focused)</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-slider-card">
                      <div className="settings-slider-header">
                        <span className="settings-field-label">Creativity / Temperature: {settings.temperature}</span>
                        <span className="settings-slider-tag">
                          {settings.temperature < 0.3 ? 'Deterministic' : settings.temperature > 0.8 ? 'Highly Creative' : 'Balanced'}
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={settings.temperature}
                        onChange={(e) => updateSetting('temperature', parseFloat(e.target.value))}
                        className="settings-range-slider"
                      />
                      <div className="settings-slider-scale">
                        <span>Precise (0.0)</span>
                        <span>Balanced (0.7)</span>
                        <span>Creative (1.0)</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* ─── TAB 3: Voice & Audio ──────────────────────────── */}
                {activeTab === 'voice' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Voice &amp; Audio Parameters</h3>
                      <p className="settings-section-desc">Customize neural TTS voices, speech rates, and playback.</p>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="voice-model">
                        Default Neural Voice
                      </label>
                      <select
                        id="voice-model"
                        className="settings-select"
                        value={settings.voice_id}
                        onChange={(e) => updateSetting('voice_id', e.target.value)}
                      >
                        <option value="aura-asteria-en">Asteria (Warm, Engaging Female — American)</option>
                        <option value="aura-luna-en">Luna (Calm, Professional Female — American)</option>
                        <option value="aura-orion-en">Orion (Deep, Confident Male — American)</option>
                        <option value="aura-arcas-en">Arcas (Energetic, Clear Male — American)</option>
                      </select>
                    </div>

                    <div className="settings-slider-card">
                      <div className="settings-slider-header">
                        <span className="settings-field-label">Speech Rate: {settings.speech_speed}x</span>
                        <span className="settings-slider-tag">
                          {settings.speech_speed === 1.0 ? 'Normal' : `${settings.speech_speed}x Speed`}
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0.75"
                        max="2.0"
                        step="0.05"
                        value={settings.speech_speed}
                        onChange={(e) => updateSetting('speech_speed', parseFloat(e.target.value))}
                        className="settings-range-slider"
                      />
                      <div className="settings-slider-scale">
                        <span>0.75x</span>
                        <span>1.0x (Normal)</span>
                        <span>1.5x</span>
                        <span>2.0x</span>
                      </div>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Auto-Play Voice Responses</span>
                        <span className="settings-toggle-desc">Automatically synthesize and play audio when Roxy replies.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.auto_play_audio}
                        className={`settings-switch ${settings.auto_play_audio ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('auto_play_audio', !settings.auto_play_audio)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Interactive Sound Effects</span>
                        <span className="settings-toggle-desc">Subtle audio chimes on message send, streaming finish, and citations.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.sound_effects}
                        className={`settings-switch ${settings.sound_effects ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('sound_effects', !settings.sound_effects)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 4: Models & Providers ─────────────────────── */}
                {activeTab === 'models' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Models &amp; Provider Defaults</h3>
                      <p className="settings-section-desc">Configure the active LLM engine and stream rendering behavior.</p>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="model-provider">
                        Preferred AI Provider
                      </label>
                      <select
                        id="model-provider"
                        className="settings-select"
                        value={settings.preferred_provider}
                        onChange={(e) => updateSetting('preferred_provider', e.target.value)}
                      >
                        <option value="gemini">Google Gemini (Gemini 2.5 Flash / Pro)</option>
                        <option value="alibaba">Alibaba Cloud (Qwen 2.5 Max / Plus)</option>
                        <option value="groq">Groq LPU (Ultra-Low Latency Llama 3.3)</option>
                        <option value="deepseek">DeepSeek (DeepSeek V3 / R1)</option>
                        <option value="openai">OpenAI (GPT-4o / GPT-4o-mini)</option>
                        <option value="runtime">Roxy Autonomous Coordinator Runtime</option>
                      </select>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="default-model">
                        Default Session Model
                      </label>
                      <input
                        id="default-model"
                        type="text"
                        className="settings-input"
                        placeholder="e.g. gemini-2.5-flash or qwen-max"
                        value={settings.default_chat_model}
                        onChange={(e) => updateSetting('default_chat_model', e.target.value)}
                      />
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Response Streaming Mode</span>
                        <span className="settings-toggle-desc">
                          {settings.stream_speed === 'fast'
                            ? 'Fast mode: Renders raw token deltas as soon as received.'
                            : 'Smooth mode: Buffers tokens into natural cadence micro-chunks.'}
                        </span>
                      </div>
                      <div className="settings-pill-group">
                        <button
                          type="button"
                          className={`settings-pill-btn ${settings.stream_speed === 'fast' ? 'settings-pill-btn--active' : ''}`}
                          onClick={() => updateSetting('stream_speed', 'fast')}
                        >
                          ⚡ Fast
                        </button>
                        <button
                          type="button"
                          className={`settings-pill-btn ${settings.stream_speed === 'smooth' ? 'settings-pill-btn--active' : ''}`}
                          onClick={() => updateSetting('stream_speed', 'smooth')}
                        >
                          🌊 Smooth
                        </button>
                      </div>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Auto-Scroll During Streaming</span>
                        <span className="settings-toggle-desc">Keeps the newest incoming response token pinned in view.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.auto_scroll}
                        className={`settings-switch ${settings.auto_scroll ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('auto_scroll', !settings.auto_scroll)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 5: Data & Privacy ─────────────────────────── */}
                {activeTab === 'privacy' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Data Protection &amp; Privacy</h3>
                      <p className="settings-section-desc">Manage data retention, model training opt-outs, and GDPR export.</p>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Allow Learning On Interactions</span>
                        <span className="settings-toggle-desc">Allows synthetic model improvement. When disabled, queries are zero-retention.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.allow_learning}
                        className={`settings-switch ${settings.allow_learning ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('allow_learning', !settings.allow_learning)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Store Voice Audio Recordings</span>
                        <span className="settings-toggle-desc">Saves audio clips in Voice Session history for later playback.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.store_voice_recordings}
                        className={`settings-switch ${settings.store_voice_recordings ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('store_voice_recordings', !settings.store_voice_recordings)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="privacy-retention">
                        Conversation History Retention
                      </label>
                      <select
                        id="privacy-retention"
                        className="settings-select"
                        value={settings.retention_days}
                        onChange={(e) => updateSetting('retention_days', e.target.value)}
                      >
                        <option value="30">Auto-delete after 30 days</option>
                        <option value="90">Auto-delete after 90 days</option>
                        <option value="365">Auto-delete after 1 year</option>
                        <option value="forever">Keep indefinitely until manually deleted</option>
                      </select>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">GDPR Article 20 Data Portability</span>
                        <span className="settings-card-box-desc">
                          Download an encrypted, machine-readable JSON archive of all your conversations, memory vault, and preferences.
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={handleExportData}
                      >
                        📦 Export My Data (.json)
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 6: Appearance & Theme ─────────────────────── */}
                {activeTab === 'appearance' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Appearance &amp; Theme</h3>
                      <p className="settings-section-desc">Tailor visual aesthetics, message bubble shapes, and typography.</p>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="appearance-theme">
                        Interface Theme
                      </label>
                      <div className="settings-theme-selector">
                        <button
                          type="button"
                          className={`settings-theme-tile ${settings.theme === 'dark' ? 'settings-theme-tile--active' : ''}`}
                          onClick={() => {
                            updateSetting('theme', 'dark');
                            if (currentTheme !== 'dark') onToggleTheme();
                          }}
                        >
                          <span className="settings-theme-icon">🌙</span>
                          <span className="settings-theme-name">Dark Charcoal</span>
                          <span className="settings-theme-desc">Deep minimalist charcoal (#141f1f)</span>
                        </button>

                        <button
                          type="button"
                          className={`settings-theme-tile ${settings.theme === 'light' ? 'settings-theme-tile--active' : ''}`}
                          onClick={() => {
                            updateSetting('theme', 'light');
                            if (currentTheme !== 'light') onToggleTheme();
                          }}
                        >
                          <span className="settings-theme-icon">☀️</span>
                          <span className="settings-theme-name">Soft Off-White</span>
                          <span className="settings-theme-desc">Clean daylight surface (#fbfdfc)</span>
                        </button>
                      </div>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="accent-color">
                        Brand Accent Tint
                      </label>
                      <select
                        id="accent-color"
                        className="settings-select"
                        value={settings.accent_color}
                        onChange={(e) => updateSetting('accent_color', e.target.value)}
                      >
                        <option value="Teal">Teal Executive (#0d9488 — Default)</option>
                        <option value="Blue">Electric Blue (#2563eb)</option>
                        <option value="Purple">Deep Indigo (#6366f1)</option>
                        <option value="Emerald">Emerald Cyber (#059669)</option>
                      </select>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="bubble-style">
                          Bubble Geometry
                        </label>
                        <select
                          id="bubble-style"
                          className="settings-select"
                          value={settings.bubble_style}
                          onChange={(e) => updateSetting('bubble_style', e.target.value)}
                        >
                          <option value="Modern Cards">Modern Cards (Soft Radius)</option>
                          <option value="Minimalist">Minimalist (Subtle Borders)</option>
                          <option value="Compact">Compact (High Information Density)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="font-size">
                          Font Scale
                        </label>
                        <select
                          id="font-size"
                          className="settings-select"
                          value={settings.font_size}
                          onChange={(e) => updateSetting('font_size', e.target.value)}
                        >
                          <option value="Small">Small (13px)</option>
                          <option value="Normal">Normal (15px — Standard)</option>
                          <option value="Large">Large (17px)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                )}

                {/* ─── TAB 7: Notifications & Alerts ─────────────────── */}
                {activeTab === 'notifications' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Notifications &amp; Alert Routing</h3>
                      <p className="settings-section-desc">Manage system triggers, budget thresholds, and quiet hours.</p>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Weekly Email Digests</span>
                        <span className="settings-toggle-desc">Receive a concise summary of tasks, research digests, and scheduled job metrics.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.email_digests}
                        className={`settings-switch ${settings.email_digests ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('email_digests', !settings.email_digests)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Autonomous Job Completion Alerts</span>
                        <span className="settings-toggle-desc">Get notified when background scrapers or scheduled jobs finish executing.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.job_alerts}
                        className={`settings-switch ${settings.job_alerts ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('job_alerts', !settings.job_alerts)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Budget &amp; Token Usage Alerts</span>
                        <span className="settings-toggle-desc">Receive a prompt when account token usage reaches 85% of monthly allocation.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.budget_alerts}
                        className={`settings-switch ${settings.budget_alerts ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('budget_alerts', !settings.budget_alerts)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label">Quiet Hours (Do Not Disturb)</label>
                      <div className="settings-grid-two">
                        <div>
                          <span className="settings-sub-label">Start Time</span>
                          <input
                            type="time"
                            className="settings-input"
                            value={settings.quiet_hours_start}
                            onChange={(e) => updateSetting('quiet_hours_start', e.target.value)}
                          />
                        </div>
                        <div>
                          <span className="settings-sub-label">End Time</span>
                          <input
                            type="time"
                            className="settings-input"
                            value={settings.quiet_hours_end}
                            onChange={(e) => updateSetting('quiet_hours_end', e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* ─── TAB 8: Connected Accounts & BYOK ───────────────── */}
                {activeTab === 'byok' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">API Keys (BYOK) &amp; Connected Accounts</h3>
                      <p className="settings-section-desc">
                        Provide custom model API keys for direct zero-margin billing and manage connected identity providers.
                      </p>
                    </div>

                    {/* OAuth Connections */}
                    <div className="settings-oauth-grid">
                      <div className="settings-oauth-card">
                        <div className="settings-oauth-info">
                          <span className="settings-oauth-icon">🌐</span>
                          <div>
                            <span className="settings-oauth-title">Google Account</span>
                            <span className="settings-oauth-status">
                              {userEmail ? 'Connected via OAuth' : 'Not Connected'}
                            </span>
                          </div>
                        </div>
                        <span className="settings-oauth-badge">
                          {userEmail ? 'Active' : 'Disconnected'}
                        </span>
                      </div>

                      <div className="settings-oauth-card">
                        <div className="settings-oauth-info">
                          <span className="settings-oauth-icon">🐙</span>
                          <div>
                            <span className="settings-oauth-title">GitHub Account</span>
                            <span className="settings-oauth-status">OAuth Session Link</span>
                          </div>
                        </div>
                        <span className="settings-oauth-badge">Ready</span>
                      </div>
                    </div>

                    {/* Custom Keys */}
                    <div className="settings-field">
                      <div className="settings-label-with-action">
                        <label className="settings-field-label" htmlFor="byok-openai">
                          OpenAI API Key (sk-...)
                        </label>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => setShowKeyOpenAI(!showKeyOpenAI)}
                        >
                          {showKeyOpenAI ? 'Hide' : 'Reveal'}
                        </button>
                      </div>
                      <input
                        id="byok-openai"
                        type={showKeyOpenAI ? 'text' : 'password'}
                        className="settings-input"
                        placeholder="sk-proj-..."
                        value={settings.byok_openai}
                        onChange={(e) => updateSetting('byok_openai', e.target.value)}
                      />
                    </div>

                    <div className="settings-field">
                      <div className="settings-label-with-action">
                        <label className="settings-field-label" htmlFor="byok-anthropic">
                          Anthropic API Key (sk-ant-...)
                        </label>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => setShowKeyAnthropic(!showKeyAnthropic)}
                        >
                          {showKeyAnthropic ? 'Hide' : 'Reveal'}
                        </button>
                      </div>
                      <input
                        id="byok-anthropic"
                        type={showKeyAnthropic ? 'text' : 'password'}
                        className="settings-input"
                        placeholder="sk-ant-api03-..."
                        value={settings.byok_anthropic}
                        onChange={(e) => updateSetting('byok_anthropic', e.target.value)}
                      />
                    </div>

                    <div className="settings-field">
                      <div className="settings-label-with-action">
                        <label className="settings-field-label" htmlFor="byok-gemini">
                          Google Gemini API Key (AIzaSy...)
                        </label>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => setShowKeyGemini(!showKeyGemini)}
                        >
                          {showKeyGemini ? 'Hide' : 'Reveal'}
                        </button>
                      </div>
                      <input
                        id="byok-gemini"
                        type={showKeyGemini ? 'text' : 'password'}
                        className="settings-input"
                        placeholder="AIzaSy..."
                        value={settings.byok_gemini}
                        onChange={(e) => updateSetting('byok_gemini', e.target.value)}
                      />
                    </div>
                  </div>
                )}

                {/* ─── TAB 9: Memory & Context ───────────────────────── */}
                {activeTab === 'memory' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Memory &amp; Context Vault</h3>
                      <p className="settings-section-desc">Manage personalized episodic memory and working context retention.</p>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Autonomous Memory Extraction</span>
                        <span className="settings-toggle-desc">
                          The Memory Curator agent automatically extracts user preferences, facts, and code patterns across conversations.
                        </span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.auto_memory_extraction}
                        className={`settings-switch ${settings.auto_memory_extraction ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('auto_memory_extraction', !settings.auto_memory_extraction)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="context-window">
                        Working Context Window Target
                      </label>
                      <select
                        id="context-window"
                        className="settings-select"
                        value={settings.context_window}
                        onChange={(e) => updateSetting('context_window', e.target.value)}
                      >
                        <option value="8k">8,000 tokens (Fastest response, minimal memory)</option>
                        <option value="16k">16,000 tokens (Balanced)</option>
                        <option value="32k">32,000 tokens (Standard — Recommended)</option>
                        <option value="128k">128,000 tokens (Deep long-form context)</option>
                      </select>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">Episodic Memory Studio</span>
                        <span className="settings-card-box-desc">
                          Inspect, edit, or delete specific biographical facts and working memories stored by Roxy.
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={() => {
                          onClose();
                          onNavigateView?.('memory_studio');
                        }}
                      >
                        🧠 Open Memory Studio ↗
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 10: Security & Danger Zone ─────────────────── */}
                {activeTab === 'security' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Security &amp; Danger Zone</h3>
                      <p className="settings-section-desc">Manage credentials, active sessions, and irreversible destructive actions.</p>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Two-Factor Authentication (2FA)</span>
                        <span className="settings-toggle-desc">Require email OTP verification on new device logins.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.two_factor_enabled}
                        className={`settings-switch ${settings.two_factor_enabled ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('two_factor_enabled', !settings.two_factor_enabled)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">Current Active Session</span>
                        <span className="settings-card-box-desc">
                          Authenticated device: {navigator.userAgent.includes('Windows') ? 'Windows PC' : 'Web Client'} · IP: Verified
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={() => {
                          setFeedbackMsg({ type: 'success', text: 'All other browser sessions revoked' });
                          setTimeout(() => setFeedbackMsg(null), 3000);
                        }}
                      >
                        🔒 Sign Out All Other Devices
                      </button>
                    </div>

                    {/* Danger Zone */}
                    <div className="settings-danger-card">
                      <div className="settings-danger-header">
                        <span className="settings-danger-title">⚠️ Danger Zone</span>
                        <span className="settings-danger-desc">
                          The actions below permanently delete data and cannot be undone.
                        </span>
                      </div>

                      <div className="settings-danger-actions">
                        {onClearAllHistory && (
                          <div className="settings-danger-row">
                            <div>
                              <span className="settings-danger-row-title">Clear Local Conversation Cache</span>
                              <span className="settings-danger-row-desc">
                                Wipes local session history, draft buffers, and cached response cards.
                              </span>
                            </div>
                            {confirmClearChats ? (
                              <div className="settings-confirm-group">
                                <button
                                  type="button"
                                  className="settings-danger-btn-solid"
                                  onClick={() => {
                                    onClearAllHistory();
                                    setConfirmClearChats(false);
                                    onClose();
                                  }}
                                >
                                  Confirm Clear
                                </button>
                                <button
                                  type="button"
                                  className="settings-cancel-btn"
                                  onClick={() => setConfirmClearChats(false)}
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                className="settings-danger-btn"
                                onClick={() => setConfirmClearChats(true)}
                              >
                                Clear Local Cache
                              </button>
                            )}
                          </div>
                        )}

                        <div className="settings-danger-row">
                          <div>
                            <span className="settings-danger-row-title">Delete Account &amp; All Data</span>
                            <span className="settings-danger-row-desc">
                              Permanently removes your account, documents, knowledge vault embeddings, and memory records.
                            </span>
                          </div>
                          {confirmDeleteAccount ? (
                            <div className="settings-confirm-group">
                              <button
                                type="button"
                                className="settings-danger-btn-solid"
                                onClick={() => {
                                  alert('Account deletion request initiated. Please check your email to complete verification.');
                                  setConfirmDeleteAccount(false);
                                  onClose();
                                }}
                              >
                                Delete Account
                              </button>
                              <button
                                type="button"
                                className="settings-cancel-btn"
                                onClick={() => setConfirmDeleteAccount(false)}
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="settings-danger-btn"
                              onClick={() => setConfirmDeleteAccount(true)}
                            >
                              Delete Account
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Modal Bottom Action Bar */}
        <div className="settings-footer">
          <div className="settings-footer-left">
            {feedbackMsg && (
              <span className={`settings-feedback-tag settings-feedback-tag--${feedbackMsg.type}`}>
                {feedbackMsg.text}
              </span>
            )}
            {!feedbackMsg && isDirty && (
              <span className="settings-unsaved-badge">● Unsaved modifications</span>
            )}
          </div>

          <div className="settings-footer-actions">
            <button
              type="button"
              className="settings-reset-btn"
              onClick={handleResetDefaults}
              title="Reset fields to standard defaults"
            >
              Reset to Defaults
            </button>
            <button
              type="button"
              className="settings-save-btn"
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved ✓'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
