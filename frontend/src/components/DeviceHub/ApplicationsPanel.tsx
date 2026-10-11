import React, { useState, useMemo } from 'react';
import {
  Layers,
  Search,
  RefreshCw,
  Play,
  Square,
  Maximize2,
  Terminal,
  Zap,
  Layout,
  X,
} from 'lucide-react';
import type { DeviceInfo, DiscoveredAppItem, WorkspaceSurfaceSession } from './DeviceHub';

export interface ApplicationsPanelProps {
  device: DeviceInfo | null;
  apps: DiscoveredAppItem[];
  workspaceSessions: WorkspaceSurfaceSession[];
  loadingApps: boolean;
  scanningApps: boolean;
  actingAppId: string | null;
  onScanApps: (forceRefresh?: boolean) => Promise<void>;
  onLaunchApp: (app: DiscoveredAppItem) => Promise<void>;
  onCloseApp: (app: DiscoveredAppItem, force?: boolean) => Promise<void>;
  onFocusApp: (app: DiscoveredAppItem) => Promise<void>;
  onCreateEmbedSession: (appIdOrUrl: string, mode?: string) => Promise<void>;
  onTerminateEmbedSession: (sessionId: string) => Promise<void>;
  onTriggerResilientExec: (app: DiscoveredAppItem) => void;
}

