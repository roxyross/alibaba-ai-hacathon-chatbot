import { useCallback, useEffect, useMemo, useState } from 'react';
import { AuthProvider, AuthGate, useAuth } from './auth';
import { ChatWindow } from './components/ChatWindow';
import { FinanceDashboard } from './components/FinanceDashboard/FinanceDashboard';
import { SessionSidebar, type AppView } from './session';
import { useSessions, type ChatSession, type CreateSessionInput } from './session';
import { useSessionMessages, type ChatMessageRecord } from './chat_history';
import { type ModelSelection } from './model_provider';
import { useChat } from './hooks/useChat';
import {
  SensitiveActionConfirm,
  useSensitiveConfirm,
} from './components/SensitiveActionConfirm/SensitiveActionConfirm';
import { ScheduledJobsPanel } from './components/ScheduledJobsPanel/ScheduledJobsPanel';
import { EmailSendPanel } from './components/EmailSendPanel/EmailSendPanel';
import { VoiceSession } from './components/VoiceSession/VoiceSession';
import { DocumentUpload } from './components/DocumentUpload';
import { Calculator } from './components/Calculator/Calculator';
import { CalendarView } from './components/Calendar/CalendarView';
import './App.css';
import './components/DocumentUpload/DocumentUpload.css';

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

const RUNTIME_URL =
  (import.meta as { env: { VITE_RUNTIME_URL?: string } }).env.VITE_RUNTIME_URL ||
  API_BASE;

