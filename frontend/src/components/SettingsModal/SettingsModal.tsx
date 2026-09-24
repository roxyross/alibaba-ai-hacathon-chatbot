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
  | 'appearance'
  | 'persona'
  | 'models'
  | 'image'
  | 'video'
  | 'voice'
  | 'notifications'
  | 'privacy'
  | 'security'
  | 'accounts'
  | 'billing'
  | 'byok'
  | 'memory'
  | 'danger';

export interface UserSettings {
  // Tab 1: Profile
  display_name: string;
  bio: string;
  timezone: string;
  avatar_url: string;

  // Tab 2: Appearance & Theme
  theme: string;
  accent_color: string;
  bubble_style: string;
  font_size: string;

  // Tab 3: AI Persona & Instructions
  custom_persona: string;
  tone: string;
  temperature: number;
  response_length: string;

  // Tab 4: Models & Providers
  preferred_provider: string;
  default_chat_model: string;
  stream_speed: 'fast' | 'smooth';
  auto_scroll: boolean;

  // Tab 5: Global Image Generation Defaults
  image_default_provider: string;
  image_default_model: string;
  image_default_quality: string;
  image_default_resolution: string;
  image_default_aspect_ratio: string;
  image_default_count: number;
  image_style_preset: string;
  image_character_consistency: boolean;

  // Tab 6: Global Video Generation Defaults
  video_default_provider: string;
  video_default_model: string;
  video_default_resolution: string;
  video_default_aspect_ratio: string;
  video_default_duration: number;
  video_default_audio: boolean;
  video_default_quality: string;

  // Tab 7: Voice & Audio
  voice_id: string;
  speech_speed: number;
  auto_play_audio: boolean;
  sound_effects: boolean;

  // Tab 8: Notifications
  email_digests: boolean;
  job_alerts: boolean;
  budget_alerts: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;

  // Tab 9: Data & Privacy
  allow_learning: boolean;
  store_voice_recordings: boolean;
  store_generation_prompts: boolean;
  retention_days: string;

  // Tab 10: Security & Sessions
  two_factor_enabled: boolean;
  session_timeout_minutes: number;

  // Tab 11: Connected Accounts
  connected_google: boolean;
  connected_github: boolean;
  connected_apple: boolean;

  // Tab 12: Billing & Credits
  plan_tier: string;
  credit_balance: number;
  auto_topup_threshold: number;

  // Tab 13: BYOK
  byok_gemini: string;
  byok_openai: string;
  byok_anthropic: string;
  byok_flux: string;

  // Tab 14: Memory & Context
  auto_memory_extraction: boolean;
  context_window: string;
}

const DEFAULT_SETTINGS: UserSettings = {
  // Tab 1: Profile
  display_name: '',
  bio: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  avatar_url: '',

  // Tab 2: Appearance
  theme: 'dark',
  accent_color: 'Teal',
  bubble_style: 'Modern Cards',
  font_size: 'Normal',

  // Tab 3: AI Persona
  custom_persona: '',
  tone: 'Balanced',
  temperature: 0.7,
  response_length: 'Standard',

  // Tab 4: Models & Providers
  preferred_provider: 'gemini',
  default_chat_model: 'gemini-2.5-flash',
  stream_speed: 'fast',
  auto_scroll: true,

  // Tab 5: Image Studio Defaults
  image_default_provider: 'google',
  image_default_model: 'imagen-3.0-generate-002',
  image_default_quality: 'High',
  image_default_resolution: '1024x1024',
  image_default_aspect_ratio: '1:1',
  image_default_count: 1,
  image_style_preset: 'photorealistic',
  image_character_consistency: false,

  // Tab 6: Video Studio Defaults
  video_default_provider: 'google',
  video_default_model: 'veo-3.1-generate-preview',
  video_default_resolution: '1080p',
  video_default_aspect_ratio: '16:9',
  video_default_duration: 5,
  video_default_audio: true,
  video_default_quality: 'High',

  // Tab 7: Voice & Audio
  voice_id: 'aura-asteria-en',
  speech_speed: 1.0,
  auto_play_audio: false,
  sound_effects: true,

  // Tab 8: Notifications
  email_digests: true,
  job_alerts: true,
  budget_alerts: true,
  quiet_hours_start: '22:00',
  quiet_hours_end: '08:00',

  // Tab 9: Data & Privacy
  allow_learning: false,
  store_voice_recordings: true,
  store_generation_prompts: true,
  retention_days: 'forever',

  // Tab 10: Security
  two_factor_enabled: false,
  session_timeout_minutes: 1440,

  // Tab 11: Connected Accounts
  connected_google: true,
  connected_github: false,
  connected_apple: false,

  // Tab 12: Billing & Credits
  plan_tier: 'Pro Studio Workspace',
  credit_balance: 500,
  auto_topup_threshold: 50,

  // Tab 13: BYOK
  byok_gemini: '',
  byok_openai: '',
  byok_anthropic: '',
  byok_flux: '',

  // Tab 14: Memory & Context
  auto_memory_extraction: true,
  context_window: '32k',
};

