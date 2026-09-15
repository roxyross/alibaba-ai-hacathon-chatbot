import React, { useState } from 'react';
import './SettingsModal.css';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  userEmail?: string | null;
  currentTheme: 'dark' | 'light';
  onToggleTheme: () => void;
  onClearAllHistory?: () => void;
}

type TabKey = 'general' | 'reasoning' | 'profile' | 'shortcuts';

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  userEmail,
  currentTheme,
  onToggleTheme,
  onClearAllHistory,
}) => {
  const [activeTab, setActiveTab] = useState<TabKey>('general');
  const [customPersona, setCustomPersona] = useState<string>(() => {
    return localStorage.getItem('roxy-custom-persona') || '';
  });
  const [streamSpeed, setStreamSpeed] = useState<'fast' | 'smooth'>(() => {
    return (localStorage.getItem('roxy-stream-speed') as 'fast' | 'smooth') || 'fast';
  });
  const [savedSuccess, setSavedSuccess] = useState(false);

  if (!isOpen) return null;

  const handleSavePersona = () => {
    localStorage.setItem('roxy-custom-persona', customPersona);
    localStorage.setItem('roxy-stream-speed', streamSpeed);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  return (
    <div className="settings-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div className="settings-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="settings-header">
          <div className="settings-title-group">
            <span className="settings-icon">⚙️</span>
            <h2 id="settings-title" className="settings-title">Settings &amp; Preferences</h2>
          </div>
          <button type="button" className="settings-close-btn" onClick={onClose} aria-label="Close settings">
            ✕
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="settings-nav" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'general'}
            className={`settings-tab-btn ${activeTab === 'general' ? 'settings-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            General
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'reasoning'}
            className={`settings-tab-btn ${activeTab === 'reasoning' ? 'settings-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('reasoning')}
          >
            AI &amp; Reasoning
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'profile'}
            className={`settings-tab-btn ${activeTab === 'profile' ? 'settings-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            Profile &amp; Cache
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'shortcuts'}
            className={`settings-tab-btn ${activeTab === 'shortcuts' ? 'settings-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('shortcuts')}
          >
            Shortcuts
          </button>
        </div>

        {/* Content Body */}
        <div className="settings-body">
          {activeTab === 'general' && (
            <div className="settings-pane">
              <div className="settings-row">
                <div className="settings-row-text">
                  <span className="settings-row-title">Appearance Theme</span>
                  <span className="settings-row-desc">Switch between soft off-white and dark interface.</span>
                </div>
                <button type="button" className="settings-toggle-btn" onClick={onToggleTheme}>
                  {currentTheme === 'dark' ? '🌙 Dark Mode' : '☀️ Light Mode (Soft Off-White)'}
                </button>
              </div>

              <div className="settings-row">
                <div className="settings-row-text">
                  <span className="settings-row-title">Response Streaming Mode</span>
                  <span className="settings-row-desc">Controls how rapidly tokens render on screen.</span>
                </div>
                <div className="settings-pill-group">
                  <button
                    type="button"
                    className={`settings-pill-btn ${streamSpeed === 'fast' ? 'settings-pill-btn--active' : ''}`}
                    onClick={() => setStreamSpeed('fast')}
                  >
                    ⚡ Fast (Token-by-token)
                  </button>
                  <button
                    type="button"
                    className={`settings-pill-btn ${streamSpeed === 'smooth' ? 'settings-pill-btn--active' : ''}`}
                    onClick={() => setStreamSpeed('smooth')}
                  >
                    🌊 Smooth (Buffered)
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'reasoning' && (
            <div className="settings-pane">
              <div className="settings-field">
                <label className="settings-field-label" htmlFor="custom-instructions">
                  Custom AI Persona &amp; Instructions
                </label>
                <span className="settings-field-desc">
                  Provide custom instructions for tone, style, or response formats across all models.
                </span>
                <textarea
                  id="custom-instructions"
                  className="settings-textarea"
                  rows={4}
                  placeholder="e.g. You are an expert technical lead. Provide direct, concise answers with type-safe code snippets."
                  value={customPersona}
                  onChange={(e) => setCustomPersona(e.target.value)}
                />
                <button type="button" className="settings-save-btn" onClick={handleSavePersona}>
                  {savedSuccess ? '✓ Saved Successfully' : 'Save Custom Instructions'}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'profile' && (
            <div className="settings-pane">
              <div className="settings-row">
                <div className="settings-row-text">
                  <span className="settings-row-title">Account Status</span>
                  <span className="settings-row-desc">
                    {userEmail ? `Signed in as ${userEmail}` : 'Browsing as Guest (1 free preview turn per session)'}
                  </span>
                </div>
                <span className="settings-status-badge">
                  {userEmail ? '🟢 Authenticated' : '⚪ Guest Session'}
                </span>
              </div>

              {onClearAllHistory && (
                <div className="settings-row">
                  <div className="settings-row-text">
                    <span className="settings-row-title">Clear Local Conversation Cache</span>
                    <span className="settings-row-desc">Remove all locally cached session threads and drafts.</span>
                  </div>
                  <button
                    type="button"
                    className="settings-danger-btn"
                    onClick={() => {
                      if (window.confirm('Are you sure you want to clear your local chat history?')) {
                        onClearAllHistory();
                        onClose();
                      }
                    }}
                  >
                    🗑️ Clear Cache
                  </button>
                </div>
              )}
            </div>
          )}

          {activeTab === 'shortcuts' && (
            <div className="settings-pane">
              <div className="settings-shortcuts-list">
                <div className="settings-shortcut-item">
                  <span className="settings-shortcut-desc">Open Sidebar Search</span>
                  <div className="settings-shortcut-keys">
                    <kbd>Ctrl</kbd> + <kbd>K</kbd> / <kbd>⌘</kbd> + <kbd>K</kbd>
                  </div>
                </div>

                <div className="settings-shortcut-item">
                  <span className="settings-shortcut-desc">Send Message</span>
                  <div className="settings-shortcut-keys">
                    <kbd>Enter</kbd>
                  </div>
                </div>

                <div className="settings-shortcut-item">
                  <span className="settings-shortcut-desc">New Line</span>
                  <div className="settings-shortcut-keys">
                    <kbd>Shift</kbd> + <kbd>Enter</kbd>
                  </div>
                </div>

                <div className="settings-shortcut-item">
                  <span className="settings-shortcut-desc">Indent Code</span>
                  <div className="settings-shortcut-keys">
                    <kbd>Tab</kbd>
                  </div>
                </div>

                <div className="settings-shortcut-item">
                  <span className="settings-shortcut-desc">Stop Generating (Interrupt Server)</span>
                  <div className="settings-shortcut-keys">
                    <kbd>Esc</kbd>
                  </div>
                </div>

                <div className="settings-shortcut-item">
                  <span className="settings-shortcut-desc">Voice Dictation Mode</span>
                  <div className="settings-shortcut-keys">
                    <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>D</kbd>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