export function ChatScreen() {
  const { accessToken, signOut, user } = useAuth();
  const {
    sessions,
    loading: sessionsLoading,
    error: sessionsError,
    refresh: refreshSessions,
    create: createSession,
    rename: renameSession,
    remove: removeSession,
  } = useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  // Dual-mode workflow: 'chat' for general conversation/search, 'task' for coding tasks
  const [mode, setMode] = useState<'chat' | 'task'>('chat');

  // Default to Google Gemini 2.0 Flash
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>({
    provider: 'gemini',
    model: 'gemini-2.0-flash',
  });
  const [activeView, setActiveView] = useState<AppView>('chat');

  // Auth modal state for on-demand sign in / sign up & trial limit prompts
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState<'signin' | 'signup'>('signin');
  const [authModalMessage, setAuthModalMessage] = useState<string | null>(null);

  const openAuth = useCallback((targetMode: 'signin' | 'signup', message?: string) => {
    setAuthModalMode(targetMode);
    setAuthModalMessage(message ?? null);
    setIsAuthModalOpen(true);
  }, []);

  // Light / Dark mode toggle with persistent state (defaulting to soft off-white light mode)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('roxy-theme');
    return saved === 'dark' ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('roxy-theme', theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  // Desktop sidebar collapse state
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    return localStorage.getItem('roxy-sidebar-collapsed') === 'true';
  });

  // Global Ctrl+K / Cmd+K shortcut to open sidebar search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSidebarCollapsed(false);
        setSidebarOpen(true);
        setTimeout(() => {
          const input = document.querySelector<HTMLInputElement>('.session-sidebar__search-input');
          input?.focus();
        }, 60);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // History for the active session, if any.
  const history = useSessionMessages(activeSession?.id ?? null);

  // Live chat state with fast token-by-token SSE streaming.
  const isRuntime = modelSelection?.provider === 'runtime';
  const chat = useChat({
    apiBase: isRuntime ? undefined : API_BASE,
    runtimeUrl: isRuntime ? RUNTIME_URL : undefined,
    provider: modelSelection?.provider,
    model: modelSelection?.model,
    sessionId: activeSession?.id ?? undefined,
    accessToken,
    agentOverride: mode === 'task' ? 'code_generation' : undefined,
    streaming: true,
  });

  // Sensitive action confirmation
  const {
    pendingConfirmation,
    triggerConfirmation,
    clearConfirmation,
    confirm: confirmSensitive,
  } = useSensitiveConfirm({ accessToken });

  // Mobile sidebar visibility
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // When switching between Chat and Task modes via sidebar toggle
  const handleModeChange = useCallback(
    (newMode: 'chat' | 'task') => {
      setMode(newMode);
      chat.clearMessages();
      setActiveSession(null);
      setModelSelection((prev) => prev ?? { provider: 'runtime', model: 'coordinator' });
      setActiveView('chat');
      void refreshSessions();
    },
    [chat, refreshSessions],
  );

  // When the user clicks a past session, adopt its model and mode.
  const handleSelectSession = useCallback(
    (s: ChatSession) => {
      chat.clearMessages();
      setActiveSession(s);
      const sessType = s.session_type === 'task' || s.title?.startsWith('[Task]') || s.model === 'code_generation' ? 'task' : 'chat';
      setMode(sessType);
      setModelSelection({ provider: s.provider, model: s.model });
      setActiveView('chat');
    },
    [chat],
  );

  // "New chat" — clear active session, set mode to 'chat', and switch back to chat view.
  const handleNewChat = useCallback(() => {
    setMode('chat');
    chat.clearMessages();
    setActiveSession(null);
    setModelSelection((prev) => prev ?? { provider: 'runtime', model: 'coordinator' });
    setActiveView('chat');
    void history.reload();
    void refreshSessions();
  }, [chat, history, refreshSessions]);

  // "New task" — clear active session, set mode to 'task' (for coding), and switch back to chat view.
  const handleNewTask = useCallback(() => {
    if (!accessToken && !user) {
      openAuth('signin', 'Please sign in to use Task & Code Generation mode.');
      return;
    }
    setMode('task');
    chat.clearMessages();
    setActiveSession(null);
    setModelSelection((prev) => prev ?? { provider: 'runtime', model: 'coordinator' });
    setActiveView('chat');
    void history.reload();
    void refreshSessions();
  }, [accessToken, user, openAuth, chat, history, refreshSessions]);

  // After a turn completes in a brand-new session, adopt it
  // as the active session so the sidebar highlights it.
  const handleSend = useCallback(
    async (text: string) => {
      // Free 1-prompt preview check for unauthenticated guests
      if (!accessToken && !user) {
        const GUEST_PROMPT_KEY = 'roxy_guest_prompt_count';
        const count = parseInt(localStorage.getItem(GUEST_PROMPT_KEY) || '0', 10);
        if (count >= 1) {
          openAuth(
            'signin',
            "You have used your 1 free preview prompt! Sign in with Google, GitHub, or Email to continue chatting with ROXY AI.",
          );
          return;
        }
        localStorage.setItem(GUEST_PROMPT_KEY, String(count + 1));
      }

      const activeModel = modelSelection ?? { provider: 'runtime', model: 'coordinator' };
      let session = activeSession;
      if (!session && (accessToken || user)) {
        try {
          const initialTitle = mode === 'task'
            ? `[Task] ${text.trim().slice(0, 32)}`
            : (text.trim().slice(0, 36) || 'New chat');
          session = await createSession({
            provider: activeModel.provider,
            model: activeModel.model,
            session_type: mode,
            title: initialTitle,
          } satisfies CreateSessionInput);
          setActiveSession(session);
          void refreshSessions();
        } catch {
          // If session creation fails, proceed with ephemeral chat
        }
      }
      await chat.sendMessage(text, session?.id);
      // Refresh history and sessions once the server has persisted the turn.
      if (session?.id) {
        window.setTimeout(() => {
          void history.reload();
          void refreshSessions();
        }, 500);
      }
    },
    [activeSession, modelSelection, createSession, chat, history, mode, accessToken, user, openAuth, refreshSessions],
  );

  // The messages the chat window renders: persisted history + the in-flight
  // streaming assistant message (if any). History is shown immediately when
  // switching sessions; live state is layered on top while streaming.
  const renderedMessages = useMemo(() => {
    if (activeSession) {
      const historyMsgs = history.messages.map(toUiMessage);
      if (chat.messages.length > 0) {
        if (historyMsgs.length >= chat.messages.length) {
          return historyMsgs;
        }
        return [...historyMsgs, ...chat.messages.slice(historyMsgs.length).map(toUiMessage)];
      }
      return historyMsgs;
    }
    return chat.messages.map(toUiMessage);
  }, [activeSession, history.messages, chat.messages]);

  return (
    <div className={`app${sidebarOpen ? ' app--sidebar-open' : ''}`}>
      {/* Mobile overlay behind sidebar */}
      {sidebarOpen && (
        <div
          className="app__sidebar-overlay"
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <SessionSidebar
        isCollapsed={sidebarCollapsed}
        onCloseSidebar={() => {
          setSidebarCollapsed(true);
          localStorage.setItem('roxy-sidebar-collapsed', 'true');
        }}
        activeSessionId={activeSession?.id ?? null}
        activeView={activeView}
        mode={mode}
        sessions={sessions}
        loading={sessionsLoading}
        error={sessionsError}
        onRename={renameSession}
        onRemove={removeSession}
        onModeChange={handleModeChange}
        onSelect={(s) => { handleSelectSession(s); setSidebarOpen(false); }}
        onNewChat={() => { handleNewChat(); setSidebarOpen(false); }}
        onNewTask={() => { handleNewTask(); setSidebarOpen(false); }}
        onViewChange={(view) => {
          if (!accessToken && !user && view !== 'chat') {
            const viewLabels: Record<AppView, string> = {
              chat: 'Chat',
              finance: 'Finance Dashboard',
              jobs: 'Scheduled Jobs',
              email: 'Email Sending',
              voice: 'Voice Mode',
              documents: 'Document Upload',
              calculator: 'Calculator',
              calendar: 'Calendar View',
            };
            openAuth('signin', `Please sign in to access ${viewLabels[view] || 'this feature'}.`);
            return;
          }
          setActiveView(view);
          setSidebarOpen(false);
        }}
      />

      <div className="app__main">
        <header className="app__header">
          <div className="app__header-left">
            <button
              type="button"
              className="app__hamburger"
              aria-label="Toggle sidebar"
              onClick={() => setSidebarOpen((v) => !v)}
            >
              {sidebarOpen ? (
                /* X mark */
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M4 4l12 12M16 4L4 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              ) : (
                /* Hamburger */
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              )}
            </button>

            {/* Clear Open Sidebar button when closed/collapsed */}
            {sidebarCollapsed && (
              <button
                type="button"
                className="app__open-sidebar-btn"
                onClick={() => {
                  setSidebarCollapsed(false);
                  localStorage.setItem('roxy-sidebar-collapsed', 'false');
                }}
                title="Open Sidebar"
                aria-label="Open Sidebar"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                  <line x1="9" y1="3" x2="9" y2="21"/>
                  <polyline points="13 9 16 12 13 15"/>
                </svg>
                <span>Open Sidebar</span>
              </button>
            )}

            <h1 className="app__title">
              ROXY <span>AI</span>
            </h1>

            {/* Prominent Search button in top bar */}
            <button
              type="button"
              className="app__header-search-btn"
              onClick={() => {
                setSidebarCollapsed(false);
                setSidebarOpen(true);
                setTimeout(() => {
                  const input = document.querySelector<HTMLInputElement>('.session-sidebar__search-input');
                  input?.focus();
                }, 60);
              }}
              title="Search previous conversations & messages (Ctrl+K)"
              aria-label="Search conversations"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/>
                <line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <span className="app__header-search-text">Search chats…</span>
              <kbd className="app__header-search-kbd">⌘K</kbd>
            </button>
          </div>
          <div className="app__header-right">
            {/* Light / Dark Mode Toggle */}
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={toggleTheme}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>

            {user ? (
              <>
                <span className="app__user">{user.email}</span>
                <button
                  type="button"
                  className="app__signout"
                  onClick={() => {
                    signOut();
                    handleNewChat();
                  }}
                >
                  Sign out
                </button>
              </>
            ) : (
              <div className="app__auth-actions">
                <button
                  type="button"
                  className="app__signin-btn"
                  onClick={() => openAuth('signin')}
                  title="Sign in to your account"
                >
                  Sign In
                </button>
                <button
                  type="button"
                  className="app__signup-btn"
                  onClick={() => openAuth('signup')}
                  title="Create a free account"
                >
                  Sign Up
                </button>
              </div>
            )}
          </div>
        </header>

        {activeView === 'finance' ? (
          <FinanceDashboard accessToken={accessToken} onBack={() => setActiveView('chat')} />
        ) : activeView === 'jobs' ? (
          <ScheduledJobsPanel accessToken={accessToken} onBack={() => setActiveView('chat')} />
        ) : activeView === 'email' ? (
          <EmailSendPanel
            accessToken={accessToken}
            onBack={() => setActiveView('chat')}
            onConfirmRequired={(token, skill, action) => {
              triggerConfirmation(token, skill, action);
            }}
          />
        ) : activeView === 'voice' ? (
          <VoiceSession accessToken={accessToken} onBack={() => setActiveView('chat')} />
        ) : activeView === 'documents' ? (
          <DocumentUpload
            accessToken={accessToken}
            runtimeUrl={isRuntime ? RUNTIME_URL : undefined}
            onBack={() => setActiveView('chat')}
            onUploadDone={(_result) => {
              // After upload, user can ask about the document
              setActiveView('chat');
            }}
          />
        ) : activeView === 'calculator' ? (
          <Calculator
            accessToken={accessToken}
            onBack={() => setActiveView('chat')}
            onSendToChat={(text) => handleSend(text)}
          />
        ) : activeView === 'calendar' ? (
          <CalendarView
            accessToken={accessToken}
            onBack={() => setActiveView('chat')}
            onScheduleWithAI={(prompt) => {
              setActiveView('chat');
              handleSend(prompt);
            }}
          />
        ) : (
          <div className="app__chat">
            <ChatWindow
              messages={renderedMessages}
              attribution={chat.attribution}
              isStreaming={chat.isStreaming}
              error={chat.error}
              needsClarification={chat.needsClarification}
              nextActions={chat.nextActions}
              onSend={handleSend}
              onStop={chat.abort}
              modelSelection={modelSelection}
              onModelChange={setModelSelection}
              onVoiceClick={() => {
                if (!accessToken && !user) {
                  openAuth('signin', 'Please sign in to access Voice Mode.');
                  return;
                }
                setActiveView('voice');
              }}
              onAttachmentClick={() => {
                if (!accessToken && !user) {
                  openAuth('signin', 'Please sign in to upload and analyze documents.');
                  return;
                }
                setActiveView('documents');
              }}
              disabledNoModel={!modelSelection}
              mode={mode}
              onNavigateView={setActiveView}
            />
          </div>
        )}
      </div>

      {/* Sensitive action confirmation modal */}
      <SensitiveActionConfirm
        pending={pendingConfirmation}
        onConfirm={async (token: string) => {
          await confirmSensitive(token);
        }}
        onCancel={clearConfirmation}
      />

      {/* On-demand Authentication Modal */}
      <AuthGate
        isModal={true}
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        bannerMessage={authModalMessage}
        mode={authModalMode}
      />
    </div>
  );
}

function toUiMessage(
  m: { role: 'user' | 'assistant'; content: string } | ChatMessageRecord,
) {
  return { role: m.role as 'user' | 'assistant', content: m.content };
}

export function App() {
  return (
    <AuthProvider>
      <ChatScreen />
    </AuthProvider>
  );
}