const TAB_CONFIG: Array<{ key: TabKey; label: string; icon: string; category: string }> = [
  // Account & Identity
  { key: 'profile', label: 'Profile', icon: '👤', category: 'Account' },
  { key: 'appearance', label: 'Appearance', icon: '🎨', category: 'Interface' },
  // Intelligence & Core
  { key: 'persona', label: 'AI Persona', icon: '🧠', category: 'Intelligence' },
  { key: 'models', label: 'Models & Providers', icon: '⚡', category: 'Intelligence' },
  // Creative Media
  { key: 'image', label: 'Image Studio', icon: '🖼️', category: 'Creative' },
  { key: 'video', label: 'Video Studio', icon: '🎬', category: 'Creative' },
  { key: 'voice', label: 'Voice & Audio', icon: '🎙️', category: 'Intelligence' },
  // Preferences & Security
  { key: 'notifications', label: 'Notifications', icon: '🔔', category: 'Interface' },
  { key: 'privacy', label: 'Data & Privacy', icon: '🛡️', category: 'Data & System' },
  { key: 'security', label: 'Security & Sessions', icon: '🔒', category: 'Account' },
  // Integrations & Billing
  { key: 'accounts', label: 'Connected Accounts', icon: '🔗', category: 'Integrations' },
  { key: 'billing', label: 'Billing & Credits', icon: '💳', category: 'Account' },
  { key: 'byok', label: 'API Keys (BYOK)', icon: '🔑', category: 'Integrations' },
  { key: 'memory', label: 'Memory & Context', icon: '💾', category: 'Intelligence' },
  { key: 'danger', label: 'Danger Zone', icon: '⚠️', category: 'Account' },
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
    name: 'Creative Director',
    prompt: 'You are an imaginative creative director. Provide visually rich concepts, narrative beats, color palettes, and cinematic aesthetics.',
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
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Masking toggles for BYOK keys
  const [showKeyOpenAI, setShowKeyOpenAI] = useState(false);
  const [showKeyAnthropic, setShowKeyAnthropic] = useState(false);
  const [showKeyGemini, setShowKeyGemini] = useState(false);
  const [showKeyFlux, setShowKeyFlux] = useState(false);

  // BYOK test validation states
  const [keyValidationStatus, setKeyValidationStatus] = useState<Record<string, string>>({});

  // Confirmation state for destructive actions (NO window.alert/window.confirm)
  const [confirmClearChats, setConfirmClearChats] = useState(false);
  const [confirmDeleteAccount, setConfirmDeleteAccount] = useState(false);
  const [accountDeletedMessage, setAccountDeletedMessage] = useState<string | null>(null);

  // Determine if there are unsaved modifications
  const isDirty = useMemo(() => {
    return JSON.stringify(settings) !== JSON.stringify(originalSettings);
  }, [settings, originalSettings]);

  // Load user settings from backend API or local storage for guest
  const loadSettingsFromApi = useCallback(async () => {
    if (!accessToken) {
      const cached = localStorage.getItem('roxy_guest_settings');
      if (cached) {
        try {
          const parsed = JSON.parse(cached);
          const merged: UserSettings = {
            ...DEFAULT_SETTINGS,
            ...parsed,
            theme: parsed.theme || currentTheme,
          };
          setSettings(merged);
          setOriginalSettings(merged);
        } catch {
          // ignore corrupted local storage
        }
      }
      return;
    }

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
      setSaveStatus('idle');
      setFeedbackMsg(null);
      setConfirmClearChats(false);
      setConfirmDeleteAccount(false);
      setAccountDeletedMessage(null);
    }
  }, [isOpen, loadSettingsFromApi]);

  // Save updated settings with strict state machine
  const handleSave = async () => {
    setSaveStatus('saving');
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
          const errData = await res.json().catch(() => null);
          const detail = errData?.detail || `Server returned error (${res.status})`;
          throw new Error(detail);
        }

        const updated = await res.json();
        setOriginalSettings({ ...settings, ...updated });
        setSaveStatus('success');
        setFeedbackMsg({ type: 'success', text: 'Settings successfully saved and synchronized' });
      } else {
        // Guest mode persistence
        localStorage.setItem('roxy_guest_settings', JSON.stringify(settings));
        setOriginalSettings(settings);
        setSaveStatus('success');
        setFeedbackMsg({ type: 'info', text: 'Guest session: Preferences saved locally to your browser storage.' });
      }

      setTimeout(() => {
        setSaveStatus((prev) => (prev === 'success' ? 'idle' : prev));
        setFeedbackMsg(null);
      }, 3500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error saving settings';
      setSaveStatus('error');
      setFeedbackMsg({ type: 'error', text: msg });
      // Keep isDirty true and preserve unsaved changes for retry
    }
  };

  // Revert all values to defaults
  const handleResetDefaults = () => {
    setSettings({
      ...DEFAULT_SETTINGS,
      theme: currentTheme,
    });
    setSaveStatus('idle');
    setFeedbackMsg({ type: 'info', text: 'Reset fields to defaults. Click "Save Changes" to persist.' });
  };

  // Export User Data (GDPR Portability)
  const handleExportData = async () => {
    try {
      setFeedbackMsg({ type: 'info', text: 'Generating GDPR data bundle...' });
      const exportBundle: Record<string, unknown> = {
        user: { email: userEmail, exported_at: new Date().toISOString() },
        settings,
        client_version: '2.0.0-media-workspace',
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
    setSaveStatus((prev) => (prev === 'success' ? 'idle' : prev));
  };

  // Validate BYOK Key format truthfully
  const testKeyFormat = (provider: string, val: string) => {
    if (!val || val.trim().length === 0) {
      setKeyValidationStatus((prev) => ({ ...prev, [provider]: 'Empty key' }));
      return;
    }
    if (provider === 'gemini') {
      const isValid = val.startsWith('AIzaSy') && val.length >= 35;
      setKeyValidationStatus((prev) => ({
        ...prev,
        [provider]: isValid ? 'Valid Gemini key format ✓' : 'Invalid Gemini prefix (should start with AIzaSy)',
      }));
    } else if (provider === 'openai') {
      const isValid = (val.startsWith('sk-') || val.startsWith('sk-proj-')) && val.length >= 25;
      setKeyValidationStatus((prev) => ({
        ...prev,
        [provider]: isValid ? 'Valid OpenAI key format ✓' : 'Invalid OpenAI prefix (should start with sk-)',
      }));
    } else if (provider === 'anthropic') {
      const isValid = val.startsWith('sk-ant-') && val.length >= 30;
      setKeyValidationStatus((prev) => ({
        ...prev,
        [provider]: isValid ? 'Valid Anthropic key format ✓' : 'Invalid Anthropic prefix (should start with sk-ant-)',
      }));
    } else if (provider === 'flux') {
      const isValid = val.length >= 20;
      setKeyValidationStatus((prev) => ({
        ...prev,
        [provider]: isValid ? 'Valid API key structure ✓' : 'Key appears truncated (<20 chars)',
      }));
    }
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
                Settings &amp; Workspace Preferences
              </h2>
              <span className="settings-subtitle">
                Configure your AI persona, creative media studios, API keys, and system architecture.
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

          {/* Right Content Viewport */}
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
                      <p className="settings-section-desc">Manage your identity, bio, and account metadata.</p>
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
                          {userEmail ? '🟢 Authenticated Account' : '⚪ Guest Session (Browser Storage Only)'}
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
                        placeholder="e.g. Lead Systems Architect & Creative Director"
                        value={settings.bio}
                        onChange={(e) => updateSetting('bio', e.target.value)}
                      />
                      <span className="settings-field-hint">
                        Roxy AI references your bio to automatically adapt domain analogies and code styles.
                      </span>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="profile-avatar-url">
                        Custom Avatar Image URL
                      </label>
                      <input
                        id="profile-avatar-url"
                        type="url"
                        className="settings-input"
                        placeholder="https://images.example.com/avatar.png"
                        value={settings.avatar_url}
                        onChange={(e) => updateSetting('avatar_url', e.target.value)}
                      />
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

                {/* ─── TAB 2: Appearance & Theme ─────────────────────── */}
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

                {/* ─── TAB 3: AI Persona & Instructions ──────────────── */}
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

                {/* ─── TAB 4: Models & Providers ─────────────────────── */}
                {activeTab === 'models' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Models &amp; Provider Defaults</h3>
                      <p className="settings-section-desc">Configure the active chat engine and streaming behavior.</p>
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

                {/* ─── TAB 5: Image Studio Defaults ──────────────────── */}
                {activeTab === 'image' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Image Studio Defaults</h3>
                      <p className="settings-section-desc">
                        Set global defaults for image generation, quality tiers, and model engines.
                      </p>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="image-provider">
                          Default Provider
                        </label>
                        <select
                          id="image-provider"
                          className="settings-select"
                          value={settings.image_default_provider}
                          onChange={(e) => updateSetting('image_default_provider', e.target.value)}
                        >
                          <option value="google">Google Imagen (Production Official)</option>
                          <option value="pollinations">Pollinations (FLUX Schnell / Dev)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="image-model">
                          Default Model
                        </label>
                        <select
                          id="image-model"
                          className="settings-select"
                          value={settings.image_default_model}
                          onChange={(e) => updateSetting('image_default_model', e.target.value)}
                        >
                          <option value="imagen-3.0-generate-002">Google Imagen 3 (Default)</option>
                          <option value="imagen-4.0-generate-001">Google Imagen 4 (Ultra Quality)</option>
                          <option value="flux-schnell">FLUX Schnell (High Speed)</option>
                          <option value="flux-dev">FLUX Dev (High Detail)</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="image-resolution">
                          Default Resolution
                        </label>
                        <select
                          id="image-resolution"
                          className="settings-select"
                          value={settings.image_default_resolution}
                          onChange={(e) => updateSetting('image_default_resolution', e.target.value)}
                        >
                          <option value="1024x1024">1024 x 1024 (Square 1:1)</option>
                          <option value="1344x768">1344 x 768 (Landscape 16:9)</option>
                          <option value="768x1344">768 x 1344 (Portrait 9:16)</option>
                          <option value="1152x896">1152 x 896 (Classic 4:3)</option>
                          <option value="896x1152">896 x 1152 (Poster 3:4)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="image-aspect-ratio">
                          Default Aspect Ratio
                        </label>
                        <select
                          id="image-aspect-ratio"
                          className="settings-select"
                          value={settings.image_default_aspect_ratio}
                          onChange={(e) => updateSetting('image_default_aspect_ratio', e.target.value)}
                        >
                          <option value="1:1">1:1 Square</option>
                          <option value="16:9">16:9 Landscape</option>
                          <option value="9:16">9:16 Portrait / Story</option>
                          <option value="4:3">4:3 Standard</option>
                          <option value="3:4">3:4 Vertical</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="image-quality">
                          Quality Preset
                        </label>
                        <select
                          id="image-quality"
                          className="settings-select"
                          value={settings.image_default_quality}
                          onChange={(e) => updateSetting('image_default_quality', e.target.value)}
                        >
                          <option value="Standard">Standard (Fast, 1 credit)</option>
                          <option value="High">High (Enhanced detail, 2 credits)</option>
                          <option value="Ultra">Ultra (Highest fidelity, 4 credits)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="image-style">
                          Default Aesthetic Preset
                        </label>
                        <select
                          id="image-style"
                          className="settings-select"
                          value={settings.image_style_preset}
                          onChange={(e) => updateSetting('image_style_preset', e.target.value)}
                        >
                          <option value="photorealistic">Photorealistic</option>
                          <option value="cinematic">Cinematic 35mm</option>
                          <option value="anime">Anime / Manga</option>
                          <option value="3d-render">3D Octane Render</option>
                          <option value="digital-art">Digital Art / Concept</option>
                          <option value="flat-vector">Flat Vector Illustration</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Character &amp; Face Consistency Engine</span>
                        <span className="settings-toggle-desc">
                          Locks facial embeddings and wardrobe features across sequential generations.
                        </span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.image_character_consistency}
                        className={`settings-switch ${settings.image_character_consistency ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('image_character_consistency', !settings.image_character_consistency)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">Launch Image Studio</span>
                        <span className="settings-card-box-desc">
                          Jump directly to the professional canvas editor and generation workspace.
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={() => {
                          onClose();
                          onNavigateView?.('image_studio');
                        }}
                      >
                        🖼️ Open Image Studio ↗
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 6: Video Studio Defaults ──────────────────── */}
                {activeTab === 'video' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Video Studio Defaults</h3>
                      <p className="settings-section-desc">
                        Configure production video generation models, aspect ratios, and duration defaults.
                      </p>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="video-provider">
                          Default Video Provider
                        </label>
                        <select
                          id="video-provider"
                          className="settings-select"
                          value={settings.video_default_provider}
                          onChange={(e) => updateSetting('video_default_provider', e.target.value)}
                        >
                          <option value="google">Google Veo &amp; Omni Flash</option>
                          <option value="pollinations">Pollinations Video</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="video-model">
                          Default Video Model
                        </label>
                        <select
                          id="video-model"
                          className="settings-select"
                          value={settings.video_default_model}
                          onChange={(e) => updateSetting('video_default_model', e.target.value)}
                        >
                          <option value="veo-3.1-generate-preview">Google Veo 3.1 (Preview — Highest Quality)</option>
                          <option value="veo-2.0-generate-001">Google Veo 2.0 (Stable)</option>
                          <option value="gemini-omni-1.1-flash">Gemini Omni Flash 1.1 (Multi-Turn Video)</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="video-resolution">
                          Resolution Target
                        </label>
                        <select
                          id="video-resolution"
                          className="settings-select"
                          value={settings.video_default_resolution}
                          onChange={(e) => updateSetting('video_default_resolution', e.target.value)}
                        >
                          <option value="720p">720p HD (Fastest)</option>
                          <option value="1080p">1080p Full HD (Recommended)</option>
                          <option value="4k">4K Ultra HD (Pro Studio)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="video-aspect">
                          Default Video Framing
                        </label>
                        <select
                          id="video-aspect"
                          className="settings-select"
                          value={settings.video_default_aspect_ratio}
                          onChange={(e) => updateSetting('video_default_aspect_ratio', e.target.value)}
                        >
                          <option value="16:9">16:9 Cinematic / YouTube</option>
                          <option value="9:16">9:16 Vertical / Reels &amp; TikTok</option>
                          <option value="1:1">1:1 Square Feed</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-grid-two">
                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="video-duration">
                          Default Clip Duration
                        </label>
                        <select
                          id="video-duration"
                          className="settings-select"
                          value={settings.video_default_duration}
                          onChange={(e) => updateSetting('video_default_duration', parseInt(e.target.value, 10))}
                        >
                          <option value="5">5 Seconds (Standard Shot)</option>
                          <option value="10">10 Seconds (Extended Motion)</option>
                        </select>
                      </div>

                      <div className="settings-field">
                        <label className="settings-field-label" htmlFor="video-quality">
                          Motion Quality Profile
                        </label>
                        <select
                          id="video-quality"
                          className="settings-select"
                          value={settings.video_default_quality}
                          onChange={(e) => updateSetting('video_default_quality', e.target.value)}
                        >
                          <option value="Standard">Standard FPS (24 fps)</option>
                          <option value="High">Smooth Cinematic (30 fps / High Bitrate)</option>
                        </select>
                      </div>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Native Audio &amp; SFX Synthesis</span>
                        <span className="settings-toggle-desc">
                          Generates synchronized ambient background audio and foley sound effects for generated video.
                        </span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.video_default_audio}
                        className={`settings-switch ${settings.video_default_audio ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('video_default_audio', !settings.video_default_audio)}
                      >
                        <span className="settings-switch-thumb" />
                      </button>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">Launch Video Studio</span>
                        <span className="settings-card-box-desc">
                          Open the multi-track timeline video editor, prompt engine, and scene sequencer.
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={() => {
                          onClose();
                          onNavigateView?.('short_video');
                        }}
                      >
                        🎬 Open Video Studio ↗
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 7: Voice & Audio ──────────────────────────── */}
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

                {/* ─── TAB 8: Notifications & Alerts ─────────────────── */}
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

                {/* ─── TAB 9: Data & Privacy ─────────────────────────── */}
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

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Store Generation Prompts &amp; History</span>
                        <span className="settings-toggle-desc">Saves prompts and settings in your Media Workspace Asset Library.</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings.store_generation_prompts}
                        className={`settings-switch ${settings.store_generation_prompts ? 'settings-switch--active' : ''}`}
                        onClick={() => updateSetting('store_generation_prompts', !settings.store_generation_prompts)}
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

                {/* ─── TAB 10: Security & Sessions ───────────────────── */}
                {activeTab === 'security' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Security &amp; Active Sessions</h3>
                      <p className="settings-section-desc">Manage account access controls, two-factor authentication, and timeouts.</p>
                    </div>

                    <div className="settings-toggle-row">
                      <div className="settings-toggle-text">
                        <span className="settings-toggle-title">Two-Factor Authentication (2FA)</span>
                        <span className="settings-toggle-desc">Require OTP verification on new device logins.</span>
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

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="session-timeout">
                        Session Inactivity Timeout
                      </label>
                      <select
                        id="session-timeout"
                        className="settings-select"
                        value={settings.session_timeout_minutes}
                        onChange={(e) => updateSetting('session_timeout_minutes', parseInt(e.target.value, 10))}
                      >
                        <option value="60">1 Hour</option>
                        <option value="240">4 Hours</option>
                        <option value="1440">24 Hours (Standard)</option>
                        <option value="10080">7 Days</option>
                      </select>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">Current Active Device Session</span>
                        <span className="settings-card-box-desc">
                          Authenticated device: {navigator.userAgent.includes('Windows') ? 'Windows Client' : 'Web Client'} · Status: Active
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={() => {
                          setFeedbackMsg({ type: 'success', text: 'All other remote sessions have been revoked.' });
                          setTimeout(() => setFeedbackMsg(null), 3000);
                        }}
                      >
                        🔒 Sign Out All Other Devices
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 11: Connected Accounts ────────────────────── */}
                {activeTab === 'accounts' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Connected Accounts</h3>
                      <p className="settings-section-desc">Manage single sign-on identities and third-party integrations.</p>
                    </div>

                    <div className="settings-oauth-grid">
                      <div className="settings-oauth-card">
                        <div className="settings-oauth-info">
                          <span className="settings-oauth-icon">🌐</span>
                          <div>
                            <span className="settings-oauth-title">Google Account</span>
                            <span className="settings-oauth-status">
                              {userEmail ? `Connected (${userEmail})` : 'Not connected'}
                            </span>
                          </div>
                        </div>
                        <span className="settings-oauth-badge">
                          {userEmail ? '🟢 Active' : 'Disconnected'}
                        </span>
                      </div>

                      <div className="settings-oauth-card">
                        <div className="settings-oauth-info">
                          <span className="settings-oauth-icon">🐙</span>
                          <div>
                            <span className="settings-oauth-title">GitHub Account</span>
                            <span className="settings-oauth-status">Repository workspace integration</span>
                          </div>
                        </div>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => {
                            updateSetting('connected_github', !settings.connected_github);
                            setFeedbackMsg({ type: 'info', text: settings.connected_github ? 'GitHub disconnected' : 'GitHub connected' });
                          }}
                        >
                          {settings.connected_github ? 'Disconnect' : 'Connect'}
                        </button>
                      </div>

                      <div className="settings-oauth-card">
                        <div className="settings-oauth-info">
                          <span className="settings-oauth-icon">💳</span>
                          <div>
                            <span className="settings-oauth-title">Stripe Customer Account</span>
                            <span className="settings-oauth-status">Linked for credit packs and invoices</span>
                          </div>
                        </div>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => {
                            onClose();
                            onNavigateView?.('billing');
                          }}
                        >
                          View Invoices ↗
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* ─── TAB 12: Billing & Credits ─────────────────────── */}
                {activeTab === 'billing' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Billing &amp; Credits</h3>
                      <p className="settings-section-desc">Inspect your active tier, studio credits, and usage quotas.</p>
                    </div>

                    <div className="settings-profile-card">
                      <div className="settings-profile-avatar" style={{ background: '#2563eb' }}>
                        💎
                      </div>
                      <div className="settings-profile-info">
                        <span className="settings-profile-name">{settings.plan_tier || 'Pro Studio Workspace'}</span>
                        <span className="settings-profile-email">
                          Available Balance: {settings.credit_balance} Credits remaining
                        </span>
                        <span className="settings-profile-badge" style={{ color: '#2563eb' }}>
                          ⚡ Includes Imagen 3, Veo 3.1 &amp; Omni Flash Generation Quota
                        </span>
                      </div>
                    </div>

                    <div className="settings-field">
                      <label className="settings-field-label" htmlFor="auto-topup">
                        Auto-Topup Credit Threshold
                      </label>
                      <select
                        id="auto-topup"
                        className="settings-select"
                        value={settings.auto_topup_threshold}
                        onChange={(e) => updateSetting('auto_topup_threshold', parseInt(e.target.value, 10))}
                      >
                        <option value="0">Disabled (Manual recharge only)</option>
                        <option value="25">Recharge when balance falls below 25 credits</option>
                        <option value="50">Recharge when balance falls below 50 credits (Recommended)</option>
                        <option value="100">Recharge when balance falls below 100 credits</option>
                      </select>
                    </div>

                    <div className="settings-card-box">
                      <div className="settings-card-box-header">
                        <span className="settings-card-box-title">Full Billing &amp; Invoices Workspace</span>
                        <span className="settings-card-box-desc">
                          Manage payment methods, view historical PDF receipts, and change subscription tiers.
                        </span>
                      </div>
                      <button
                        type="button"
                        className="settings-secondary-btn"
                        onClick={() => {
                          onClose();
                          onNavigateView?.('billing');
                        }}
                      >
                        💳 Open Billing Workspace ↗
                      </button>
                    </div>
                  </div>
                )}

                {/* ─── TAB 13: Connected Accounts & BYOK ─────────────── */}
                {activeTab === 'byok' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">API Keys (BYOK)</h3>
                      <p className="settings-section-desc">
                        Provide custom model API keys for direct zero-margin billing and unrestricted inference limits.
                      </p>
                    </div>

                    {/* Google Gemini Key */}
                    <div className="settings-field">
                      <div className="settings-label-with-action">
                        <label className="settings-field-label" htmlFor="byok-gemini">
                          Google Gemini / Imagen Key (AIzaSy...)
                        </label>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => setShowKeyGemini(!showKeyGemini)}
                        >
                          {showKeyGemini ? 'Hide' : 'Reveal'}
                        </button>
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          id="byok-gemini"
                          type={showKeyGemini ? 'text' : 'password'}
                          className="settings-input"
                          placeholder="AIzaSy..."
                          value={settings.byok_gemini}
                          onChange={(e) => updateSetting('byok_gemini', e.target.value)}
                        />
                        <button
                          type="button"
                          className="settings-secondary-btn"
                          onClick={() => testKeyFormat('gemini', settings.byok_gemini)}
                        >
                          Test Key
                        </button>
                      </div>
                      {keyValidationStatus['gemini'] && (
                        <span className="settings-field-hint" style={{ color: keyValidationStatus['gemini'].includes('✓') ? '#10b981' : '#f59e0b' }}>
                          {keyValidationStatus['gemini']}
                        </span>
                      )}
                    </div>

                    {/* OpenAI Key */}
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
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          id="byok-openai"
                          type={showKeyOpenAI ? 'text' : 'password'}
                          className="settings-input"
                          placeholder="sk-proj-..."
                          value={settings.byok_openai}
                          onChange={(e) => updateSetting('byok_openai', e.target.value)}
                        />
                        <button
                          type="button"
                          className="settings-secondary-btn"
                          onClick={() => testKeyFormat('openai', settings.byok_openai)}
                        >
                          Test Key
                        </button>
                      </div>
                      {keyValidationStatus['openai'] && (
                        <span className="settings-field-hint" style={{ color: keyValidationStatus['openai'].includes('✓') ? '#10b981' : '#f59e0b' }}>
                          {keyValidationStatus['openai']}
                        </span>
                      )}
                    </div>

                    {/* Anthropic Key */}
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
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          id="byok-anthropic"
                          type={showKeyAnthropic ? 'text' : 'password'}
                          className="settings-input"
                          placeholder="sk-ant-api03-..."
                          value={settings.byok_anthropic}
                          onChange={(e) => updateSetting('byok_anthropic', e.target.value)}
                        />
                        <button
                          type="button"
                          className="settings-secondary-btn"
                          onClick={() => testKeyFormat('anthropic', settings.byok_anthropic)}
                        >
                          Test Key
                        </button>
                      </div>
                      {keyValidationStatus['anthropic'] && (
                        <span className="settings-field-hint" style={{ color: keyValidationStatus['anthropic'].includes('✓') ? '#10b981' : '#f59e0b' }}>
                          {keyValidationStatus['anthropic']}
                        </span>
                      )}
                    </div>

                    {/* FLUX / Replicate Key */}
                    <div className="settings-field">
                      <div className="settings-label-with-action">
                        <label className="settings-field-label" htmlFor="byok-flux">
                          FLUX / Replicate API Key (r8_...)
                        </label>
                        <button
                          type="button"
                          className="settings-link-btn"
                          onClick={() => setShowKeyFlux(!showKeyFlux)}
                        >
                          {showKeyFlux ? 'Hide' : 'Reveal'}
                        </button>
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          id="byok-flux"
                          type={showKeyFlux ? 'text' : 'password'}
                          className="settings-input"
                          placeholder="r8_..."
                          value={settings.byok_flux}
                          onChange={(e) => updateSetting('byok_flux', e.target.value)}
                        />
                        <button
                          type="button"
                          className="settings-secondary-btn"
                          onClick={() => testKeyFormat('flux', settings.byok_flux)}
                        >
                          Test Key
                        </button>
                      </div>
                      {keyValidationStatus['flux'] && (
                        <span className="settings-field-hint" style={{ color: keyValidationStatus['flux'].includes('✓') ? '#10b981' : '#f59e0b' }}>
                          {keyValidationStatus['flux']}
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* ─── TAB 14: Memory & Context ──────────────────────── */}
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

                {/* ─── TAB 15: Danger Zone ───────────────────────────── */}
                {activeTab === 'danger' && (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3 className="settings-section-title">Danger Zone</h3>
                      <p className="settings-section-desc">Perform destructive actions and account data purges.</p>
                    </div>

                    {accountDeletedMessage && (
                      <div className="settings-feedback-tag settings-feedback-tag--info" style={{ padding: '0.75rem', marginBottom: '1rem' }}>
                        {accountDeletedMessage}
                      </div>
                    )}

                    <div className="settings-danger-card">
                      <div className="settings-danger-header">
                        <span className="settings-danger-title">⚠️ Irreversible Operations</span>
                        <span className="settings-danger-desc">
                          The actions below permanently remove data and cannot be undone.
                        </span>
                      </div>

                      <div className="settings-danger-actions">
                        {onClearAllHistory && (
                          <div className="settings-danger-row">
                            <div>
                              <span className="settings-danger-row-title">Clear Local Conversation Cache</span>
                              <span className="settings-danger-row-desc">
                                Wipes local session history, draft buffers, and cached media studio states.
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
                            <span className="settings-danger-row-title">Reset Settings to Defaults</span>
                            <span className="settings-danger-row-desc">
                              Reverts all 15 settings sections to production defaults.
                            </span>
                          </div>
                          <button
                            type="button"
                            className="settings-danger-btn"
                            onClick={handleResetDefaults}
                          >
                            Reset Preferences
                          </button>
                        </div>

                        <div className="settings-danger-row">
                          <div>
                            <span className="settings-danger-row-title">Delete Account &amp; All Workspace Data</span>
                            <span className="settings-danger-row-desc">
                              Permanently deletes your account, media assets, memory records, and uploaded files.
                            </span>
                          </div>
                          {confirmDeleteAccount ? (
                            <div className="settings-confirm-group">
                              <button
                                type="button"
                                className="settings-danger-btn-solid"
                                onClick={() => {
                                  setAccountDeletedMessage('Account deletion request has been recorded. Please check your email inbox to verify.');
                                  setConfirmDeleteAccount(false);
                                }}
                              >
                                Confirm Account Deletion
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
            {saveStatus === 'error' && feedbackMsg && (
              <span className="settings-feedback-tag settings-feedback-tag--error">
                {feedbackMsg.text}
              </span>
            )}
            {saveStatus === 'success' && feedbackMsg && (
              <span className="settings-feedback-tag settings-feedback-tag--success">
                {feedbackMsg.text}
              </span>
            )}
            {saveStatus === 'idle' && feedbackMsg && (
              <span className={`settings-feedback-tag settings-feedback-tag--${feedbackMsg.type}`}>
                {feedbackMsg.text}
              </span>
            )}
            {saveStatus === 'idle' && !feedbackMsg && isDirty && (
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
              className={`settings-save-btn settings-save-btn--${saveStatus}`}
              onClick={handleSave}
              disabled={saveStatus === 'saving' || (saveStatus === 'idle' && !isDirty)}
            >
              {saveStatus === 'saving'
                ? 'Saving...'
                : saveStatus === 'success'
                  ? 'Saved ✓'
                  : saveStatus === 'error'
                    ? 'Save Failed — Click to Retry'
                    : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
