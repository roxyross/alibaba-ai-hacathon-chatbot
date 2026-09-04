/* ChatWindow — scrollable message list + input */

import React, { useCallback, useRef } from 'react';
import { ChatMessage } from '../ChatMessage';
import { ChatInput } from '../ChatInput';
import type { ChatState } from '../../hooks/useChat';

interface ChatWindowProps extends ChatState {
  onSend: (message: string) => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  attribution,
  isStreaming,
  error,
  onSend,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming
  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Scroll after each render where streaming is active
  React.useEffect(() => {
    if (isStreaming) {
      scrollToBottom();
    }
  }, [messages, isStreaming, scrollToBottom]);

  return (
    <main className="chat-window" aria-label="Chat window">
      {/* Message list */}
      <section
        ref={scrollContainerRef}
        className="chat-window__messages"
        aria-label="Messages"
        aria-live="polite"
        aria-atomic="false"
      >
        {messages.length === 0 && !isStreaming && (
          <div className="chat-window__empty" aria-label="No messages yet">
            <p>Send a message to start chatting.</p>
            <p>Responses will show which AI provider handled your request.</p>
          </div>
        )}

        {messages.map((msg, i) => {
          // The last assistant message while streaming has no attribution yet
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
      </section>

      {/* Input */}
      <ChatInput
        onSend={onSend}
        disabled={false}
        isStreaming={isStreaming}
      />
    </main>
  );
};
