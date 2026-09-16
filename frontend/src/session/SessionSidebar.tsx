import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Zap,
  Search,
  X,
  MoreHorizontal,
  Edit2,
  Trash2,
  Pin,
  MessageSquare,
  Mic,
  FileText,
  Sparkles,
  Database,
  LayoutGrid,
  Clock,
  Wallet,
  Mail,
  Calculator,
  Calendar,
  BarChart2,
  Receipt,
  ChevronDown,
  ChevronRight,
  LogIn,
} from 'lucide-react';
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
  onOpenSidebar?: () => void;
  initialSearchQuery?: string;
  isAuthenticated?: boolean;
  onOpenAuth?: (mode: 'signin' | 'signup', msg?: string) => void;
}

interface GroupedSessions {
  label: string;
  items: ChatSession[];
}

function groupSessionsByDate(sessions: ChatSession[]): GroupedSessions[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const startOf7Days = startOfToday - 7 * 86400000;

  const groups: { [key: string]: ChatSession[] } = {
    Today: [],
    Yesterday: [],
    'Previous 7 Days': [],
    Older: [],
  };

  for (const session of sessions) {
    const rawDate = session.updated_at || session.created_at;
    const ts = rawDate ? new Date(rawDate).getTime() : NaN;
    if (isNaN(ts) || ts >= startOfToday) {
      groups['Today'].push(session);
    } else if (ts >= startOfYesterday) {
      groups['Yesterday'].push(session);
    } else if (ts >= startOf7Days) {
      groups['Previous 7 Days'].push(session);
    } else {
      groups['Older'].push(session);
    }
  }

  return Object.entries(groups)
    .filter(([_, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
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
  onOpenSidebar,
  initialSearchQuery = '',
  isAuthenticated = false,
  onOpenAuth,
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
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [showUtilities, setShowUtilities] = useState(false);

  const menuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Platform-specific shortcut string
  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
  const shortcutLabel = isMac ? '⌘K' : 'Ctrl K';

  useEffect(() => {
    if (initialSearchQuery !== undefined) {
      setSearchQuery(initialSearchQuery);
    }
  }, [initialSearchQuery]);

  // Click outside listener for context menu
  useEffect(() => {
    if (!activeMenuId) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setActiveMenuId(null);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setActiveMenuId(null);
        setRenamingId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeMenuId]);

  // Check pinned sessions in localStorage
  const isSessionPinned = (id: string): boolean => {
    try {
      const saved = localStorage.getItem('roxy_pinned_items');
      if (!saved) return false;
      const items = JSON.parse(saved);
      return Array.isArray(items) && items.some((p: { id: string }) => p.id === id);
    } catch {
      return false;
    }
  };

  const togglePin = (session: ChatSession) => {
    try {
      const saved = localStorage.getItem('roxy_pinned_items');
      let items: Array<{ id: string; title: string; type: string }> = saved ? JSON.parse(saved) : [];
      if (items.some((p) => p.id === session.id)) {
        items = items.filter((p) => p.id !== session.id);
      } else {
        items.unshift({
          id: session.id,
          title: session.title || 'Untitled conversation',
          type: session.session_type === 'task' ? 'Task' : 'Conversation',
        });
      }
      localStorage.setItem('roxy_pinned_items', JSON.stringify(items));
      window.dispatchEvent(new Event('storage'));
      setActiveMenuId(null);
    } catch (err) {
      console.error('Failed to toggle pin:', err);
    }
  };

  // Filter sessions based on search query
  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase();
    return sessions.filter((s) => {
      return (
        (s.title && s.title.toLowerCase().includes(q)) ||
        (s.provider && s.provider.toLowerCase().includes(q)) ||
        (s.model && s.model.toLowerCase().includes(q))
      );
    });
  }, [sessions, searchQuery]);

  const groupedSessions = useMemo(() => {
    return groupSessionsByDate(filteredSessions);
  }, [filteredSessions]);

  // Handle New Chat trigger
  const handleNewChatAction = () => {
    onModeChange?.('chat');
    onNewChat();
    if (onViewChange) onViewChange('chat');
  };

  // Handle New Task trigger
  const handleNewTaskAction = () => {
    if (onNewTask) {
      onNewTask();
    } else {
      onModeChange?.('task');
      onNewChat();
    }
    if (onViewChange) onViewChange('chat');
  };

  // If collapsed, render the sleek icon rail
  if (isCollapsed) {
    return (
      <aside
        className="session-sidebar session-sidebar--collapsed"
        aria-label="Collapsed sidebar navigation"
      >
        <div className="session-sidebar__rail-top">
          {/* Brand mark */}
          <div className="session-sidebar__rail-brand" title="ROXY AI">
            <span className="session-sidebar__logo-badge">R</span>
          </div>

          {/* Expand sidebar trigger button */}
          <button
            type="button"
            className="session-sidebar__rail-btn"
            onClick={onOpenSidebar}
            aria-label="Open sidebar"
            data-tooltip="Open sidebar"
          >
            <PanelLeftOpen size={18} strokeWidth={2} />
          </button>

          {/* Quick search button */}
          <button
            type="button"
            className="session-sidebar__rail-btn"
            onClick={() => {
              onOpenSidebar?.();
              setTimeout(() => searchInputRef.current?.focus(), 80);
            }}
            aria-label="Search chats (Ctrl K)"
            data-tooltip={`Search chats (${shortcutLabel})`}
          >
            <Search size={18} strokeWidth={2} />
          </button>

          <div className="session-sidebar__rail-divider" />

          {/* New Chat icon-only action */}
          <button
            type="button"
            className={`session-sidebar__rail-btn session-sidebar__rail-btn--primary ${mode === 'chat' ? 'session-sidebar__rail-btn--active' : ''}`}
            onClick={handleNewChatAction}
            aria-label="New Chat"
            data-tooltip="New Chat"
          >
            <Plus size={19} strokeWidth={2.4} />
          </button>

          {/* New Task icon-only action */}
          <button
            type="button"
            className={`session-sidebar__rail-btn session-sidebar__rail-btn--accent ${mode === 'task' ? 'session-sidebar__rail-btn--accent-active' : ''}`}
            onClick={handleNewTaskAction}
            aria-label="New Task"
            data-tooltip="New Task"
          >
            <Zap size={17} strokeWidth={2.4} />
          </button>
        </div>

        {/* Rail navigation items */}
        {onViewChange && (
          <div className="session-sidebar__rail-nav">
            <div className="session-sidebar__rail-divider" />

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'chat' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('chat')}
              aria-label="Chat & Reasoning"
              data-tooltip="Chat & Reasoning"
            >
              <MessageSquare size={18} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'voice' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('voice')}
              aria-label="Voice Mode"
              data-tooltip="Voice Mode"
            >
              <Mic size={18} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'documents' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('documents')}
              aria-label="Document Upload"
              data-tooltip="Document Upload"
            >
              <FileText size={18} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'finance' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('finance')}
              aria-label="Finances"
              data-tooltip="Finances (Raast / Plaid)"
            >
              <Wallet size={18} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'jobs' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('jobs')}
              aria-label="Scheduled Jobs"
              data-tooltip="Scheduled Jobs"
            >
              <Clock size={18} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'image_studio' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('image_studio')}
              aria-label="Image Studio"
              data-tooltip="Image Studio"
            >
              <Sparkles size={18} strokeWidth={1.8} />
            </button>
          </div>
        )}

        {/* Rail bottom controls */}
        <div className="session-sidebar__rail-bottom">
          <button
            type="button"
            className={`session-sidebar__rail-btn ${activeView === 'pricing' ? 'session-sidebar__rail-btn--active' : ''}`}
            onClick={() => onViewChange?.('pricing')}
            aria-label="Upgrade Plans"
            data-tooltip="Upgrade Plans"
          >
            <Zap size={18} strokeWidth={2} color="#0d9488" />
          </button>
        </div>
      </aside>
    );
  }

  // Expanded Sidebar view
  return (
    <aside
      className="session-sidebar"
      aria-label="Conversations and workspace navigation"
    >
      {/* 1. Header: CONVERSATIONS + Collapse Button */}
      <div className="session-sidebar__header">
        <div className="session-sidebar__header-top">
          <div className="session-sidebar__brand-area">
            <span className="session-sidebar__logo-badge">R</span>
            <span className="session-sidebar__header-title">Conversations</span>
          </div>
          {onCloseSidebar && (
            <button
              type="button"
              className="session-sidebar__collapse-btn"
              onClick={onCloseSidebar}
              aria-label="Collapse sidebar"
              data-tooltip="Collapse sidebar"
            >
              <PanelLeftClose size={17} strokeWidth={2} />
            </button>
          )}
        </div>

        {/* 2. Search Control */}
        <div className="session-sidebar__search-box">
          <Search size={14} strokeWidth={2} className="session-sidebar__search-icon" />
          <input
            ref={searchInputRef}
            type="search"
            className="session-sidebar__search-input"
            placeholder="Search chats..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search chats"
          />
          {searchQuery ? (
            <button
              type="button"
              className="session-sidebar__search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
              title="Clear search"
            >
              <X size={12} strokeWidth={2.2} />
            </button>
          ) : (
            <kbd className="session-sidebar__search-kbd">{shortcutLabel}</kbd>
          )}
        </div>
      </div>

      {/* 3. Conversation Area: RECENT CHATS with compact [ + ] [ ⚡ ] actions */}
      <div className="session-sidebar__chats-section">
        <div className="session-sidebar__chats-header">
          <span className="session-sidebar__chats-title">
            {searchQuery ? 'Search Results' : 'Recent Chats'}
          </span>
          <div className="session-sidebar__quick-actions">
            <button
              type="button"
              className={`session-sidebar__action-icon-btn ${mode === 'chat' ? 'session-sidebar__action-icon-btn--active' : ''}`}
              onClick={handleNewChatAction}
              aria-label="New Chat"
              data-tooltip="New Chat"
            >
              <Plus size={16} strokeWidth={2.2} />
            </button>
            <button
              type="button"
              className={`session-sidebar__action-icon-btn session-sidebar__action-icon-btn--task ${mode === 'task' ? 'session-sidebar__action-icon-btn--task-active' : ''}`}
              onClick={handleNewTaskAction}
              aria-label="New Task"
              data-tooltip="New Task"
            >
              <Zap size={14} strokeWidth={2.2} />
            </button>
          </div>
        </div>

        {/* History List / Date Grouping */}
        <div className="session-sidebar__scroll-area">
          {loading && (
            <div className="session-sidebar__status-box">
              <span className="session-sidebar__spinner" />
              <span>Loading conversations…</span>
            </div>
          )}

          {error && (
            <div className="session-sidebar__status-box session-sidebar__status-box--error">
              <span>{error}</span>
            </div>
          )}

          {groupedSessions.map(({ label, items }) => (
            <div key={label} className="session-sidebar__date-group">
              <span className="session-sidebar__date-label">{label}</span>
              <ul className="session-sidebar__list">
                {items.map((s) => {
                  const isActive = s.id === activeSessionId;
                  const isRenaming = renamingId === s.id;
                  const isPinned = isSessionPinned(s.id);
                  const isTask = s.session_type === 'task' || s.title?.startsWith('[Task]');

                  return (
                    <li
                      key={s.id}
                      className={`session-sidebar__item ${isActive ? 'session-sidebar__item--active' : ''}`}
                    >
                      {isRenaming ? (
                        <form
                          className="session-sidebar__rename-form"
                          onSubmit={async (e) => {
                            e.preventDefault();
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
                            onBlur={async () => {
                              if (renameValue.trim()) {
                                await rename(s.id, renameValue.trim());
                              }
                              setRenamingId(null);
                            }}
                            className="session-sidebar__rename-input"
                            aria-label="Rename conversation"
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
                            {isPinned && <Pin size={12} className="session-sidebar__pin-indicator" />}
                            {isTask && <Zap size={12} className="session-sidebar__task-indicator" />}
                            {s.title || 'Untitled conversation'}
                          </span>
                        </button>
                      )}

                      {/* Context Menu Trigger */}
                      {!isRenaming && (
                        <div className="session-sidebar__menu-container">
                          <button
                            type="button"
                            className={`session-sidebar__item-menu-btn ${activeMenuId === s.id ? 'session-sidebar__item-menu-btn--active' : ''}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setActiveMenuId((prev) => (prev === s.id ? null : s.id));
                            }}
                            aria-label="Conversation options"
                            aria-expanded={activeMenuId === s.id}
                          >
                            <MoreHorizontal size={14} />
                          </button>

                          {activeMenuId === s.id && (
                            <div ref={menuRef} className="session-sidebar__dropdown" role="menu">
                              <button
                                type="button"
                                className="session-sidebar__dropdown-item"
                                role="menuitem"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setActiveMenuId(null);
                                  setRenamingId(s.id);
                                  setRenameValue(s.title || '');
                                }}
                              >
                                <Edit2 size={13} strokeWidth={2} />
                                <span>Rename</span>
                              </button>

                              <button
                                type="button"
                                className="session-sidebar__dropdown-item"
                                role="menuitem"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  togglePin(s);
                                }}
                              >
                                <Pin size={13} strokeWidth={2} />
                                <span>{isPinned ? 'Unpin' : 'Pin to top'}</span>
                              </button>

                              <button
                                type="button"
                                className="session-sidebar__dropdown-item session-sidebar__dropdown-item--delete"
                                role="menuitem"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setActiveMenuId(null);
                                  if (window.confirm('Delete this conversation?')) {
                                    void remove(s.id);
                                  }
                                }}
                              >
                                <Trash2 size={13} strokeWidth={2} />
                                <span>Delete</span>
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}

          {/* Empty State Requirements */}
          {!loading && filteredSessions.length === 0 && (
            <div className="session-sidebar__empty-state">
              {!isAuthenticated ? (
                <>
                  <p className="session-sidebar__empty-title">Sign in to save your conversations</p>
                  <p className="session-sidebar__empty-sub">Your conversations will appear here.</p>
                  {onOpenAuth && (
                    <button
                      type="button"
                      className="session-sidebar__signin-btn"
                      onClick={() => onOpenAuth('signin')}
                    >
                      <LogIn size={13} />
                      <span>Sign In</span>
                    </button>
                  )}
                </>
              ) : searchQuery ? (
                <>
                  <p className="session-sidebar__empty-title">No conversations found</p>
                  <p className="session-sidebar__empty-sub">No results match &ldquo;{searchQuery}&rdquo;</p>
                </>
              ) : (
                <>
                  <p className="session-sidebar__empty-title">Your conversations will appear here.</p>
                  <p className="session-sidebar__empty-sub">Start a new chat to begin.</p>
                  <button
                    type="button"
                    className="session-sidebar__empty-action-btn"
                    onClick={handleNewChatAction}
                  >
                    <Plus size={14} />
                    <span>New Chat</span>
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 4. Workspace & Tools Navigation Hierarchy */}
      {onViewChange && (
        <div className="session-sidebar__footer-nav">
          {/* WORKSPACE */}
          <div className="session-sidebar__section-title">
            <span>Workspace</span>
          </div>
          <nav className="session-sidebar__nav-list" aria-label="Workspace Modules">
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'chat' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('chat')}
            >
              <MessageSquare size={17} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Chat &amp; Reasoning</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'voice' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('voice')}
            >
              <Mic size={17} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Voice Mode</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'documents' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('documents')}
            >
              <FileText size={17} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Document Upload</span>
            </button>
          </nav>

          {/* Collapsible Utilities Drawer */}
          <div className="session-sidebar__utilities-wrap">
            <button
              type="button"
              className="session-sidebar__utilities-toggle"
              onClick={() => setShowUtilities((v) => !v)}
              aria-expanded={showUtilities}
            >
              <span className="session-sidebar__section-title-text">Tools &amp; Extensions</span>
              {showUtilities ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {showUtilities && (
              <nav className="session-sidebar__nav-list session-sidebar__nav-list--sub" aria-label="Tools">
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'finance' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('finance')}
                >
                  <Wallet size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Finances (Raast / Plaid)</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'jobs' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('jobs')}
                >
                  <Clock size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Scheduled Jobs</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'image_studio' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('image_studio')}
                >
                  <Sparkles size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Image Studio</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'knowledge_vault' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('knowledge_vault')}
                >
                  <Database size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Knowledge Vault</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'workspace_hub' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('workspace_hub')}
                >
                  <LayoutGrid size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Workspace Hub</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'email' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('email')}
                >
                  <Mail size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Email Send</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'calculator' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('calculator')}
                >
                  <Calculator size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Calculator</span>
                </button>
                <button
                  type="button"
                  className={`session-sidebar__nav-link ${activeView === 'calendar' ? 'session-sidebar__nav-link--active' : ''}`}
                  onClick={() => onViewChange('calendar')}
                >
                  <Calendar size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                  <span className="session-sidebar__nav-text">Calendar</span>
                </button>
              </nav>
            )}
          </div>

          {/* ACCOUNT & UPGRADE */}
          <div className="session-sidebar__account-row">
            <button
              type="button"
              className={`session-sidebar__account-link ${activeView === 'usage' ? 'session-sidebar__account-link--active' : ''}`}
              onClick={() => onViewChange('usage')}
              title="Usage & Telemetry"
            >
              <BarChart2 size={15} strokeWidth={1.8} />
              <span>Usage</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__account-link ${activeView === 'billing' ? 'session-sidebar__account-link--active' : ''}`}
              onClick={() => onViewChange('billing')}
              title="Billing & Invoices"
            >
              <Receipt size={15} strokeWidth={1.8} />
              <span>Billing</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__upgrade-pill ${activeView === 'pricing' ? 'session-sidebar__upgrade-pill--active' : ''}`}
              onClick={() => onViewChange('pricing')}
              title="Upgrade Plans"
            >
              <Zap size={13} strokeWidth={2.4} />
              <span>Upgrade</span>
            </button>
          </div>
        </div>
      )}
    </aside>
  );
};
