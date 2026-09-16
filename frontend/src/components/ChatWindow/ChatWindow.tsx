/* ChatWindow — Modern ChatGPT/Claude Style Chat Interface */

import React, { useCallback, useRef } from 'react';
import { ChatMessage } from '../ChatMessage';
import { ChatInput } from '../ChatInput';
import { AgentActivityTimeline } from '../AgentActivityTimeline';
import { ModelPicker, type ModelSelection } from '../../model_provider';
import type { ChatState } from '../../hooks/useChat';
import './ChatWindow.css';

interface ChatWindowProps extends ChatState {
  onSend: (message: string) => void;
  modelSelection?: ModelSelection | null;
  onModelChange?: (model: ModelSelection) => void;
  onVoiceClick?: () => void;
  onAttachmentClick?: () => void;
  disabledNoModel?: boolean;
  mode?: 'chat' | 'task';
  onNavigateView?: (view: 'finance' | 'jobs' | 'email' | 'calculator' | 'calendar') => void;
  onStop?: () => void;
  onClearConversation?: () => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  attribution,
  isStreaming,
  error,
  criticReview,
  nextActions,
  onSend,
  modelSelection,
  onModelChange,
  onVoiceClick,
  onAttachmentClick,
  disabledNoModel = false,
  mode = 'chat',
  onNavigateView,
  onStop,
  onClearConversation,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming
  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  React.useEffect(() => {
    if (isStreaming || messages.length > 0) {
      scrollToBottom();
    }
  }, [messages, isStreaming, scrollToBottom]);

  const modelPickerSlot = onModelChange ? (
    <ModelPicker value={modelSelection ?? null} onChange={onModelChange} />
  ) : undefined;

