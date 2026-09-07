import React, { useState } from 'react';
import { useSessions, ChatSession } from './useSessions';
import './SessionSidebar.css';

export type AppView = 'chat' | 'finance' | 'jobs' | 'email' | 'voice' | 'documents';

interface SessionSidebarProps {
  activeSessionId: string | null;
  activeView?: AppView;
  onSelect: (session: ChatSession) => void;
  onNewChat: () => void;
  onViewChange?: (view: AppView) => void;
}

export const SessionSidebar: React.FC<SessionSidebarProps> = ({
  activeSessionId,
  activeView = 'chat',
  onSelect,
  onNewChat,
  onViewChange,
}) => {
  const { sessions, loading, error, rename, remove } = useSessions();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');

  return (
    <aside className="session-sidebar" aria-label="Chat history">
      <div className="session-sidebar__header">
        <button
          type="button"
          className="session-sidebar__new"
          onClick={() => {
            onNewChat();
            if (onViewChange) onViewChange('chat');
          }}
        >
          + New chat
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
              className={`session-sidebar__nav-item${activeView === 'voice' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('voice')}
            >
              <span className="session-sidebar__nav-icon">🎙️</span>
              <span className="session-sidebar__nav-label">Voice Mode</span>
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
              className={`session-sidebar__nav-item${activeView === 'jobs' ? ' session-sidebar__nav-item--active' : ''}`}
              onClick={() => onViewChange('jobs')}
            >
              <span className="session-sidebar__nav-icon">⏰</span>
              <span className="session-sidebar__nav-label">Scheduled Jobs</span>
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
          </nav>
        )}
      </div>

      <div className="session-sidebar__section-title">Recent Chats</div>

      {loading && (
        <p className="session-sidebar__status">Loading…</p>
      )}
      {error && (
        <p className="session-sidebar__status session-sidebar__status--error">
          {error}
        </p>
      )}

      <ul className="session-sidebar__list">
        {sessions.map((s) => {
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
                    {s.title || 'New chat'}
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
                  className="session-sidebar__icon"
                  title="Delete"
                  aria-label="Delete session"
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm('Delete this chat?')) return;
                    await remove(s.id);
                    if (isActive) onNewChat();
                  }}
                >
                  ✕
                </button>
              </div>
            </li>
          );
        })}
        {!loading && sessions.length === 0 && (
          <li className="session-sidebar__empty">
            No chats yet. Click <strong>+ New chat</strong> to start.
          </li>
        )}
      </ul>
    </aside>
  );
};
