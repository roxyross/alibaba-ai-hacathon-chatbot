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
import './App.css';
import './components/DocumentUpload/DocumentUpload.css';

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

const RUNTIME_URL =
  (import.meta as { env: { VITE_RUNTIME_URL?: string } }).env.VITE_RUNTIME_URL ??
  'http://localhost:8000';

export function ChatScreen() {
  const { accessToken, signOut, user } = useAuth();
  const { create } = useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  // Default to Runtime Coordinator so buttons and prompt cards immediately work without blocking
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>({
    provider: 'runtime',
    model: 'coordinator',
  });
  const [activeView, setActiveView] = useState<AppView>('chat');

  // Light / Dark mode toggle with persistent state
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('roxy-theme');
    return saved === 'light' || saved === 'dark' ? saved : 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('roxy-theme', theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  // History for the active session, if any.
  const history = useSessionMessages(activeSession?.id ?? null);

  // Live chat state. Re-initialized whenever the session changes.
  const isRuntime = modelSelection?.provider === 'runtime';
  const chat = useChat({
    apiBase: isRuntime ? undefined : API_BASE,
    runtimeUrl: isRuntime ? RUNTIME_URL : undefined,
    provider: modelSelection?.provider,
    model: modelSelection?.model,
    sessionId: activeSession?.id ?? undefined,
    accessToken,
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

  // When the user clicks a past session, adopt its model and let history load.
  const handleSelectSession = useCallback(
    (s: ChatSession) => {
      chat.clearMessages();
      setActiveSession(s);
      setModelSelection({ provider: s.provider, model: s.model });
      setActiveView('chat');
    },
    [chat],
  );

  // "New chat" — clear active session and in-flight messages, keep selected model, and switch back to chat view.
  const handleNewChat = useCallback(() => {
    chat.clearMessages();
    setActiveSession(null);
    setModelSelection((prev) => prev ?? { provider: 'runtime', model: 'coordinator' });
    setActiveView('chat');
    void history.reload();
  }, [chat, history]);

  // After a turn completes in a brand-new (just-created) session, adopt it
  // as the active session so the sidebar highlights it.
  const handleSend = useCallback(
    async (text: string) => {
      const activeModel = modelSelection ?? { provider: 'runtime', model: 'coordinator' };
      let session = activeSession;
      if (!session) {
        session = await create({
          provider: activeModel.provider,
          model: activeModel.model,
        } satisfies CreateSessionInput);
        setActiveSession(session);
      }
      await chat.sendMessage(text, session?.id);
      // Refresh history once the server has persisted the turn.
      window.setTimeout(() => {
        void history.reload();
      }, 500);
    },
    [activeSession, modelSelection, create, chat, history],
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
        activeSessionId={activeSession?.id ?? null}
        activeView={activeView}
        onSelect={(s) => { handleSelectSession(s); setSidebarOpen(false); }}
        onNewChat={() => { handleNewChat(); setSidebarOpen(false); }}
        onViewChange={(view) => { setActiveView(view); setSidebarOpen(false); }}
      />

      <div className="app__main">
        <header className="app__header">
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
          <h1 className="app__title">
            ROXY <span>AI</span>
          </h1>
          <div className="app__header-right">
            {user && <span className="app__user">{user.email}</span>}

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
              modelSelection={modelSelection}
              onModelChange={setModelSelection}
              onVoiceClick={() => setActiveView('voice')}
              onAttachmentClick={() => setActiveView('documents')}
              disabledNoModel={!modelSelection}
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
      <AuthGate>
        <ChatScreen />
      </AuthGate>
    </AuthProvider>
  );
}
