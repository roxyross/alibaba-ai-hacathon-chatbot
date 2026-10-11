import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Search,
  Mic,
  Sparkles,
  Zap,
  Users,
  Smartphone,
  Globe,
  Code2,
  Sliders,
  ShieldCheck,
  FileText,
  Calendar,
  ArrowRight,
  Sun,
  Moon,
  Trash2,
  HardDrive,
  Cpu,
  Bookmark,
  Volume2,
} from 'lucide-react';
import { useI18n, type Locale, type LocaleConfig } from '../../i18n';
import './RoxyCommandBar.css';

export interface CommandItem {
  id: string;
  title: string;
  subtitle?: string;
  category: 'quick' | 'studios' | 'device' | 'system';
  icon: React.ReactNode;
  badge?: string;
  shortcut?: string;
  action: () => void;
}

export interface RoxyCommandBarProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateView: (view: string) => void;
  onSendChatQuery: (query: string) => void;
  onOpenNewTask: () => void;
  onEnterCowork: () => void;
  onStartVoice: () => void;
  onToggleTheme?: () => void;
  currentTheme?: 'dark' | 'light';
  onClearChat?: () => void;
}

export const RoxyCommandBar: React.FC<RoxyCommandBarProps> = ({
  isOpen,
  onClose,
  onNavigateView,
  onSendChatQuery,
  onOpenNewTask,
  onEnterCowork,
  onStartVoice,
  onToggleTheme,
  currentTheme,
  onClearChat,
}) => {
  const { locale, setLocale, dir, isRtl, locales } = useI18n();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus input automatically upon opening
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Master command registry
  const allCommands = useMemo<CommandItem[]>(() => {
    const list: CommandItem[] = [
      // 1. Quick Actions
      {
        id: 'new-task',
        title: 'Launch Autonomous Task',
        subtitle: 'Configure goal, category, strategy & target device',
        category: 'quick',
        icon: <Zap size={18} className="command-icon--gold" />,
        badge: 'Agentic',
        shortcut: 'Ctrl+N',
        action: () => {
          onClose();
          onOpenNewTask();
        },
      },
      {
        id: 'cowork-mode',
        title: 'Enter Cowork Workspace',
        subtitle: 'Split-screen pair copilot with synchronized code/browser surface',
        category: 'quick',
        icon: <Users size={18} className="command-icon--cyan" />,
        badge: 'Pair AI',
        action: () => {
          onClose();
          onEnterCowork();
        },
      },
      {
        id: 'voice-session',
        title: 'Start Live Voice Session',
        subtitle: 'Bidirectional low-latency speech dialogue with Roxy',
        category: 'quick',
        icon: <Mic size={18} className="command-icon--emerald" />,
        badge: 'Real-time',
        shortcut: 'Ctrl+V',
        action: () => {
          onClose();
          onStartVoice();
        },
      },

      // 2. Device & Universal App Control
      {
        id: 'device-hub',
        title: 'Device Hub & Fleet',
        subtitle: 'Manage connected desktop, Android, iOS devices & permissions',
        category: 'device',
        icon: <Smartphone size={18} className="command-icon--purple" />,
        badge: 'Phase 19',
        action: () => {
          onClose();
          onNavigateView('device_hub');
        },
      },
      {
        id: 'app-catalog',
        title: 'Application Catalog & Scan',
        subtitle: 'Inspect installed software, discovered tools, and MCP endpoints',
        category: 'device',
        icon: <HardDrive size={18} className="command-icon--blue" />,
        action: () => {
          onClose();
          onNavigateView('device_hub');
        },
      },
      {
        id: 'permissions-matrix',
        title: 'Device Permissions & Security Matrix',
        subtitle: 'Audit accessibility, screen recording, and file system rights',
        category: 'device',
        icon: <ShieldCheck size={18} className="command-icon--rose" />,
        action: () => {
          onClose();
          onNavigateView('device_hub');
        },
      },

      // 3. Studios & Workspaces
      {
        id: 'coding-studio',
        title: 'Coding Studio',
        subtitle: 'Multi-language scratchpad, code generation & execution',
        category: 'studios',
        icon: <Code2 size={18} className="command-icon--blue" />,
        action: () => {
          onClose();
          onNavigateView('coding');
        },
      },
      {
        id: 'browser-studio',
        title: 'Browser Automation Studio',
        subtitle: 'Autonomous web navigation, DOM extraction & scraping',
        category: 'studios',
        icon: <Globe size={18} className="command-icon--teal" />,
        action: () => {
          onClose();
          onNavigateView('browser');
        },
      },
      {
        id: 'connectors-hub',
        title: 'Connectors & MCP Hub',
        subtitle: 'Model Context Protocol servers, APIs & database adapters',
        category: 'studios',
        icon: <Cpu size={18} className="command-icon--violet" />,
        action: () => {
          onClose();
          onNavigateView('connectors');
        },
      },
      {
        id: 'control-center',
        title: 'System Control Center',
        subtitle: 'System metrics, process monitors & runtime settings',
        category: 'studios',
        icon: <Sliders size={18} className="command-icon--indigo" />,
        action: () => {
          onClose();
          onNavigateView('control_center');
        },
      },
      {
        id: 'trust-center',
        title: 'Trust & Privacy Center',
        subtitle: 'Zero data retention toggles, encryption & audit trails',
        category: 'studios',
        icon: <ShieldCheck size={18} className="command-icon--green" />,
        action: () => {
          onClose();
          onNavigateView('trust_center');
        },
      },
      {
        id: 'memory-studio',
        title: 'Memory & Knowledge Vault',
        subtitle: 'Long-term user preferences, semantic memory & documents',
        category: 'studios',
        icon: <Bookmark size={18} className="command-icon--amber" />,
        action: () => {
          onClose();
          onNavigateView('memory');
        },
      },
      {
        id: 'calendar-view',
        title: 'Calendar & Event Scheduler',
        subtitle: 'AI-assisted appointments, reminders & sync',
        category: 'studios',
        icon: <Calendar size={18} className="command-icon--sky" />,
        action: () => {
          onClose();
          onNavigateView('calendar');
        },
      },
      {
        id: 'doc-upload',
        title: 'Document Analysis & OCR',
        subtitle: 'Extract text, tables, and insights from PDFs and images',
        category: 'studios',
        icon: <FileText size={18} className="command-icon--pink" />,
        action: () => {
          onClose();
          onNavigateView('documents');
        },
      },

      // 4. System & Interface
      {
        id: 'toggle-theme',
        title: `Switch to ${currentTheme === 'dark' ? 'Light' : 'Dark'} Mode`,
        subtitle: 'Toggle high-contrast themes and color temperature',
        category: 'system',
        icon: currentTheme === 'dark' ? <Sun size={18} className="command-icon--gold" /> : <Moon size={18} className="command-icon--indigo" />,
        action: () => {
          onToggleTheme?.();
          onClose();
        },
      },
      {
        id: 'clear-chat',
        title: 'Clear Current Chat History',
        subtitle: 'Reset conversation messages for this session',
        category: 'system',
        icon: <Trash2 size={18} className="command-icon--rose" />,
        action: () => {
          onClearChat?.();
          onClose();
        },
      },
    ];

    return list;
  }, [
    currentTheme,
    onClearChat,
    onClose,
    onEnterCowork,
    onNavigateView,
    onOpenNewTask,
    onStartVoice,
    onToggleTheme,
  ]);

  // Filter commands by query string
  const filteredCommands = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allCommands;
    return allCommands.filter(
      (cmd) =>
        cmd.title.toLowerCase().includes(q) ||
        (cmd.subtitle && cmd.subtitle.toLowerCase().includes(q)) ||
        cmd.category.toLowerCase().includes(q) ||
        (cmd.badge && cmd.badge.toLowerCase().includes(q)),
    );
  }, [allCommands, query]);

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev < filteredCommands.length - 1 ? prev + 1 : 0,
      );
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev > 0 ? prev - 1 : filteredCommands.length - 1,
      );
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredCommands.length > 0 && filteredCommands[selectedIndex]) {
        filteredCommands[selectedIndex].action();
      } else if (query.trim()) {
        // Send direct query to Roxy Chat
        onClose();
        onSendChatQuery(query.trim());
      }
    }
  };

  // Scroll active item into view
  useEffect(() => {
    if (listRef.current) {
      const activeEl = listRef.current.querySelector<HTMLElement>(
        `[data-cmd-index="${selectedIndex}"]`,
      );
      if (activeEl) {
        activeEl.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <div
      className="roxy-command-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      dir={dir}
    >
      <div className="roxy-command-palette">
        {/* Top Header & Multilingual Selector */}
        <div className="roxy-command-palette__top-bar">
          <div className="roxy-command-palette__brand">
            <div className="roxy-command-palette__brand-icon">
              <Sparkles size={16} />
            </div>
            <span className="roxy-command-palette__brand-title">ROXY COMMAND</span>
            <span className="roxy-command-palette__version-badge">v2.0 Universal</span>
          </div>

          {/* Multilingual Selector */}
          <div className="roxy-command-palette__locales" title="Switch UI & Prompt Language">
            {locales.map((loc: LocaleConfig) => (
              <button
                key={loc.code}
                type="button"
                className={`roxy-command-palette__locale-btn ${
                  locale === loc.code ? 'roxy-command-palette__locale-btn--active' : ''
                }`}
                onClick={() => setLocale(loc.code as Locale)}
              >
                <span className="roxy-command-palette__locale-flag">{loc.flag}</span>
                <span className="roxy-command-palette__locale-name">{loc.nativeName}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Omnibar Input Bar */}
        <div className="roxy-command-palette__input-wrap">
          <Search size={20} className="roxy-command-palette__search-icon" />
          <input
            ref={inputRef}
            type="text"
            className="roxy-command-palette__input"
            placeholder={
              locale === 'ur'
                ? 'روکسی سے کچھ بھی پوچھیں، کام شروع کریں یا اسٹوڈیو کھولیں... (Enter دبائیں)'
                : locale === 'ar'
                ? 'اسأل روكسي، أطلق مهمة جديدة أو افتح استوديو... (اضغط Enter)'
                : 'Ask Roxy anything, launch a task, or open any studio... (Press Enter)'
            }
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
          />
          {query.trim() && (
            <button
              type="button"
              className="roxy-command-palette__send-btn"
              onClick={() => {
                onClose();
                onSendChatQuery(query.trim());
              }}
              title="Send to Roxy AI Chat"
            >
              <span>{isRtl ? 'پوچھیں' : 'Ask'}</span>
              <ArrowRight size={14} />
            </button>
          )}
          <button
            type="button"
            className="roxy-command-palette__mic-btn"
            onClick={() => {
              onClose();
              onStartVoice();
            }}
            title="Launch Voice Mode (Ctrl+V)"
          >
            <Mic size={17} />
          </button>
          <kbd className="roxy-command-palette__kbd-esc" onClick={onClose}>
            ESC
          </kbd>
        </div>

        {/* Quick Launch Cards (When query is empty or broad) */}
        {!query.trim() && (
          <div className="roxy-command-palette__quick-grid">
            <button
              type="button"
              className="roxy-command-card roxy-command-card--gold"
              onClick={() => {
                onClose();
                onOpenNewTask();
              }}
            >
              <div className="roxy-command-card__icon-box">
                <Zap size={18} />
              </div>
              <div className="roxy-command-card__info">
                <span className="roxy-command-card__title">
                  {locale === 'ur' ? 'نیا ٹاسک شروع کریں' : locale === 'ar' ? 'مهمة جديدة' : 'New Task'}
                </span>
                <span className="roxy-command-card__desc">
                  {locale === 'ur'
                    ? 'خود مختار ملٹی اسٹیپ ایجنٹ'
                    : locale === 'ar'
                    ? 'وكيل مستقل متعدد الخطوات'
                    : 'Autonomous multi-step agent'}
                </span>
              </div>
            </button>

            <button
              type="button"
              className="roxy-command-card roxy-command-card--cyan"
              onClick={() => {
                onClose();
                onEnterCowork();
              }}
            >
              <div className="roxy-command-card__icon-box">
                <Users size={18} />
              </div>
              <div className="roxy-command-card__info">
                <span className="roxy-command-card__title">
                  {locale === 'ur' ? 'کو-ورک موڈ' : locale === 'ar' ? 'وضع العمل المشترك' : 'Cowork Mode'}
                </span>
                <span className="roxy-command-card__desc">
                  {locale === 'ur'
                    ? 'مشترکہ اسکرین اور جوڑی کوڈنگ'
                    : locale === 'ar'
                    ? 'شاشة مشتركة ومساعد ثنائي'
                    : 'Pair copilot with split screen'}
                </span>
              </div>
            </button>

            <button
              type="button"
              className="roxy-command-card roxy-command-card--emerald"
              onClick={() => {
                onClose();
                onStartVoice();
              }}
            >
              <div className="roxy-command-card__icon-box">
                <Volume2 size={18} />
              </div>
              <div className="roxy-command-card__info">
                <span className="roxy-command-card__title">
                  {locale === 'ur' ? 'آواز کا سیشن' : locale === 'ar' ? 'جلسة صوتية' : 'Voice Session'}
                </span>
                <span className="roxy-command-card__desc">
                  {locale === 'ur'
                    ? 'براہ راست بات چیت اور ڈکٹیشن'
                    : locale === 'ar'
                    ? 'محادثة صوتية فورية'
                    : 'Bidirectional low-latency speech'}
                </span>
              </div>
            </button>

            <button
              type="button"
              className="roxy-command-card roxy-command-card--purple"
              onClick={() => {
                onClose();
                onNavigateView('device_hub');
              }}
            >
              <div className="roxy-command-card__icon-box">
                <Smartphone size={18} />
              </div>
              <div className="roxy-command-card__info">
                <span className="roxy-command-card__title">
                  {locale === 'ur' ? 'ڈیوائس ہب' : locale === 'ar' ? 'مركز الأجهزة' : 'Device Hub'}
                </span>
                <span className="roxy-command-card__desc">
                  {locale === 'ur'
                    ? 'منسلک آلات اور اجازتیں'
                    : locale === 'ar'
                    ? 'الأجهزة المتصلة والصلاحيات'
                    : 'Fleet, Apps & Permissions'}
                </span>
              </div>
            </button>
          </div>
        )}

        {/* Command Search Results List */}
        <div className="roxy-command-palette__list" ref={listRef}>
          {filteredCommands.length > 0 ? (
            filteredCommands.map((cmd, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={cmd.id}
                  data-cmd-index={idx}
                  className={`roxy-command-item ${
                    isSelected ? 'roxy-command-item--selected' : ''
                  }`}
                  onClick={cmd.action}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div className="roxy-command-item__icon-wrapper">{cmd.icon}</div>
                  <div className="roxy-command-item__content">
                    <div className="roxy-command-item__title-row">
                      <span className="roxy-command-item__title">{cmd.title}</span>
                      {cmd.badge && (
                        <span className="roxy-command-item__badge">{cmd.badge}</span>
                      )}
                    </div>
                    {cmd.subtitle && (
                      <span className="roxy-command-item__subtitle">
                        {cmd.subtitle}
                      </span>
                    )}
                  </div>
                  <div className="roxy-command-item__action-hint">
                    {cmd.shortcut && (
                      <kbd className="roxy-command-item__shortcut">{cmd.shortcut}</kbd>
                    )}
                    <ArrowRight size={14} className="roxy-command-item__arrow" />
                  </div>
                </div>
              );
            })
          ) : (
            <div className="roxy-command-palette__empty">
              <Sparkles size={24} className="roxy-command-palette__empty-icon" />
              <p className="roxy-command-palette__empty-text">
                No matching studio command for &ldquo;{query}&rdquo;
              </p>
              <button
                type="button"
                className="roxy-command-palette__empty-action"
                onClick={() => {
                  onClose();
                  onSendChatQuery(query.trim());
                }}
              >
                <span>Ask Roxy AI directly</span>
                <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>

        {/* Footer shortcuts helper */}
        <div className="roxy-command-palette__footer">
          <div className="roxy-command-palette__keys-hint">
            <span>
              <kbd>↑</kbd> <kbd>↓</kbd> Navigate
            </span>
            <span>
              <kbd>↵</kbd> Select / Ask
            </span>
            <span>
              <kbd>ESC</kbd> Close
            </span>
          </div>
          <span className="roxy-command-palette__footer-brand">
            ROXY Universal OS • 25+ Studios Ready
          </span>
        </div>
      </div>
    </div>
  );
};
