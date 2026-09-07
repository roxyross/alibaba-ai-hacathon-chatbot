import { useCallback, useMemo, useState } from 'react';
import { AuthProvider, AuthGate, useAuth } from './auth';
import { ChatWindow } from './components/ChatWindow';
import { ChatInput } from './components/ChatInput';
import { FinanceDashboard } from './components/FinanceDashboard/FinanceDashboard';
import { SessionSidebar } from './session';
import { useSessions, type ChatSession, type CreateSessionInput } from './session';
import { useSessionMessages, type ChatMessageRecord } from './chat_history';
import { ModelPicker, type ModelSelection } from './model_provider';
import { useChat } from './hooks/useChat';
import {
  SensitiveActionConfirm,
  useSensitiveConfirm,
} from './components/SensitiveActionConfirm/SensitiveActionConfirm';
import { ScheduledJobsPanel } from './components/ScheduledJobsPanel/ScheduledJobsPanel';
import { EmailSendPanel } from './components/EmailSendPanel/EmailSendPanel';
import { VoiceSession } from './components/VoiceSession/VoiceSession';
import './App.css';

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

const RUNTIME_URL =
  (import.meta as { env: { VITE_RUNTIME_URL?: string } }).env.VITE_RUNTIME_URL ??
  'http://localhost:8000';

export type AppView = 'chat' | 'finance' | 'jobs' | 'email' | 'voice';

export function ChatScreen() {
  const { accessToken, signOut, user } = useAuth();
  const { create } = useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>(
    null,
  );
  const [activeView, setActiveView] = useState<AppView>('chat');

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
  const handleSelectSession = useCallback((s: ChatSession) => {
    setActiveSession(s);
    setModelSelection({ provider: s.provider, model: s.model });
  }, []);

  // "New chat" — clear active session so the picker is required again.
  const handleNewChat = useCallback(() => {
    setActiveSession(null);
    setModelSelection(null);
    setActiveView('chat');
  }, []);

  // After a turn completes in a brand-new (just-created) session, adopt it
  // as the active session so the sidebar highlights it.
  const handleSend = useCallback(
    async (text: string) => {
      if (!modelSelection) return;
      let session = activeSession;
      if (!session) {
        session = await create({
          provider: modelSelection.provider,
          model: modelSelection.model,
        } satisfies CreateSessionInput);
        setActiveSession(session);
      }
      await chat.sendMessage(text);
      // Refresh history once the server has persisted the turn.
      // (A small delay keeps the read from racing the write on slow boxes.)
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
        return [...historyMsgs, ...chat.messages.map(toUiMessage)];
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
        onSelect={(s) => { handleSelectSession(s); setSidebarOpen(false); }}
        onNewChat={() => { handleNewChat(); setSidebarOpen(false); }}
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

            {/* View switcher */}
            <div className="app__views" role="group" aria-label="App views">
              {activeView === 'chat' && (
                <>
                  <button
                    type="button"
                    className="app__view-btn"
                    onClick={() => setActiveView('voice')}
                    title="Voice"
                  >
                    🎙️
                  </button>
                  <button
                    type="button"
                    className="app__view-btn"
                    onClick={() => setActiveView('finance')}
                    title="Finance"
                  >
                    💰
                  </button>
                  <button
                    type="button"
                    className="app__view-btn"
                    onClick={() => setActiveView('jobs')}
                    title="Scheduled Jobs"
                  >
                    ⏰
                  </button>
                  <button
                    type="button"
                    className="app__view-btn"
                    onClick={() => setActiveView('email')}
                    title="Email"
                  >
                    📧
                  </button>
                </>
              )}
              {(activeView === 'finance' || activeView === 'jobs' || activeView === 'email' || activeView === 'voice') && (
                <button
                  type="button"
                  className="app__view-btn"
                  onClick={() => setActiveView('chat')}
                  title="Back to Chat"
                >
                  💬
                </button>
              )}
            </div>

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
          <FinanceDashboard accessToken={accessToken} />
        ) : activeView === 'jobs' ? (
          <ScheduledJobsPanel accessToken={accessToken} />
        ) : activeView === 'email' ? (
          <EmailSendPanel
            accessToken={accessToken}
            onConfirmRequired={(token, skill, action) => {
              triggerConfirmation(token, skill, action);
            }}
          />
        ) : activeView === 'voice' ? (
          <VoiceSession accessToken={accessToken} />
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
            />
            <ChatInput
              onSend={handleSend}
              isStreaming={chat.isStreaming}
              disabledNoModel={!modelSelection}
              leftSlot={
                <ModelPicker value={modelSelection} onChange={setModelSelection} />
              }
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
