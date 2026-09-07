/* ChatWindow — Modern ChatGPT/Claude Style Chat Interface */

import React, { useCallback, useRef } from 'react';
import { ChatMessage } from '../ChatMessage';
import { ChatInput } from '../ChatInput';
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
}

const SUGGESTIONS = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    ),
    title: 'Write or edit code',
    prompt: 'Write a Python script to fetch and process structured data with error handling.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    ),
    title: 'Search the web',
    prompt: 'Search the web for the latest updates on autonomous AI agents and open models.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    title: 'Check finances & balances',
    prompt: 'Check my current bank account balance and review recent transactions.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
    title: 'Schedule a task or reminder',
    prompt: 'Schedule a reminder for tomorrow at 10 AM to review project milestones.',
  },
];

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

  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <main className="chat-window" aria-label="Chat window">
      {isEmpty ? (
        /* ─── Modern ChatGPT-Style Centered Hero (Empty State) ─── */
        <div className="chat-window__hero">
          <div className="chat-window__hero-content">
            <h1 className="chat-window__hero-title">Ready when you are.</h1>

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
              />
            </div>

            {/* Quick Action Suggestion Cards */}
            <div className="chat-window__suggestions" role="list" aria-label="Suggested prompts">
              {SUGGESTIONS.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="chat-window__suggestion-card"
                  onClick={() => onSend(item.prompt)}
                  role="listitem"
                >
                  <span className="chat-window__suggestion-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className="chat-window__suggestion-text">{item.title}</span>
                </button>
              ))}
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
                  />
                );
              })}

              {error && (
                <div className="chat-window__error" role="alert" aria-live="assertive">
                  <strong>Error:</strong> {error}
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
            />
          </div>
        </>
      )}
    </main>
  );
};
