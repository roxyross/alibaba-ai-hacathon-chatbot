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

  // Sync initialSearchQuery if updated externally
  React.useEffect(() => {
    if (initialSearchQuery !== undefined) {
      setSearchQuery(initialSearchQuery);
    }
  }, [initialSearchQuery]);

  // Filter sessions strictly by selected mode and search query
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
      aria-label="Chat history"
      aria-hidden={isCollapsed}
    >
      <div className="session-sidebar__header">
        {/* Header bar with title and Close Sidebar button */}
        <div className="session-sidebar__top-controls">
          <span className="session-sidebar__brand">Conversations</span>
          {onCloseSidebar && (
            <button
              type="button"
              className="session-sidebar__close-btn"
              onClick={onCloseSidebar}
              title="Close Sidebar"
              aria-label="Close Sidebar"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
              <span>Close Sidebar</span>
            </button>
          )}
        </div>

        {/* Search Bar for previous conversations */}
        <div className="session-sidebar__search-box">
          <span className="session-sidebar__search-icon" aria-hidden="true">🔍</span>
          <input
            type="search"
            className="session-sidebar__search-input"
            placeholder="Search chats & messages…"
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
        {/* Toggle between New Chat and New Task */}
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
            💬 Chat
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
            ⚡ Task
          </button>
        </div>

        <button
          type="button"
          className={`session-sidebar__new${mode === 'task' ? ' session-sidebar__new--task' : ''}`}
          onClick={() => {
            if (mode === 'task') {
              (onNewTask || onNewChat)();
            } else {
              onNewChat();
            }
            if (onViewChange) onViewChange('chat');
          }}
        >
          {mode === 'task' ? '+ New task' : '+ New chat'}
        </button>

        {/* View navigation buttons moved under New Chat */}
        {onViewChange && (
          <nav className="session-sidebar__nav" aria-label="Modules">
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'chat' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('chat')}
            >
              <span className="session-sidebar__nav-icon">💬</span>
              <span className="session-sidebar__nav-label">Chat</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'image_studio' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('image_studio')}
            >
              <span className="session-sidebar__nav-icon">🎨</span>
              <span className="session-sidebar__nav-label">Image Studio</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'knowledge_vault' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('knowledge_vault')}
            >
              <span className="session-sidebar__nav-icon">📚</span>
              <span className="session-sidebar__nav-label">Knowledge Vault</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'workspace_hub' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('workspace_hub')}
            >
              <span className="session-sidebar__nav-icon">🗂️</span>
              <span className="session-sidebar__nav-label">Workspace Hub</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'jobs' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('jobs')}
            >
              <span className="session-sidebar__nav-icon">⏰</span>
              <span className="session-sidebar__nav-label">Scheduled Jobs</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'finance' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('finance')}
            >
              <span className="session-sidebar__nav-icon">💰</span>
              <span className="session-sidebar__nav-label">Finances</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'voice' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('voice')}
            >
              <span className="session-sidebar__nav-icon">🎙️</span>
              <span className="session-sidebar__nav-label">Voice Mode</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'usage' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('usage')}
            >
              <span className="session-sidebar__nav-icon">📊</span>
              <span className="session-sidebar__nav-label">Usage & Credits</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'billing' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('billing')}
            >
              <span className="session-sidebar__nav-icon">💳</span>
              <span className="session-sidebar__nav-label">Billing</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'pricing' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('pricing')}
            >
              <span className="session-sidebar__nav-icon">⚡</span>
              <span className="session-sidebar__nav-label">Upgrade Plans</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'email' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('email')}
            >
              <span className="session-sidebar__nav-icon">📧</span>
              <span className="session-sidebar__nav-label">Email Send</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'documents' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('documents')}
            >
              <span className="session-sidebar__nav-icon">📄</span>
              <span className="session-sidebar__nav-label">Documents</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'calculator' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('calculator')}
            >
              <span className="session-sidebar__nav-icon">🧮</span>
              <span className="session-sidebar__nav-label">Calculator</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-item${activeView === 'calendar' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('calendar')}
            >
              <span className="session-sidebar__nav-icon">📅</span>
              <span className="session-sidebar__nav-label">Calendar</span>
            </button>
          </nav>
        )}
      </div>

      <div className="session-sidebar__section-title">
        {mode === 'task' ? 'Coding Tasks' : 'Recent Chats'}
      </div>

      {loading && (
        <p className="session-sidebar__status">Loading…</p>
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
                  className="session-sidebar__select"
                  onClick={() => onSelect(s)}
                >
                  <span className="session-sidebar__title">
                    {s.title || (mode === 'task' ? 'Coding task' : 'New chat')}
                  </span>
                  <span className="session-sidebar__meta">
                    {s.provider} · {s.model}
                  </span>
                </button>
              )}
              <div className="session-sidebar__actions">
                {!isRenaming && (
                  <button
                    type="button"
                    className="session-sidebar__icon"
                    title="Rename"
                    aria-label="Rename session"
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenamingId(s.id);
                      setRenameValue(s.title || '');
                    }}
                  >
                    ✎
                  </button>
                )}
                <button
                  type="button"
                  className="session-sidebar__icon session-sidebar__icon--delete"
                  title="Delete session"
                  aria-label="Delete session"
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (isActive) {
                      onNewChat();
                    }
                    try {
                      await remove(s.id);
                    } catch (err) {
                      console.error('Failed to delete session:', err);
                    }
                  }}
                >
                  ✕
                </button>
              </div>
            </li>
          );
        })}
        {!loading && filteredSessions.length === 0 && (
          <li className="session-sidebar__empty">
            {mode === 'task'
              ? <>No coding tasks yet. Click <strong>+ New task</strong> to start.</>
              : <>No chats yet. Click <strong>+ New chat</strong> to start.</>}
          </li>
        )}
      </ul>
    </aside>
  );
};