  const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user');
  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <main className="chat-window" aria-label="Chat window">
      {isEmpty ? (
        /* ─── Modern ChatGPT-Style Centered Hero (Empty State) ─── */
        <div className="chat-window__hero">
          <div className="chat-window__hero-content">
            <div className="chat-window__hero-badge">
              <span className="chat-window__hero-badge-spark">✨</span>
              <span>Next-Gen Multi-Agent Intelligence</span>
            </div>

            <h1 className="chat-window__hero-title">
              {mode === 'task' ? 'What code shall we build today?' : 'What would you like to accomplish?'}
            </h1>

            <p className="chat-window__hero-subtitle">
              Fast streaming reasoning, live web context, document understanding, and multi-model synthesis.
            </p>

            {/* Centered Single Input Capsule */}
            <div className="chat-window__hero-input-wrapper">
              <ChatInput
                onSend={onSend}
                disabled={false}
                isStreaming={isStreaming}
                disabledNoModel={disabledNoModel}
                leftSlot={modelPickerSlot}
                onVoiceClick={onVoiceClick}
                onAttachmentClick={onAttachmentClick}
                onStop={onStop}
                placeholder={
                  mode === 'task'
                    ? 'Ask to write code, build a script, or debug…'
                    : 'Ask anything, chat, or paste code…'
                }
                onNavigateView={onNavigateView}
              />
            </div>

            {/* 4 Categorized Suggestion Cards */}
            <div className="chat-window__suggestions" role="region" aria-label="Suggested prompts">
              <button
                type="button"
                className="chat-window__suggestion-card"
                onClick={() => onSend('Build a type-safe FastAPI service with JWT authentication, rate limiting, and health checks')}
              >
                <div className="chat-window__suggestion-icon">⚡</div>
                <div className="chat-window__suggestion-content">
                  <span className="chat-window__suggestion-category">Code &amp; Architecture</span>
                  <span className="chat-window__suggestion-text">Build a type-safe FastAPI service with JWT auth</span>
                </div>
              </button>

              <button
                type="button"
                className="chat-window__suggestion-card"
                onClick={() => onSend('Analyze key performance indicators and revenue growth patterns in modern SaaS platforms')}
              >
                <div className="chat-window__suggestion-icon">📊</div>
                <div className="chat-window__suggestion-content">
                  <span className="chat-window__suggestion-category">Data &amp; Analysis</span>
                  <span className="chat-window__suggestion-text">Analyze KPI metrics and SaaS revenue patterns</span>
                </div>
              </button>

              <button
                type="button"
                className="chat-window__suggestion-card"
                onClick={() => onSend('Synthesize the latest research breakthroughs in small reasoning models and test-time compute')}
              >
                <div className="chat-window__suggestion-icon">🔍</div>
                <div className="chat-window__suggestion-content">
                  <span className="chat-window__suggestion-category">Research &amp; Grounding</span>
                  <span className="chat-window__suggestion-text">Synthesize breakthrough research in reasoning models</span>
                </div>
              </button>

              <button
                type="button"
                className="chat-window__suggestion-card"
                onClick={() => onSend('Draft a comprehensive launch plan and technical documentation roadmap for a developer product')}
              >
                <div className="chat-window__suggestion-icon">💡</div>
                <div className="chat-window__suggestion-content">
                  <span className="chat-window__suggestion-category">Brainstorm &amp; Strategy</span>
                  <span className="chat-window__suggestion-text">Draft a launch strategy and documentation roadmap</span>
                </div>
              </button>
            </div>

            {/* Capability Badges */}
            <div className="chat-window__capabilities">
              <span className="chat-window__capability-chip">🌐 Live Web Search</span>
              <span className="chat-window__capability-chip">📑 Document Vision</span>
              <span className="chat-window__capability-chip">🎙️ Voice Mode</span>
              <span className="chat-window__capability-chip">🧠 Deep Reasoning</span>
            </div>
          </div>
        </div>
      ) : (
        /* ─── Active Conversation View ─── */
        <>
          <section
            ref={scrollContainerRef}
            className="chat-window__messages"
            aria-label="Messages"
            aria-live="polite"
            aria-atomic="false"
          >
            {/* In-chat Context Pill & Clear Conversation Bar */}
            <div className="chat-window__context-bar">
              <div className="chat-window__context-pill">
                <span className="chat-window__context-icon">🧠</span>
                <span>Active Context: {messages.length} messages</span>
                <span className="chat-window__context-dot">·</span>
                <span className="chat-window__context-model">
                  {modelSelection?.model || 'Coordinator Agent'}
                </span>
                <span className="chat-window__context-dot">·</span>
                <span className="chat-window__context-status">Memory Active</span>
              </div>

              {onClearConversation && (
                <button
                  type="button"
                  className="chat-window__clear-btn"
                  onClick={() => {
                    if (window.confirm('Clear active conversation messages?')) {
                      onClearConversation();
                    }
                  }}
                  title="Clear active conversation"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                  <span>Clear chat</span>
                </button>
              )}
            </div>

            <div className="chat-window__messages-inner">
              {messages.map((msg, i) => {
                const isLastAssistant =
                  msg.role === 'assistant' &&
                  i === messages.findIndex((m) => m.role === 'assistant') + messages.filter((m) => m.role === 'assistant').length - 1;
                const showAttribution =
                  msg.role === 'assistant' && (attribution !== null || !isStreaming);

                return (
                  <ChatMessage
                    key={i}
                    role={msg.role}
                    content={msg.content}
                    attribution={msg.role === 'assistant' && showAttribution ? attribution ?? undefined : undefined}
                    criticReview={msg.role === 'assistant' ? criticReview ?? null : null}
                    isStreaming={isLastAssistant && isStreaming}
                    onRegenerate={
                      isLastAssistant && !isStreaming
                        ? () => {
                            if (lastUserMessage?.content) onSend(lastUserMessage.content);
                          }
                        : undefined
                    }
                  />
                );
              })}

              {/* Agent Activity Pipeline Timeline during streaming */}
              {isStreaming && (
                <AgentActivityTimeline
                  isStreaming={isStreaming}
                  prompt={lastUserMessage?.content}
                  onStop={onStop}
                  onReplyNow={scrollToBottom}
                  agentSlug={attribution?.agentSlug || 'coordinator'}
                />
              )}

              {/* Error card with inline Retry */}
              {error && (
                <div className="chat-window__error-card" role="alert" aria-live="assertive">
                  <div className="chat-window__error-content">
                    <span className="chat-window__error-icon">⚠️</span>
                    <div className="chat-window__error-text">
                      <strong>Generation Error:</strong> {error}
                    </div>
                  </div>
                  {lastUserMessage?.content && (
                    <button
                      type="button"
                      className="chat-window__error-retry-btn"
                      onClick={() => onSend(lastUserMessage.content)}
                      title="Retry sending previous prompt"
                    >
                      🔄 Retry Turn
                    </button>
                  )}
                </div>
              )}

              <div ref={bottomRef} aria-hidden="true" />
            </div>
          </section>

          {/* Coordinator Next-Action Chips */}
          {nextActions && nextActions.length > 0 && (
            <div className="chat-window__next-actions" role="toolbar" aria-label="Suggested next actions">
              {nextActions.map((action, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="chat-window__action-chip"
                  onClick={() => onSend(action)}
                >
                  {action}
                </button>
              ))}
            </div>
          )}

          {/* Floating Bottom Single Input */}
          <div className="chat-window__bottom-bar">

            <ChatInput
              onSend={onSend}
              disabled={false}
              isStreaming={isStreaming}
              disabledNoModel={disabledNoModel}
              leftSlot={modelPickerSlot}
              onVoiceClick={onVoiceClick}
              onAttachmentClick={onAttachmentClick}
              onStop={onStop}
              placeholder={
                mode === 'task'
                  ? 'Ask to write code, build a script, or debug…'
                  : 'Ask anything, chat, or paste code…'
              }
              onNavigateView={onNavigateView}
            />
          </div>
        </>
      )}
    </main>
  );
};
