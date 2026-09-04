import { useCallback, useMemo, useState } from 'react';
import { AuthProvider, AuthGate, useAuth } from './auth';
import { ChatWindow } from './components/ChatWindow';
import { ChatInput } from './components/ChatInput';
import { SessionSidebar } from './session';
import { useSessions, type ChatSession, type CreateSessionInput } from './session';
import { useSessionMessages, type ChatMessageRecord } from './chat_history';
import { ModelPicker, type ModelSelection } from './model_provider';
import { useChat } from './hooks/useChat';
import './App.css';

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

export function ChatScreen() {
  const { accessToken, signOut, user } = useAuth();
  const { create } = useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>(
    null,
  );

  // History for the active session, if any.
  const history = useSessionMessages(activeSession?.id ?? null);

  // Live chat state. Re-initialized whenever the session changes.
  const chat = useChat({
    apiBase: API_BASE,
    provider: modelSelection?.provider,
    model: modelSelection?.model,
    sessionId: activeSession?.id ?? undefined,
    accessToken,
  });

  // When the user clicks a past session, adopt its model and let history load.
  const handleSelectSession = useCallback((s: ChatSession) => {
    setActiveSession(s);
    setModelSelection({ provider: s.provider, model: s.model });
  }, []);

  // "New chat" — clear active session so the picker is required again.
  const handleNewChat = useCallback(() => {
    setActiveSession(null);
    setModelSelection(null);
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
    <div className="app">
      <SessionSidebar
        activeSessionId={activeSession?.id ?? null}
        onSelect={handleSelectSession}
        onNewChat={handleNewChat}
      />

      <div className="app__main">
        <header className="app__header">
          <h1 className="app__title">
            ROXY <span>AI</span>
          </h1>
          <div className="app__header-right">
            {user && <span className="app__user">{user.email}</span>}
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

        <div className="app__chat">
          <ChatWindow
            messages={renderedMessages}
            attribution={chat.attribution}
            isStreaming={chat.isStreaming}
            error={chat.error}
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
      </div>
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
