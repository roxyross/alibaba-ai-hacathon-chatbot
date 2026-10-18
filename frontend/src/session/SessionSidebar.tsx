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
  ChevronRight,
  Archive,
  Share2,
  CreditCard,
  Film,
  Monitor,
  Sliders,
  FolderPlus,
  FolderCheck,
  Check,
  Copy,
} from 'lucide-react';
import { useSessions, ChatSession } from './useSessions';
import { useTranslation, LOCALES, Locale } from '../i18n';
import { useAuth } from '../auth';
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
  | 'audit'
  | 'connectors'
  | 'device_hub'
  | 'control_center'
  | 'trust_center';

export const SECONDARY_VIEWS: AppView[] = [
  'study',
  'documents',
  'memory',
  'voice',
  'email',
  'jobs',
  'workspace_hub',
  'connectors',
  'control_center',
  'trust_center',
  'audit',
  'finance',
  'payment_methods',
];

export interface NavItemConfig {
  id: AppView;
  titleKey: string;
  defaultTitle: string;
  icon: React.ElementType;
  shortcut?: string;
}

export interface NavGroupConfig {
  id: string;
  titleKey: string;
  defaultTitle: string;
  icon: React.ElementType;
  items: NavItemConfig[];
}

export const NAVIGATION_GROUPS: NavGroupConfig[] = [
  {
    id: 'core',
    titleKey: 'nav_groups.core',
    defaultTitle: 'Core',
    icon: MessageSquare,
    items: [
      { id: 'chat', titleKey: 'nav.chat', defaultTitle: 'Chat & Assistant', icon: MessageSquare },
      { id: 'coding', titleKey: 'nav.coding', defaultTitle: 'Code Studio (IDE)', icon: Code2, shortcut: 'Ctrl+Alt+I' },
    ],
  },
  {
    id: 'autonomous',
    titleKey: 'nav_groups.autonomous',
    defaultTitle: 'Autonomous Workspaces',
    icon: Compass,
    items: [
      { id: 'browser', titleKey: 'nav.browser', defaultTitle: 'Browser Studio', icon: Compass },
      { id: 'device_hub', titleKey: 'nav.device_hub', defaultTitle: 'Universal App Control', icon: Monitor },
      { id: 'research', titleKey: 'nav.research', defaultTitle: 'Deep Research', icon: Globe },
    ],
  },
  {
    id: 'knowledge',
    titleKey: 'nav_groups.knowledge',
    defaultTitle: 'Knowledge',
    icon: Database,
    items: [
      { id: 'knowledge_vault', titleKey: 'nav.knowledge_vault', defaultTitle: 'Knowledge Vault', icon: Database },
      { id: 'memory', titleKey: 'nav.memory', defaultTitle: 'Memory & Curator', icon: Brain },
      { id: 'documents', titleKey: 'nav.documents', defaultTitle: 'Documents & Vault', icon: FileText },
      { id: 'study', titleKey: 'nav.study', defaultTitle: 'Study Studio', icon: BookOpen },
    ],
  },
  {
    id: 'productivity',
    titleKey: 'nav_groups.productivity',
    defaultTitle: 'Productivity',
    icon: Calendar,
    items: [
      { id: 'calendar', titleKey: 'nav.calendar', defaultTitle: 'Calendar & Agendas', icon: Calendar },
      { id: 'email', titleKey: 'nav.email', defaultTitle: 'Email Hub', icon: Mail },
      { id: 'voice', titleKey: 'nav.voice', defaultTitle: 'Voice Session', icon: Mic },
      { id: 'jobs', titleKey: 'nav.jobs', defaultTitle: 'Scheduled Jobs', icon: Clock },
      { id: 'calculator', titleKey: 'nav.calculator', defaultTitle: 'Calculator', icon: Calculator },
    ],
  },
  {
    id: 'business',
    titleKey: 'nav_groups.business',
    defaultTitle: 'Business & Account',
    icon: Wallet,
    items: [
      { id: 'finance', titleKey: 'nav.finance', defaultTitle: 'Finance & Banking', icon: Wallet },
      { id: 'billing', titleKey: 'nav.billing', defaultTitle: 'Billing & Plans', icon: Receipt },
      { id: 'payment_methods', titleKey: 'nav.payment_methods', defaultTitle: 'Payment Methods', icon: CreditCard },
      { id: 'pricing', titleKey: 'nav.pricing', defaultTitle: 'Pricing & Plans', icon: Zap },
      { id: 'usage', titleKey: 'nav.usage', defaultTitle: 'Usage & Telemetry', icon: BarChart2 },
    ],
  },
  {
    id: 'system',
    titleKey: 'nav_groups.system',
    defaultTitle: 'System & Trust',
    icon: ShieldCheck,
    items: [
      { id: 'connectors', titleKey: 'nav.connectors', defaultTitle: 'Connectors Hub', icon: Layers },
      { id: 'control_center', titleKey: 'nav.control_center', defaultTitle: 'Control Center', icon: Sliders },
      { id: 'trust_center', titleKey: 'nav.trust_center', defaultTitle: 'Trust & Safety', icon: ShieldCheck },
      { id: 'audit', titleKey: 'nav.audit', defaultTitle: 'Audit & Security', icon: ShieldCheck },
    ],
  },
  {
    id: 'media',
    titleKey: 'nav_groups.media',
    defaultTitle: 'Media & Workspaces',
    icon: Sparkles,
    items: [
      { id: 'image_studio', titleKey: 'nav.image_studio', defaultTitle: 'Image Studio', icon: Sparkles },
      { id: 'video_studio', titleKey: 'nav.video_studio', defaultTitle: 'Video Studio', icon: Film },
      { id: 'workspace_hub', titleKey: 'nav.workspace_hub', defaultTitle: 'Workspace Hub', icon: LayoutGrid },
    ],
  },
];