export const ApplicationsPanel: React.FC<ApplicationsPanelProps> = ({
  device,
  apps,
  workspaceSessions,
  loadingApps,
  scanningApps,
  actingAppId,
  onScanApps,
  onLaunchApp,
  onCloseApp,
  onFocusApp,
  onCreateEmbedSession,
  onTerminateEmbedSession,
  onTriggerResilientExec,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [runningOnly, setRunningOnly] = useState(false);
  const [showEmbedModal, setShowEmbedModal] = useState(false);
  const [customEmbedUrl, setCustomEmbedUrl] = useState('https://app.slack.com');
  const [embedMode, setEmbedMode] = useState('safe_iframe');
  const [creatingEmbed, setCreatingEmbed] = useState(false);

  const categories = [
    'all',
    'browser',
    'development',
    'productivity',
    'media',
    'utilities',
    'system',
    'mobile',
  ];

  const filteredApps = useMemo(() => {
    return apps.filter((app) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        q === '' ||
        app.app_name.toLowerCase().includes(q) ||
        app.executable_path.toLowerCase().includes(q) ||
        app.category.toLowerCase().includes(q);

      const matchesCat =
        selectedCategory === 'all' ||
        app.category.toLowerCase() === selectedCategory.toLowerCase();

      const matchesRunning = !runningOnly || app.is_running;

      return matchesSearch && matchesCat && matchesRunning;
    });
  }, [apps, searchQuery, selectedCategory, runningOnly]);

  const handleLaunchEmbed = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customEmbedUrl.trim()) return;
    setCreatingEmbed(true);
    try {
      await onCreateEmbedSession(customEmbedUrl.trim(), embedMode);
      setShowEmbedModal(false);
    } finally {
      setCreatingEmbed(false);
    }
  };

  const getRouteBadges = (app: DiscoveredAppItem) => {
    const isBrowser = app.category === 'browser' || app.app_name.toLowerCase().includes('chrome') || app.app_name.toLowerCase().includes('edge');
    const isDev = app.category === 'development' || app.app_name.toLowerCase().includes('code') || app.app_name.toLowerCase().includes('terminal');

    return (
      <div className="app-card__routes-row">
        <span className="app-card__route-badge app-card__route-badge--desktop" title="Native OS GUI / Process Automation">
          Desktop Route
        </span>
        {isBrowser && (
          <span className="app-card__route-badge app-card__route-badge--browser" title="Direct Web / DOM Tree Automation">
            Browser Route
          </span>
        )}
        {(isDev || isBrowser) && (
          <span className="app-card__route-badge app-card__route-badge--api" title="REST API / Background Protocol">
            API Route
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="apps-panel">
      {/* 1. Header & Controls */}
      <div className="apps-panel__controls-bar">
        <div className="apps-panel__search-box">
          <Search size={16} className="apps-panel__search-icon" />
          <input
            type="text"
            className="apps-panel__search-input"
            placeholder={`Search ${apps.length} applications on ${device?.device_name || 'host'}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="apps-panel__filter-group">
          <label className="apps-panel__toggle-label">
            <input
              type="checkbox"
              checked={runningOnly}
              onChange={(e) => setRunningOnly(e.target.checked)}
            />
            <span>Running Processes Only</span>
          </label>

          <button
            type="button"
            className="apps-panel__btn apps-panel__btn--secondary"
            onClick={() => setShowEmbedModal(true)}
            title="Open Workspace Embedding Session (Phase 16)"
          >
            <Layout size={14} />
            <span>Workspace Embed</span>
            {workspaceSessions.length > 0 && (
              <span className="apps-panel__session-count-badge">
                {workspaceSessions.length}
              </span>
            )}
          </button>

          <button
            type="button"
            className="apps-panel__btn apps-panel__btn--primary"
            onClick={() => onScanApps(false)}
            disabled={scanningApps}
            title="Run Deep Application Scanner on Host OS"
          >
            <RefreshCw size={14} className={scanningApps ? 'spin' : ''} />
            <span>{scanningApps ? 'Scanning Host OS...' : 'Scan Installed Apps'}</span>
          </button>
        </div>
      </div>

      {/* 2. Category Filter Chips */}
      <div className="apps-panel__categories">
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            className={`apps-panel__cat-chip ${
              selectedCategory === cat ? 'apps-panel__cat-chip--active' : ''
            }`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </button>
        ))}
        <span className="apps-panel__count-indicator">
          Showing {filteredApps.length} of {apps.length}
        </span>
      </div>

      {/* 3. Active Workspace Embedding Sessions (Phase 16) */}
      {workspaceSessions.length > 0 && (
        <div className="apps-panel__sessions-card">
          <div className="apps-panel__sessions-header">
            <div className="apps-panel__sessions-title">
              <Layout size={16} className="apps-panel__sessions-icon" />
              <span>In-Roxy Workspace Active Surfaces (Phase 16)</span>
            </div>
            <span className="apps-panel__sessions-tag">
              {workspaceSessions.length} Embedded Session{workspaceSessions.length > 1 ? 's' : ''}
            </span>
          </div>
          <div className="apps-panel__sessions-list">
            {workspaceSessions.map((s) => (
              <div key={s.session_id} className="apps-panel__session-item">
                <div className="apps-panel__session-info">
                  <span className="apps-panel__session-id">ID: {s.session_id.slice(0, 10)}...</span>
                  <span className="apps-panel__session-url">{s.target_url || s.app_id || 'Embedded Surface'}</span>
                  <span className="apps-panel__session-mode">{s.embedding_mode}</span>
                </div>
                <button
                  type="button"
                  className="apps-panel__session-close"
                  onClick={() => onTerminateEmbedSession(s.session_id)}
                  title="Close Workspace Surface"
                >
                  <X size={14} />
                  <span>Terminate</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. Applications Grid */}
      {loadingApps ? (
        <div className="apps-panel__loading-box">
          <RefreshCw size={26} className="spin" />
          <span>Cataloging installed applications from operating system...</span>
        </div>
      ) : filteredApps.length === 0 ? (
        <div className="apps-panel__empty-box">
          <Layers size={40} />
          <h3>No Applications Match Query</h3>
          <p>
            Try adjusting your search criteria, clearing the category filter, or clicking "Scan Installed
            Apps" to discover local software.
          </p>
          <button
            type="button"
            className="apps-panel__btn apps-panel__btn--primary"
            onClick={() => onScanApps(true)}
          >
            Run Force Discovery Scan
          </button>
        </div>
      ) : (
        <div className="apps-panel__grid">
          {filteredApps.map((app) => {
            const isActing = actingAppId === app.id;

            return (
              <div
                key={app.id}
                className={`app-card ${app.is_running ? 'app-card--running' : ''}`}
              >
                {/* Header */}
                <div className="app-card__header">
                  <div className="app-card__icon-wrap">
                    {app.icon_url ? (
                      <img
                        src={app.icon_url}
                        alt={app.app_name}
                        className="app-card__icon-img"
                      />
                    ) : (
                      <Terminal size={20} className="app-card__fallback-icon" />
                    )}
                  </div>
                  <div className="app-card__title-area">
                    <div className="app-card__name-row">
                      <span className="app-card__name" title={app.app_name}>
                        {app.app_name}
                      </span>
                      {app.is_running && (
                        <span className="app-card__badge app-card__badge--running">
                          RUNNING
                        </span>
                      )}
                    </div>
                    <span className="app-card__badge app-card__badge--cat">
                      {app.category}
                    </span>
                  </div>
                </div>

                {/* Body Details */}
                <div className="app-card__body">
                  <p className="app-card__path" title={app.executable_path}>
                    {app.executable_path}
                  </p>
                  <div className="app-card__meta-row">
                    <span>Launches: {app.launch_count}</span>
                    {app.process_id && <span>PID: {app.process_id}</span>}
                  </div>
                  {getRouteBadges(app)}
                </div>

                {/* Footer Controls */}
                <div className="app-card__footer">
                  {app.is_running ? (
                    <>
                      <button
                        type="button"
                        className="app-card__btn app-card__btn--focus"
                        onClick={() => onFocusApp(app)}
                        disabled={isActing}
                        title="Bring application window to front"
                      >
                        <Maximize2 size={13} />
                        <span>Focus</span>
                      </button>
                      <button
                        type="button"
                        className="app-card__btn app-card__btn--close"
                        onClick={() => onCloseApp(app, false)}
                        disabled={isActing}
                        title="Terminate process"
                      >
                        <Square size={13} />
                        <span>Close</span>
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="app-card__btn app-card__btn--launch"
                      onClick={() => onLaunchApp(app)}
                      disabled={isActing}
                      title="Launch application process"
                    >
                      <Play size={13} />
                      <span>Launch</span>
                    </button>
                  )}

                  {/* Resilient Execution Trigger (Phase 18) */}
                  <button
                    type="button"
                    className="app-card__btn app-card__btn--resilient"
                    onClick={() => onTriggerResilientExec(app)}
                    title="Execute action with multi-tier fallback (API -> Browser -> Desktop)"
                  >
                    <Zap size={13} />
                    <span>Resilient Exec</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 5. Workspace Embedding Modal (Phase 16) */}
      {showEmbedModal && (
        <div className="apps-panel__modal-backdrop" onClick={() => setShowEmbedModal(false)}>
          <div
            className="apps-panel__modal-window"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="embed-modal-title"
          >
            <div className="apps-panel__modal-header">
              <div className="apps-panel__modal-title-wrap">
                <Layout size={20} className="apps-panel__modal-icon" />
                <h2 id="embed-modal-title">In-Roxy Workspace Embedding (Phase 16)</h2>
              </div>
              <button
                type="button"
                className="apps-panel__modal-close"
                onClick={() => setShowEmbedModal(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleLaunchEmbed} className="apps-panel__modal-body">
              <p className="apps-panel__modal-intro">
                Project native web applications, remote surfaces, or headless browser sessions
                directly into an isolated sandboxed workspace iframe inside Roxy.
              </p>

              <div className="apps-panel__form-group">
                <label>Target Web App URL or App Identifier</label>
                <input
                  type="text"
                  required
                  placeholder="https://example.com or app:slack"
                  value={customEmbedUrl}
                  onChange={(e) => setCustomEmbedUrl(e.target.value)}
                  className="apps-panel__input"
                />
              </div>

              <div className="apps-panel__form-group">
                <label>Embedding Sandbox Mode</label>
                <select
                  value={embedMode}
                  onChange={(e) => setEmbedMode(e.target.value)}
                  className="apps-panel__select"
                >
                  <option value="safe_iframe">Safe Sandboxed IFrame (Header Rewriting)</option>
                  <option value="remote_surface">Remote Desktop Surface Projection</option>
                  <option value="headless_browser">Headless Automation Window</option>
                </select>
              </div>

              <div className="apps-panel__modal-actions">
                <button
                  type="button"
                  className="apps-panel__btn apps-panel__btn--secondary"
                  onClick={() => setShowEmbedModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="apps-panel__btn apps-panel__btn--primary"
                  disabled={creatingEmbed}
                >
                  {creatingEmbed ? 'Initiating Session...' : 'Create Embedded Surface'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
