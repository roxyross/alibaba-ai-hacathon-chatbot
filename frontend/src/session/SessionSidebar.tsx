import React, { useState } from 'react';
import { useSessions, ChatSession } from './useSessions';
import './SessionSidebar.css';

export type AppView =
  | 'chat'
  | 'pricing'
  | 'image_studio'
  | 'knowledge_vault'
  | 'workspace_hub'
  | 'jobs'
  | 'finance'
  | 'usage'
  | 'billing'
  | 'payment_methods'
  | 'email'
  | 'voice'
  | 'documents'
  | 'calculator'
  | 'calendar';

interface SessionSidebarProps {
  activeSessionId: string | null;
  activeView?: AppView;
  mode?: 'chat' | 'task';
  onModeChange?: (mode: 'chat' | 'task') => void;
  onSelect: (session: ChatSession) => void;
  onNewChat: () => void;
  onNewTask?: () => void;
  onViewChange?: (view: AppView) => void;
  sessions?: ChatSession[];
  loading?: boolean;
  error?: string | null;
  onRename?: (id: string, title: string) => Promise<ChatSession>;
  onRemove?: (id: string) => Promise<void>;
  isCollapsed?: boolean;
  onCloseSidebar?: () => void;
  initialSearchQuery?: string;
}

export const SessionSidebar: React.FC<SessionSidebarProps> = ({
  activeSessionId,
  activeView = 'chat',
  mode = 'chat',
  onModeChange,
  onSelect,
  onNewChat,
  onNewTask,
  onViewChange,
  sessions: propSessions,
  loading: propLoading,
  error: propError,
  onRename: propRename,
  onRemove: propRemove,
  isCollapsed = false,
  onCloseSidebar,
  initialSearchQuery = '',
}) => {
  const localHook = useSessions();
  const sessions = propSessions !== undefined ? propSessions : localHook.sessions;
  const loading = propLoading !== undefined ? propLoading : localHook.loading;
  const error = propError !== undefined ? propError : localHook.error;
  const rename = propRename || localHook.rename;
  const remove = propRemove || localHook.remove;
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery);
  const [showMoreTools, setShowMoreTools] = useState(false);

  React.useEffect(() => {
    if (initialSearchQuery !== undefined) {
      setSearchQuery(initialSearchQuery);
    }
  }, [initialSearchQuery]);

  const filteredSessions = sessions.filter((s) => {
    const isTask = s.session_type === 'task' || s.title?.startsWith('[Task]') || s.model === 'code_generation';
    const matchesMode = mode === 'task' ? isTask : !isTask;
    if (!matchesMode) return false;
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (s.title && s.title.toLowerCase().includes(q)) ||
      (s.provider && s.provider.toLowerCase().includes(q)) ||
      (s.model && s.model.toLowerCase().includes(q))
    );
  });

  return (
    <aside
      className={`session-sidebar${isCollapsed ? ' session-sidebar--collapsed' : ''}`}
      aria-label="Sidebar navigation"
      aria-hidden={isCollapsed}
    >
      <div className="session-sidebar__header">
        {/* Header bar with title and Close Sidebar button */}
        <div className="session-sidebar__top-controls">
          <span className="session-sidebar__brand">Workspace</span>
          {onCloseSidebar && (
            <button
              type="button"
              className="session-sidebar__close-btn"
              onClick={onCloseSidebar}
              title="Close Sidebar"
              aria-label="Close Sidebar"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
              <span>Close</span>
            </button>
          )}
        </div>

        {/* Search Bar for previous conversations */}
        <div className="session-sidebar__search-box">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="search"
            className="session-sidebar__search-input"
            placeholder="Search history (⌘K)…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search conversations"
          />
          {searchQuery && (
            <button
              type="button"
              className="session-sidebar__search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Toggle between Chat and Task mode */}
        <div className="session-sidebar__mode-toggle" role="tablist" aria-label="Workflow mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'chat'}
            className={`session-sidebar__mode-btn${mode === 'chat' ? ' session-sidebar__mode-btn--active' : ''}`}
            onClick={() => {
              onModeChange?.('chat');
              if (activeView !== 'chat') onViewChange?.('chat');
            }}
          >
            <span>💬</span>
            <span>Chat</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'task'}
            className={`session-sidebar__mode-btn${mode === 'task' ? ' session-sidebar__mode-btn--active' : ''}`}
            onClick={() => {
              onModeChange?.('task');
              if (activeView !== 'chat') onViewChange?.('chat');
            }}
          >
            <span>⚡</span>
            <span>Task</span>
          </button>
        </div>

        {/* + New Chat Button: Executive Dark Minimalist */}
        <button
          type="button"
          className="session-sidebar__new"
          onClick={() => {
            if (mode === 'task') {
              (onNewTask || onNewChat)();
            } else {
              onNewChat();
            }
            if (onViewChange) onViewChange('chat');
          }}
        >
          <span className="session-sidebar__new-icon">+</span>
          <span>{mode === 'task' ? 'New Task' : 'New Chat'}</span>
        </button>
      </div>

      {/* Primary Modules Group */}
      {onViewChange && (
        <div className="session-sidebar__nav-group">
          <div className="session-sidebar__section-header">
            <span>Modules</span>
          </div>
          <nav className="session-sidebar__nav" aria-label="Core Modules">
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'chat' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('chat')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Chat &amp; Reasoning</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'image_studio' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('image_studio')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Image Studio</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'knowledge_vault' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('knowledge_vault')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Knowledge Vault</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'workspace_hub' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('workspace_hub')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Workspace Hub</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'jobs' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('jobs')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Scheduled Jobs</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'finance' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('finance')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Finances (Raast / Plaid)</span>
            </button>
          </nav>

          {/* Collapsible Utility Tools */}
          <div className="session-sidebar__more-toggle-row">
            <button
              type="button"
              className="session-sidebar__more-toggle"
              onClick={() => setShowMoreTools(!showMoreTools)}
            >
              <span>{showMoreTools ? '▾ Hide utilities' : '▸ Utilities (Voice, Docs…)'}</span>
            </button>
          </div>

          {showMoreTools && (
            <nav className="session-sidebar__nav session-sidebar__nav--secondary">
              <button
                type="button"
                className={`session-sidebar__nav-item${activeView === 'voice' ? ' session-sidebar__nav-item--active' : ''}`}
                onClick={() => onViewChange('voice')}
              >
                <span className="session-sidebar__nav-sub-dot" />
                <span className="session-sidebar__nav-label">Voice Mode</span>
              </button>
              <button
                type="button"
                className={`session-sidebar__nav-item${activeView === 'documents' ? ' session-sidebar__nav-item--active' : ''}`}
                onClick={() => onViewChange('documents')}
              >
                <span className="session-sidebar__nav-sub-dot" />
                <span className="session-sidebar__nav-label">Document Upload</span>
              </button>
              <button
                type="button"
                className={`session-sidebar__nav-item${activeView === 'email' ? ' session-sidebar__nav-item--active' : ''}`}
                onClick={() => onViewChange('email')}
              >
                <span className="session-sidebar__nav-sub-dot" />
                <span className="session-sidebar__nav-label">Email Send</span>
              </button>
              <button
                type="button"
                className={`session-sidebar__nav-item${activeView === 'calculator' ? ' session-sidebar__nav-item--active' : ''}`}
                onClick={() => onViewChange('calculator')}
              >
                <span className="session-sidebar__nav-sub-dot" />
                <span className="session-sidebar__nav-label">Calculator</span>
              </button>
              <button
                type="button"
                className={`session-sidebar__nav-item${activeView === 'calendar' ? ' session-sidebar__nav-item--active' : ''}`}
                onClick={() => onViewChange('calendar')}
              >
                <span className="session-sidebar__nav-sub-dot" />
                <span className="session-sidebar__nav-label">Calendar</span>
              </button>
            </nav>
          )}

          {/* Billing & Tier Quick Links */}
          <div className="session-sidebar__section-header session-sidebar__section-header--border">
            <span>Account</span>
          </div>
          <nav className="session-sidebar__nav">
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'usage' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('usage')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Usage &amp; Telemetry</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'billing' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('billing')}
            >
              <span className="session-sidebar__nav-dot" />
              <span className="session-sidebar__nav-label">Billing &amp; Invoices</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item session-sidebar__nav-item--upgrade${activeView === 'pricing' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('pricing')}
            >
              <span className="session-sidebar__nav-upgrade-badge">⚡</span>
              <span className="session-sidebar__nav-label">Upgrade Plans</span>
            </button>
          </nav>
        </div>
      )}

      {/* History section */}
      <div className="session-sidebar__section-header session-sidebar__section-header--border">
        <span>{mode === 'task' ? 'Coding Tasks' : 'Recent Chats'}</span>
      </div>

      {loading && (
        <p className="session-sidebar__status">Loading history…</p>
      )}
      {error && (
        <p className="session-sidebar__status session-sidebar__status--error">
          {error}
        </p>
      )}

      <ul className="session-sidebar__list">
        {filteredSessions.map((s) => {
          const isActive = s.id === activeSessionId;
          const isRenaming = renamingId === s.id;

          return (
            <li
              key={s.id}
              className={`session-sidebar__item${
                isActive ? ' session-sidebar__item--active' : ''
              }`}
            >
              {isRenaming ? (
                <form
                  className="session-sidebar__rename"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    if (!renameValue.trim()) return;
                    await rename(s.id, renameValue.trim());
                    setRenamingId(null);
                  }}
                  onBlur={async () => {
                    if (renameValue.trim()) {
                      await rename(s.id, renameValue.trim());
                    }
                    setRenamingId(null);
                  }}
                >
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    className="session-sidebar__rename-input"
                  />
                </form>
              ) : (
                <button
                  type="button"
                  className="session-sidebar__session-btn"
                  onClick={() => onSelect(s)}
                  title={s.title || 'Untitled conversation'}
                >
                  <span className="session-sidebar__session-title">
                    {s.title || 'Untitled conversation'}
                  </span>
                  <span className="session-sidebar__session-meta">
                    {s.model || s.provider}
                  </span>
                </button>
              )}

              <div className="session-sidebar__actions">
                <button
                  type="button"
                  className="session-sidebar__action-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setRenamingId(s.id);
                    setRenameValue(s.title || '');
                  }}
                  title="Rename conversation"
                  aria-label="Rename conversation"
                >
                  ✎
                </button>
                <button
                  type="button"
                  className="session-sidebar__action-btn session-sidebar__action-btn--delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm('Delete this conversation?')) {
                      void remove(s.id);
                    }
                  }}
                  title="Delete conversation"
                  aria-label="Delete conversation"
                >
                  ✕
                </button>
              </div>
            </li>
          );
        })}

        {filteredSessions.length === 0 && !loading && (
          <li className="session-sidebar__empty">
            No {mode === 'task' ? 'tasks' : 'conversations'} yet
          </li>
        )}
      </ul>
    </aside>
  );
};
