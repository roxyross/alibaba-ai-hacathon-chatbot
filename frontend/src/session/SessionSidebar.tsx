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
  LogIn,
  Globe,
  Compass,
  BookOpen,
  Code2,
  Brain,
  ShieldCheck,
  Layers,
  ChevronDown,
  CreditCard,
  Film,
} from 'lucide-react';
import { useSessions, ChatSession } from './useSessions';
import './SessionSidebar.css';

export type AppView =
  | 'chat'
  | 'pricing'
  | 'image_studio'
  | 'video_studio'
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
  | 'calendar'
  | 'research'
  | 'browser'
  | 'study'
  | 'coding'
  | 'memory'
  | 'audit';

export const SECONDARY_VIEWS: AppView[] = [
  'finance',
  'jobs',
  'voice',
  'research',
  'browser',
  'study',
  'coding',
  'memory',
  'audit',
  'documents',
  'email',
  'workspace_hub',
  'payment_methods',
];

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
  const [menuPlacement, setMenuPlacement] = useState<'up' | 'down'>('down');

  const isSecondaryActive = SECONDARY_VIEWS.includes(activeView);

  const [toolsOpen, setToolsOpen] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem('roxy_sidebar_tools_open');
      if (stored !== null) return stored === 'true';
    } catch {
      // ignore
    }
    return false;
  });

  // Auto-expand if a secondary tool is the currently active view
  useEffect(() => {
    if (isSecondaryActive && !toolsOpen) {
      setToolsOpen(true);
    }
  }, [activeView, isSecondaryActive]);

  const toggleToolsOpen = () => {
    setToolsOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('roxy_sidebar_tools_open', String(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const [railToolsMenuOpen, setRailToolsMenuOpen] = useState(false);
  const railToolsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!railToolsMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (railToolsRef.current && !railToolsRef.current.contains(e.target as Node)) {
        setRailToolsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [railToolsMenuOpen]);

  // Detect mobile viewport (<= 768px) to prevent rendering collapsed rail in mobile drawer
  const [isMobileScreen, setIsMobileScreen] = useState<boolean>(() => {
    return typeof window !== 'undefined' ? window.innerWidth <= 768 : false;
  });

  useEffect(() => {
    const handleResize = () => {
      setIsMobileScreen(window.innerWidth <= 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const menuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Platform-specific shortcut string
  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const shortcutLabel = isMac ? '⌘K' : 'Ctrl K';

  // Global Cmd/Ctrl + K shortcut handler
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isCollapsed) {
          onOpenSidebar?.();
        }
        setTimeout(() => {
          searchInputRef.current?.focus();
          searchInputRef.current?.select();
        }, 80);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [isCollapsed, onOpenSidebar]);

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
      window.dispatchEvent(new Event('roxy-pins-updated'));
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

  // If collapsed, render the sleek icon rail ONLY on desktop
  if (isCollapsed && !isMobileScreen) {
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
            aria-label={`Search chats (${shortcutLabel})`}
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
            <Plus size={18} strokeWidth={2.4} />
          </button>

          {/* New Task icon-only action */}
          <button
            type="button"
            className={`session-sidebar__rail-btn session-sidebar__rail-btn--accent ${mode === 'task' ? 'session-sidebar__rail-btn--accent-active' : ''}`}
            onClick={handleNewTaskAction}
            aria-label="New Task"
            data-tooltip="New Task"
          >
            <Zap size={16} strokeWidth={2.4} />
          </button>
        </div>

        {/* Rail navigation items */}
        {onViewChange && (
          <div className="session-sidebar__rail-nav">
            <div className="session-sidebar__rail-divider" />

            {/* Primary navigation icons */}
            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'chat' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('chat')}
              aria-label="Chat"
              data-tooltip="Chat"
            >
              <MessageSquare size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'image_studio' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('image_studio')}
              aria-label="Image Studio"
              data-tooltip="Image Studio"
            >
              <Sparkles size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'video_studio' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('video_studio')}
              aria-label="Video Studio"
              data-tooltip="Video Studio"
            >
              <Film size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'knowledge_vault' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('knowledge_vault')}
              aria-label="Knowledge Vault"
              data-tooltip="Knowledge Vault"
            >
              <Database size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'calendar' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('calendar')}
              aria-label="Calendar"
              data-tooltip="Calendar"
            >
              <Calendar size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'calculator' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('calculator')}
              aria-label="Calculator"
              data-tooltip="Calculator"
            >
              <Calculator size={17} strokeWidth={1.8} />
            </button>

            <div className="session-sidebar__rail-divider" />

            {/* Secondary Tools Popover */}
            <div className="session-sidebar__rail-tools-wrap" ref={railToolsRef}>
              <button
                type="button"
                className={`session-sidebar__rail-btn ${railToolsMenuOpen || isSecondaryActive ? 'session-sidebar__rail-btn--active' : ''}`}
                onClick={() => setRailToolsMenuOpen((v) => !v)}
                aria-label="All Tools"
                data-tooltip="All Tools"
                aria-expanded={railToolsMenuOpen}
              >
                <Layers size={17} strokeWidth={1.8} />
              </button>

              {railToolsMenuOpen && (
                <div className="session-sidebar__rail-popover" role="menu">
                  <div className="session-sidebar__rail-popover-header">
                    <span>Tools</span>
                  </div>
                  <div className="session-sidebar__rail-popover-list">
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'finance' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('finance');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Wallet size={15} strokeWidth={1.8} />
                      <span>Finances</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'jobs' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('jobs');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Clock size={15} strokeWidth={1.8} />
                      <span>Scheduled Jobs</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'voice' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('voice');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Mic size={15} strokeWidth={1.8} />
                      <span>Voice</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'research' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('research');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Globe size={15} strokeWidth={1.8} />
                      <span>Deep Research</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'browser' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('browser');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Compass size={15} strokeWidth={1.8} />
                      <span>Browser Studio</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'study' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('study');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <BookOpen size={15} strokeWidth={1.8} />
                      <span>Study Studio</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'coding' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('coding');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Code2 size={15} strokeWidth={1.8} />
                      <span>Coding Studio</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'memory' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('memory');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Brain size={15} strokeWidth={1.8} />
                      <span>Memory Studio</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'audit' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('audit');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <ShieldCheck size={15} strokeWidth={1.8} />
                      <span>Audit & Security</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'documents' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('documents');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <FileText size={15} strokeWidth={1.8} />
                      <span>Documents</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'email' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('email');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <Mail size={15} strokeWidth={1.8} />
                      <span>Email</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'workspace_hub' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('workspace_hub');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <LayoutGrid size={15} strokeWidth={1.8} />
                      <span>Workspace Hub</span>
                    </button>
                    <button
                      type="button"
                      className={`session-sidebar__rail-popover-item ${activeView === 'payment_methods' ? 'session-sidebar__rail-popover-item--active' : ''}`}
                      onClick={() => {
                        onViewChange('payment_methods');
                        setRailToolsMenuOpen(false);
                      }}
                    >
                      <CreditCard size={15} strokeWidth={1.8} />
                      <span>Payment Methods</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Rail bottom controls */}
        <div className="session-sidebar__rail-bottom">
          <button
            type="button"
            className={`session-sidebar__rail-btn ${activeView === 'usage' ? 'session-sidebar__rail-btn--active' : ''}`}
            onClick={() => onViewChange?.('usage')}
            aria-label="Usage"
            data-tooltip="Usage"
          >
            <BarChart2 size={16} strokeWidth={1.8} />
          </button>
          <button
            type="button"
            className={`session-sidebar__rail-btn ${activeView === 'billing' ? 'session-sidebar__rail-btn--active' : ''}`}
            onClick={() => onViewChange?.('billing')}
            aria-label="Billing"
            data-tooltip="Billing"
          >
            <Receipt size={16} strokeWidth={1.8} />
          </button>
          <button
            type="button"
            className={`session-sidebar__rail-btn ${activeView === 'pricing' ? 'session-sidebar__rail-btn--active' : ''}`}
            onClick={() => onViewChange?.('pricing')}
            aria-label="Upgrade Plans"
            data-tooltip="Upgrade Plans"
          >
            <Zap size={16} strokeWidth={2.2} color="#0d9488" />
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
      {/* 1. Header: Brand + Collapse Button */}
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
              aria-label={isMobileScreen ? 'Close sidebar' : 'Collapse sidebar'}
              data-tooltip={isMobileScreen ? undefined : 'Collapse sidebar'}
            >
              <PanelLeftClose size={17} strokeWidth={2} />
            </button>
          )}
        </div>

        {/* 2. Primary Action: Prominent New Chat Button */}
        <div className="session-sidebar__primary-action">
          <button
            type="button"
            className="session-sidebar__new-chat-btn"
            onClick={handleNewChatAction}
            aria-label="New Chat"
          >
            <Plus size={16} strokeWidth={2.4} />
            <span>New Chat</span>
          </button>
        </div>

        {/* 3. Refined Segmented Control: Chat / Task Switcher */}
        <div className="session-sidebar__mode-switcher" role="tablist" aria-label="Conversation mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'chat'}
            className={`session-sidebar__mode-tab ${mode === 'chat' ? 'session-sidebar__mode-tab--active' : ''}`}
            onClick={() => {
              onModeChange?.('chat');
              if (mode !== 'chat') handleNewChatAction();
            }}
            title="General chat & reasoning"
          >
            <MessageSquare size={13} strokeWidth={2} />
            <span>Chat</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'task'}
            className={`session-sidebar__mode-tab ${mode === 'task' ? 'session-sidebar__mode-tab--active' : ''}`}
            onClick={() => {
              onModeChange?.('task');
              if (mode !== 'task') handleNewTaskAction();
            }}
            title="Autonomous task execution & code"
          >
            <Zap size={13} strokeWidth={2.2} />
            <span>Task</span>
          </button>
        </div>

        {/* 4. Search Control */}
        <div className="session-sidebar__search-box">
          <Search size={14} strokeWidth={2} className="session-sidebar__search-icon" />
          <input
            ref={searchInputRef}
            type="search"
            className="session-sidebar__search-input"
            placeholder="Search chats..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                if (searchQuery) {
                  setSearchQuery('');
                } else {
                  searchInputRef.current?.blur();
                }
              }
            }}
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

      {/* 2. Primary Navigation & Collapsible Tools Accordion */}
      {onViewChange && (
        <div className="session-sidebar__primary-nav">
          <div className="session-sidebar__nav-list" aria-label="Primary Navigation">
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'chat' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('chat')}
            >
              <MessageSquare size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Chat</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'image_studio' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('image_studio')}
            >
              <Sparkles size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Images</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'video_studio' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('video_studio')}
            >
              <Film size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Video Studio</span>
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
              className={`session-sidebar__nav-link ${activeView === 'calendar' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('calendar')}
            >
              <Calendar size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Calendar</span>
            </button>
            <button
              type="button"
              className={`session-sidebar__nav-link ${activeView === 'calculator' ? 'session-sidebar__nav-link--active' : ''}`}
              onClick={() => onViewChange('calculator')}
            >
              <Calculator size={16} strokeWidth={1.8} className="session-sidebar__nav-icon" />
              <span className="session-sidebar__nav-text">Calculator</span>
            </button>
          </div>

          {/* Collapsible TOOLS Accordion */}
          <div className="session-sidebar__tools-accordion">
            <button
              type="button"
              className={`session-sidebar__tools-toggle ${toolsOpen ? 'session-sidebar__tools-toggle--open' : ''} ${isSecondaryActive ? 'session-sidebar__tools-toggle--active-child' : ''}`}
              onClick={toggleToolsOpen}
              aria-expanded={toolsOpen}
              aria-controls="sidebar-tools-drawer"
            >
              <div className="session-sidebar__tools-toggle-left">
                <Layers size={14} strokeWidth={1.8} className="session-sidebar__tools-icon" />
                <span className="session-sidebar__tools-title">Tools</span>
                <span className="session-sidebar__tools-count">13</span>
              </div>
              <ChevronDown
                size={14}
                strokeWidth={2}
                className={`session-sidebar__tools-chevron ${toolsOpen ? 'session-sidebar__tools-chevron--open' : ''}`}
              />
            </button>

            {toolsOpen && (
              <div id="sidebar-tools-drawer" className="session-sidebar__tools-drawer sidebar-tools-dropdown">
                <nav className="session-sidebar__nav-list session-sidebar__nav-list--tools" aria-label="Secondary tools">
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'finance' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('finance')}
                  >
                    <Wallet size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Finances</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'jobs' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('jobs')}
                  >
                    <Clock size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Scheduled Jobs</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'voice' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('voice')}
                  >
                    <Mic size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Voice</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'research' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('research')}
                  >
                    <Globe size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Deep Research</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'browser' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('browser')}
                  >
                    <Compass size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Browser Studio</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'study' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('study')}
                  >
                    <BookOpen size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Study Studio</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'coding' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('coding')}
                  >
                    <Code2 size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Coding Studio</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'memory' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('memory')}
                  >
                    <Brain size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Memory Studio</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'audit' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('audit')}
                  >
                    <ShieldCheck size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Audit & Security</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'documents' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('documents')}
                  >
                    <FileText size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Documents</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'email' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('email')}
                  >
                    <Mail size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Email</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'workspace_hub' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('workspace_hub')}
                  >
                    <LayoutGrid size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Workspace Hub</span>
                  </button>
                  <button
                    type="button"
                    className={`session-sidebar__nav-link ${activeView === 'payment_methods' ? 'session-sidebar__nav-link--active' : ''}`}
                    onClick={() => onViewChange('payment_methods')}
                  >
                    <CreditCard size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                    <span className="session-sidebar__nav-text">Payment Methods</span>
                  </button>
                </nav>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 3. Conversation Area: RECENT CHATS (Dedicated Independent Scroll Container) */}
      <div className="session-sidebar__chats-section">
        <div className="session-sidebar__chats-header">
          <span className="session-sidebar__chats-title">
            {searchQuery ? 'Search Results' : 'Recent Chats'}
          </span>
          {filteredSessions.length > 0 && (
            <span className="session-sidebar__chats-count">
              {filteredSessions.length}
            </span>
          )}
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
                            if (renameValue.trim() && renameValue.trim() !== s.title) {
                              await rename(s.id, renameValue.trim());
                            }
                            setRenamingId(null);
                          }}
                        >
                          <input
                            autoFocus
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Escape') {
                                e.stopPropagation();
                                setRenamingId(null);
                              }
                            }}
                            onBlur={async () => {
                              if (renameValue.trim() && renameValue.trim() !== s.title) {
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
                          aria-label={s.title || 'Untitled conversation'}
                        >
                          <span className="session-sidebar__session-title">
                            {isPinned && (
                              <span className="session-sidebar__item-icon-wrap" title="Pinned conversation">
                                <Pin size={11} className="session-sidebar__pin-indicator" />
                              </span>
                            )}
                            {isTask && (
                              <span className="session-sidebar__item-icon-wrap" title="Task session">
                                <Zap size={11} className="session-sidebar__task-indicator" />
                              </span>
                            )}
                            <span className="session-sidebar__session-title-text">
                              {s.title || 'Untitled conversation'}
                            </span>
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
                              const rect = e.currentTarget.getBoundingClientRect();
                              const spaceBelow = window.innerHeight - rect.bottom;
                              setMenuPlacement(spaceBelow < 145 ? 'up' : 'down');
                              setActiveMenuId((prev) => (prev === s.id ? null : s.id));
                            }}
                            aria-label="Conversation options"
                            aria-expanded={activeMenuId === s.id}
                          >
                            <MoreHorizontal size={14} />
                          </button>

                          {activeMenuId === s.id && (
                            <div
                              ref={menuRef}
                              className={`session-sidebar__dropdown session-sidebar__dropdown--${menuPlacement}`}
                              role="menu"
                            >
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
                  <div className="session-sidebar__empty-icon-box">
                    <LogIn size={18} strokeWidth={2} />
                  </div>
                  <p className="session-sidebar__empty-title">Sign in to save chats</p>
                  <p className="session-sidebar__empty-sub">Your conversations and tasks will sync across your devices.</p>
                  {onOpenAuth && (
                    <button
                      type="button"
                      className="session-sidebar__signin-btn"
                      onClick={() => onOpenAuth('signin')}
                    >
                      <LogIn size={13} strokeWidth={2} />
                      <span>Sign In</span>
                    </button>
                  )}
                </>
              ) : searchQuery ? (
                <>
                  <div className="session-sidebar__empty-icon-box">
                    <Search size={18} strokeWidth={2} />
                  </div>
                  <p className="session-sidebar__empty-title">No conversations found</p>
                  <p className="session-sidebar__empty-sub">No results match &ldquo;{searchQuery}&rdquo;</p>
                  <button
                    type="button"
                    className="session-sidebar__empty-action-btn"
                    onClick={() => setSearchQuery('')}
                  >
                    <X size={12} strokeWidth={2} />
                    <span>Clear search</span>
                  </button>
                </>
              ) : (
                <>
                  <div className="session-sidebar__empty-icon-box">
                    <MessageSquare size={18} strokeWidth={2} />
                  </div>
                  <p className="session-sidebar__empty-title">No conversations yet</p>
                  <p className="session-sidebar__empty-sub">Start a new conversation or run a task to begin.</p>
                  <button
                    type="button"
                    className="session-sidebar__empty-action-btn"
                    onClick={handleNewChatAction}
                  >
                    <Plus size={13} strokeWidth={2.2} />
                    <span>New Chat</span>
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 4. Footer: Account & Upgrade Row */}
      {onViewChange && (
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
      )}
    </aside>
  );
};
