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
  mode?: 'chat' | 'task';
  onNavigateView?: (view: 'finance' | 'jobs' | 'email') => void;
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
            <h1 className="chat-window__hero-title">
              {mode === 'task' ? 'What code shall we build today?' : 'Ready when you are.'}
            </h1>

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
                placeholder={
                  mode === 'task'
                    ? 'Ask to write code, build a script, or debug…'
                    : 'Ask anything, chat, or paste code…'
                }
                onNavigateView={onNavigateView}
              />
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