export interface ProjectOption {
  id: string;
  name: string;
  desc: string;
}

export const PROJECT_OPTIONS: ProjectOption[] = [
  { id: 'default', name: 'Default Workspace', desc: 'General conversations and active tasks' },
  { id: 'design', name: 'Product Redesign', desc: 'UI/UX overhaul and design system items' },
  { id: 'ai-eng', name: 'AI Engineering', desc: 'Models, prompts, agents, and pipeline tasks' },
  { id: 'research', name: 'Deep Research', desc: 'Synthesized papers, web extracts, and vaults' },
  { id: 'personal', name: 'Personal & Notes', desc: 'Personal agendas, thoughts, and documents' },
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
  onTogglePin?: (id: string, pinned: boolean) => Promise<ChatSession>;
  onToggleArchive?: (id: string, archived: boolean) => Promise<ChatSession>;
  onShare?: (session: ChatSession) => void;
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
  onTogglePin: propTogglePin,
  onToggleArchive: propToggleArchive,
  onShare: propShare,
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
  const togglePinBackend = propTogglePin || localHook.togglePin;
  const toggleArchiveBackend = propToggleArchive || localHook.toggleArchive;
  const { authedFetch } = useAuth();

  const { t, locale, setLocale, locales } = useTranslation();
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const langMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!langMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (langMenuRef.current && !langMenuRef.current.contains(e.target as Node)) {
        setLangMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [langMenuOpen]);

  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [menuPlacement, setMenuPlacement] = useState<'up' | 'down'>('down');

  const isSecondaryActive = SECONDARY_VIEWS.includes(activeView);

  const [movingSession, setMovingSession] = useState<ChatSession | null>(null);
  const [projectToast, setProjectToast] = useState<string | null>(null);
  const [copyConvToast, setCopyConvToast] = useState<string | null>(null);

  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(() => {
    try {
      const stored = localStorage.getItem('roxy_sidebar_expanded_groups');
      if (stored) return JSON.parse(stored);
    } catch {
      // ignore
    }
    return { core: true, autonomous: false, knowledge: false, productivity: false, business: false, system: false, media: false };
  });

  const toggleGroupExpanded = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = { ...prev, [groupId]: !prev[groupId] };
      try {
        localStorage.setItem('roxy_sidebar_expanded_groups', JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  // Auto-expand group containing the activeView
  useEffect(() => {
    const activeGroup = NAVIGATION_GROUPS.find((g) => g.items.some((item) => item.id === activeView));
    if (activeGroup && !expandedGroups[activeGroup.id]) {
      setExpandedGroups((prev) => {
        const next = { ...prev, [activeGroup.id]: true };
        try {
          localStorage.setItem('roxy_sidebar_expanded_groups', JSON.stringify(next));
        } catch {
          // ignore
        }
        return next;
      });
    }
  }, [activeView]);

  const handleAssignProject = async (sessionId: string, projectName: string) => {
    try {
      if (localHook.moveToProject) {
        await localHook.moveToProject(sessionId, projectName);
      } else {
        await authedFetch(`/sessions/${sessionId}`, {
          method: 'PATCH',
          body: JSON.stringify({ project_id: projectName }),
        });
      }
      try {
        const saved = localStorage.getItem('roxy_session_projects');
        const map: Record<string, string> = saved ? JSON.parse(saved) : {};
        map[sessionId] = projectName;
        localStorage.setItem('roxy_session_projects', JSON.stringify(map));
      } catch {
        // local mirror
      }
      window.dispatchEvent(new CustomEvent('roxy-session-moved', { detail: { sessionId, projectName } }));
      setMovingSession(null);
      setProjectToast(`Moved to ${projectName}`);
      setTimeout(() => setProjectToast(null), 2500);
    } catch (e) {
      console.error('Failed to save session project assignment to server:', e);
      setProjectToast('Failed to move session');
      setTimeout(() => setProjectToast(null), 3000);
    }
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

  const [copyShareToast, setCopyShareToast] = useState<string | null>(null);

  const [pinnedCollapsed, setPinnedCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('roxy_sidebar_pinned_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const [recentCollapsed, setRecentCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('roxy_sidebar_recent_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const togglePinnedCollapsed = () => {
    setPinnedCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('roxy_sidebar_pinned_collapsed', String(next));
      } catch {
        /* ignore storage error */
      }
      return next;
    });
  };

  const toggleRecentCollapsed = () => {
    setRecentCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('roxy_sidebar_recent_collapsed', String(next));
      } catch {
        /* ignore storage error */
      }
      return next;
    });
  };

  const handleTogglePin = async (session: ChatSession) => {
    const isCurrentlyPinned = Boolean(session.pinned || isSessionPinned(session.id));
    const nextPinned = !isCurrentlyPinned;
    setActiveMenuId(null);

    // Immediate local persistence
    try {
      const saved = localStorage.getItem('roxy_pinned_items');
      let items: Array<{ id: string; title: string; type: string }> = saved ? JSON.parse(saved) : [];
      if (!nextPinned) {
        items = items.filter((p) => p.id !== session.id);
      } else {
        if (!items.some((p) => p.id === session.id)) {
          items.unshift({
            id: session.id,
            title: session.title || 'Untitled conversation',
            type: session.session_type === 'task' ? 'Task' : 'Conversation',
          });
        }
      }
      localStorage.setItem('roxy_pinned_items', JSON.stringify(items));
      window.dispatchEvent(new Event('storage'));
      window.dispatchEvent(new Event('roxy-pins-updated'));
    } catch (err) {
      console.error('Failed to toggle local pin:', err);
    }

    // Persist in backend
    try {
      await togglePinBackend(session.id, nextPinned);
    } catch (err) {
      console.warn('Backend pin update fallback to local storage:', err);
    }
  };

  const handleToggleArchive = async (session: ChatSession) => {
    setActiveMenuId(null);
    try {
      await toggleArchiveBackend(session.id, true);
    } catch (err) {
      console.error('Failed to archive session:', err);
    }
  };

  const handleShare = async (session: ChatSession) => {
    setActiveMenuId(null);
    if (propShare) {
      propShare(session);
      return;
    }
    try {
      const res = await authedFetch<{ url?: string; share_url?: string; share_token?: string }>(
        `/sessions/${session.id}/share`,
        { method: 'POST' }
      );
      const path = res?.url || res?.share_url || `/share/${res?.share_token || session.id}`;
      const shareUrl = `${window.location.origin}${path}`;
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(shareUrl);
        setCopyShareToast(session.id);
        setTimeout(() => setCopyShareToast(null), 2000);
      }
    } catch (err) {
      console.error('Secure share failed:', err);
      setProjectToast('Failed to generate share link');
      setTimeout(() => setProjectToast(null), 3000);
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

  // Partition into pinned and recent sessions
  const { pinnedSessions, recentSessions } = useMemo(() => {
    const pinned: ChatSession[] = [];
    const recent: ChatSession[] = [];
    for (const s of filteredSessions) {
      if (s.pinned || isSessionPinned(s.id)) {
        pinned.push(s);
      } else {
        recent.push(s);
      }
    }
    return { pinnedSessions: pinned, recentSessions: recent };
  }, [filteredSessions]);

  const groupedRecentSessions = useMemo(() => {
    return groupSessionsByDate(recentSessions);
  }, [recentSessions]);

  const renderSessionItem = (s: ChatSession, isPinnedItem = false) => {
    const isActive = s.id === activeSessionId;
    const isRenaming = renamingId === s.id;
    const isPinned = isPinnedItem || Boolean(s.pinned || isSessionPinned(s.id));
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
                try {
                  await rename(s.id, renameValue.trim());
                } catch {
                  alert('Rename failed. Please retry.');
                }
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
                  try {
                    await rename(s.id, renameValue.trim());
                  } catch {
                    // keep old title on error
                  }
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
                setMenuPlacement(spaceBelow < 185 ? 'up' : 'down');
                setActiveMenuId((prev) => (prev === s.id ? null : s.id));
              }}
              aria-label="More conversation actions"
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
                  aria-label="Rename conversation"
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
                  aria-label={isPinned ? 'Unpin conversation' : 'Pin conversation'}
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleTogglePin(s);
                  }}
                >
                  <Pin size={13} strokeWidth={2} />
                  <span>{isPinned ? 'Unpin' : 'Pin to top'}</span>
                </button>

                <button
                  type="button"
                  className="session-sidebar__dropdown-item"
                  role="menuitem"
                  aria-label="Move conversation to project"
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveMenuId(null);
                    setMovingSession(s);
                  }}
                >
                  <FolderPlus size={13} strokeWidth={2} />
                  <span>Move to Project</span>
                </button>

                <button
                  type="button"
                  className="session-sidebar__dropdown-item"
                  role="menuitem"
                  aria-label="Copy conversation content"
                  onClick={async (e) => {
                    e.stopPropagation();
                    setActiveMenuId(null);
                    const text = `Conversation: ${s.title || 'Untitled'}\nID: ${s.id}\nUpdated: ${s.updated_at || s.created_at || 'Recently'}`;
                    if (navigator.clipboard) {
                      await navigator.clipboard.writeText(text);
                      setCopyConvToast(s.id);
                      setTimeout(() => setCopyConvToast(null), 2000);
                    }
                  }}
                >
                  <Copy size={13} strokeWidth={2} />
                  <span>{copyConvToast === s.id ? 'Copied content!' : 'Copy Content'}</span>
                </button>

                <button
                  type="button"
                  className="session-sidebar__dropdown-item session-sidebar__dropdown-item--archive"
                  role="menuitem"
                  aria-label="Archive conversation"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleToggleArchive(s);
                  }}
                >
                  <Archive size={13} strokeWidth={2} />
                  <span>Archive</span>
                </button>

                <button
                  type="button"
                  className="session-sidebar__dropdown-item session-sidebar__dropdown-item--share"
                  role="menuitem"
                  aria-label="Share conversation"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleShare(s);
                  }}
                >
                  <Share2 size={13} strokeWidth={2} />
                  <span>{copyShareToast === s.id ? 'Copied link!' : 'Share'}</span>
                </button>

                <button
                  type="button"
                  className="session-sidebar__dropdown-item session-sidebar__dropdown-item--delete"
                  role="menuitem"
                  aria-label="Delete conversation"
                  onClick={async (e) => {
                    e.stopPropagation();
                    setActiveMenuId(null);
                    if (window.confirm('Delete this conversation permanently?')) {
                      try {
                        await remove(s.id);
                      } catch {
                        alert('Delete failed. Please retry.');
                      }
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
  };

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
              className={`session-sidebar__rail-btn ${activeView === 'chat' && mode === 'chat' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => {
                onModeChange?.('chat');
                onViewChange('chat');
              }}
              aria-label="Chat"
              data-tooltip="Chat"
            >
              <MessageSquare size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'coding' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('coding')}
              aria-label="IDE / Code Studio"
              data-tooltip="IDE / Code Studio (Ctrl+Alt+I)"
            >
              <Code2 size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'browser' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('browser')}
              aria-label="Browser Studio"
              data-tooltip="Browser Studio"
            >
              <Compass size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'research' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('research')}
              aria-label="Deep Research"
              data-tooltip="Deep Research"
            >
              <Globe size={17} strokeWidth={1.8} />
            </button>

            <button
              type="button"
              className={`session-sidebar__rail-btn ${activeView === 'device_hub' ? 'session-sidebar__rail-btn--active' : ''}`}
              onClick={() => onViewChange('device_hub')}
              aria-label="Device & App Control"
              data-tooltip="Device & App Control"
            >
              <Monitor size={17} strokeWidth={1.8} />
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
                    <span>Workspaces</span>
                  </div>
                  <div className="session-sidebar__rail-popover-list">
                    {NAVIGATION_GROUPS.map((g) => (
                      <div key={g.id} className="session-sidebar__rail-popover-group">
                        <div className="session-sidebar__rail-popover-group-title">
                          {t(g.titleKey) || g.defaultTitle}
                        </div>
                        {g.items.map((item) => {
                          const IconComp = item.icon;
                          const isActive = activeView === item.id;
                          return (
                            <button
                              key={item.id}
                              type="button"
                              className={`session-sidebar__rail-popover-item ${isActive ? 'session-sidebar__rail-popover-item--active' : ''}`}
                              onClick={() => {
                                onViewChange(item.id);
                                setRailToolsMenuOpen(false);
                              }}
                            >
                              <IconComp size={14} strokeWidth={1.8} />
                              <span>{t(item.titleKey) || item.defaultTitle}</span>
                            </button>
                          );
                        })}
                      </div>
                    ))}
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
            className="session-sidebar__rail-btn"
            onClick={() => {
              const next: Locale = locale === 'en' ? 'ur' : locale === 'ur' ? 'ar' : 'en';
              setLocale(next);
            }}
            aria-label={`Language: ${LOCALES[locale].nativeName}`}
            data-tooltip={`Language: ${LOCALES[locale].nativeName}`}
          >
            <Globe size={16} strokeWidth={1.8} />
          </button>
          <button
            type="button"
            className={`session-sidebar__rail-btn ${activeView === 'usage' ? 'session-sidebar__rail-btn--active' : ''}`}
            onClick={() => onViewChange?.('usage')}
            aria-label={t('nav.usage')}
            data-tooltip={t('nav.usage')}
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

        {/* 2. Primary Actions: New Chat & New Task */}
        <div className="session-sidebar__primary-action">
          <button
            type="button"
            className={`session-sidebar__new-chat-btn ${mode === 'chat' ? 'session-sidebar__new-chat-btn--primary' : ''}`}
            onClick={handleNewChatAction}
            aria-label={t('common.new_chat')}
            title={t('common.new_chat')}
          >
            <Plus size={15} strokeWidth={2.4} />
            <span>{t('common.new_chat')}</span>
          </button>
          <button
            type="button"
            className={`session-sidebar__new-task-btn ${mode === 'task' ? 'session-sidebar__new-task-btn--active' : ''}`}
            onClick={handleNewTaskAction}
            aria-label={t('common.new_task')}
            title={t('common.new_task')}
          >
            <Zap size={14} strokeWidth={2.2} />
            <span>{t('common.new_task')}</span>
          </button>
        </div>

        {/* 3. Search Control */}
        <div className="session-sidebar__search-box">
          <Search size={14} strokeWidth={2} className="session-sidebar__search-icon" />
          <input
            ref={searchInputRef}
            type="search"
            className="session-sidebar__search-input"
            placeholder={t('sidebar.search_placeholder')}
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
            aria-label={t('common.search')}
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

      {/* 2. Cohesive Global Navigation: 7 Workspaces & Studio Groups */}
      {onViewChange && (
        <div className="session-sidebar__nav-accordion" role="navigation" aria-label="Workspaces & Navigation">
          {NAVIGATION_GROUPS.map((group) => {
            const isGroupOpen = Boolean(expandedGroups[group.id]);
            const hasActiveItem = group.items.some((item) => item.id === activeView);
            const GroupIcon = group.icon;

            return (
              <div
                key={group.id}
                className={`session-sidebar__group ${hasActiveItem ? 'session-sidebar__group--has-active' : ''}`}
              >
                <button
                  type="button"
                  className={`session-sidebar__group-header ${isGroupOpen ? 'session-sidebar__group-header--open' : ''} ${hasActiveItem ? 'session-sidebar__group-header--active' : ''}`}
                  onClick={() => toggleGroupExpanded(group.id)}
                  aria-expanded={isGroupOpen}
                  aria-controls={`sidebar-group-${group.id}`}
                  aria-label={`${t(group.titleKey) || group.defaultTitle} (${group.items.length} items)`}
                >
                  <div className="session-sidebar__group-header-left">
                    <GroupIcon size={14} strokeWidth={1.8} className="session-sidebar__group-icon" />
                    <span className="session-sidebar__group-title">
                      {t(group.titleKey) || group.defaultTitle}
                    </span>
                    <span className="session-sidebar__group-count">{group.items.length}</span>
                  </div>
                  <ChevronDown
                    size={13}
                    strokeWidth={2}
                    className={`session-sidebar__group-chevron ${isGroupOpen ? 'session-sidebar__group-chevron--open' : ''}`}
                  />
                </button>

                {isGroupOpen && (
                  <div id={`sidebar-group-${group.id}`} className="session-sidebar__group-drawer">
                    <div className="session-sidebar__nav-list">
                      {group.items.map((item) => {
                        const ItemIcon = item.icon;
                        const isActive = activeView === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            className={`session-sidebar__nav-link ${isActive ? 'session-sidebar__nav-link--active' : ''}`}
                            onClick={() => {
                              if (item.id === 'chat') {
                                onModeChange?.('chat');
                              }
                              onViewChange(item.id);
                            }}
                            title={t(item.titleKey) || item.defaultTitle}
                            aria-current={isActive ? 'page' : undefined}
                          >
                            <ItemIcon size={15} strokeWidth={1.8} className="session-sidebar__nav-icon" />
                            <span className="session-sidebar__nav-text">
                              {t(item.titleKey) || item.defaultTitle}
                            </span>
                            {item.shortcut && (
                              <kbd className="session-sidebar__nav-shortcut">{item.shortcut}</kbd>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 4. Conversation Area: RECENT & PINNED CHATS (Dedicated Independent Scroll Container) */}
      <div className="session-sidebar__chats-section">
        {searchQuery ? (
          <div className="session-sidebar__chats-header">
            <span className="session-sidebar__chats-title">Search Results</span>
            {filteredSessions.length > 0 && (
              <span className="session-sidebar__chats-count">
                {filteredSessions.length}
              </span>
            )}
          </div>
        ) : null}

        {/* History List / Date Grouping / Pinned Section */}
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

          {/* If Search Query Active: Render Search Results List */}
          {searchQuery.trim() ? (
            <ul className="session-sidebar__list">
              {filteredSessions.map((s) => renderSessionItem(s))}
            </ul>
          ) : (
            <>
              {/* PINNED SECTION (renders above Recent when pinned items exist) */}
              {pinnedSessions.length > 0 && (
                <div className="session-sidebar__pinned-section">
                  <button
                    type="button"
                    className="session-sidebar__section-toggle"
                    onClick={togglePinnedCollapsed}
                    aria-expanded={!pinnedCollapsed}
                    aria-label="Toggle pinned conversations"
                  >
                    <div className="session-sidebar__section-toggle-left">
                      <Pin size={11} className="session-sidebar__section-pin-icon" />
                      <span className="session-sidebar__section-title">PINNED</span>
                      <span className="session-sidebar__section-count">{pinnedSessions.length}</span>
                    </div>
                    {pinnedCollapsed ? (
                      <ChevronRight size={13} className="session-sidebar__section-chevron" />
                    ) : (
                      <ChevronDown size={13} className="session-sidebar__section-chevron" />
                    )}
                  </button>

                  {!pinnedCollapsed && (
                    <ul className="session-sidebar__list">
                      {pinnedSessions.map((s) => renderSessionItem(s, true))}
                    </ul>
                  )}

                  <div className="session-sidebar__section-divider" />
                </div>
              )}

              {/* RECENT SECTION (collapsible, with date groupings) */}
              <div className="session-sidebar__recent-section">
                <button
                  type="button"
                  className="session-sidebar__section-toggle"
                  onClick={toggleRecentCollapsed}
                  aria-expanded={!recentCollapsed}
                  aria-label="Toggle recent conversations"
                >
                  <div className="session-sidebar__section-toggle-left">
                    <span className="session-sidebar__section-title">RECENT</span>
                    {recentSessions.length > 0 && (
                      <span className="session-sidebar__section-count">{recentSessions.length}</span>
                    )}
                  </div>
                  {recentCollapsed ? (
                    <ChevronRight size={13} className="session-sidebar__section-chevron" />
                  ) : (
                    <ChevronDown size={13} className="session-sidebar__section-chevron" />
                  )}
                </button>

                {!recentCollapsed && (
                  <>
                    {groupedRecentSessions.map(({ label, items }) => (
                      <div key={label} className="session-sidebar__date-group">
                        <span className="session-sidebar__date-label">{label}</span>
                        <ul className="session-sidebar__list">
                          {items.map((s) => renderSessionItem(s, false))}
                        </ul>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </>
          )}

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
                    <span>{t('common.new_chat')}</span>
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 4. Footer: Account, Language & Upgrade Row */}
      {onViewChange && (
        <div className="session-sidebar__account-row">
          <div className="session-sidebar__lang-wrap" ref={langMenuRef}>
            <button
              type="button"
              className={`session-sidebar__account-link session-sidebar__lang-btn ${langMenuOpen ? 'session-sidebar__account-link--active' : ''}`}
              onClick={() => setLangMenuOpen((v) => !v)}
              title={`${t('common.language')}: ${LOCALES[locale].nativeName}`}
              aria-label={t('common.language')}
              aria-expanded={langMenuOpen}
            >
              <Globe size={15} strokeWidth={1.8} />
              <span className="session-sidebar__lang-label">{LOCALES[locale].nativeName}</span>
            </button>

            {langMenuOpen && (
              <div className="session-sidebar__lang-popover" role="menu">
                <div className="session-sidebar__lang-popover-header">
                  <span>{t('common.language')}</span>
                </div>
                <div className="session-sidebar__lang-popover-list">
                  {locales.map((loc) => (
                    <button
                      key={loc.code}
                      type="button"
                      className={`session-sidebar__lang-popover-item ${locale === loc.code ? 'session-sidebar__lang-popover-item--active' : ''}`}
                      onClick={() => {
                        setLocale(loc.code);
                        setLangMenuOpen(false);
                      }}
                      role="menuitem"
                    >
                      <span className="session-sidebar__lang-flag">{loc.flag}</span>
                      <span className="session-sidebar__lang-name">{loc.nativeName}</span>
                      <span className="session-sidebar__lang-sub">({loc.name})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            className={`session-sidebar__account-link ${activeView === 'usage' ? 'session-sidebar__account-link--active' : ''}`}
            onClick={() => onViewChange('usage')}
            title={t('nav.usage')}
          >
            <BarChart2 size={15} strokeWidth={1.8} />
            <span>{t('nav.usage')}</span>
          </button>
          <button
            type="button"
            className={`session-sidebar__account-link ${activeView === 'billing' ? 'session-sidebar__account-link--active' : ''}`}
            onClick={() => onViewChange('billing')}
            title={t('nav.billing')}
          >
            <Receipt size={15} strokeWidth={1.8} />
            <span>{t('nav.billing')}</span>
          </button>
          <button
            type="button"
            className={`session-sidebar__upgrade-pill ${activeView === 'pricing' ? 'session-sidebar__upgrade-pill--active' : ''}`}
            onClick={() => onViewChange('pricing')}
            title={t('common.upgrade')}
          >
            <Zap size={13} strokeWidth={2.4} />
            <span>{t('common.upgrade')}</span>
          </button>
        </div>
      )}

      {/* Move to Project Modal Dialog */}
      {movingSession && (
        <div
          className="session-sidebar__modal-backdrop"
          onClick={() => setMovingSession(null)}
          role="presentation"
        >
          <div
            className="session-sidebar__modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="move-project-dialog-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="session-sidebar__modal-header">
              <h3 id="move-project-dialog-title" className="session-sidebar__modal-title">
                Move to Project
              </h3>
              <button
                type="button"
                className="session-sidebar__modal-close"
                onClick={() => setMovingSession(null)}
                aria-label="Close dialog"
              >
                <X size={15} />
              </button>
            </div>
            <p className="session-sidebar__modal-desc">
              Select destination project for <strong>&ldquo;{movingSession.title || 'Untitled conversation'}&rdquo;</strong>:
            </p>
            <div className="session-sidebar__project-list" role="listbox">
              {PROJECT_OPTIONS.map((proj) => (
                <button
                  key={proj.id}
                  type="button"
                  className="session-sidebar__project-option"
                  role="option"
                  aria-selected="false"
                  onClick={() => handleAssignProject(movingSession.id, proj.name)}
                >
                  <FolderCheck size={16} className="session-sidebar__project-icon" />
                  <div className="session-sidebar__project-info">
                    <span className="session-sidebar__project-name">{proj.name}</span>
                    <span className="session-sidebar__project-sub">{proj.desc}</span>
                  </div>
                </button>
              ))}
            </div>
            <div className="session-sidebar__modal-actions">
              <button
                type="button"
                className="session-sidebar__modal-cancel"
                onClick={() => setMovingSession(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating feedback toast */}
      {projectToast && (
        <div className="session-sidebar__floating-toast" role="status" aria-live="polite">
          <Check size={14} className="session-sidebar__toast-check" />
          <span>{projectToast}</span>
        </div>
      )}
    </aside>
  );
};
