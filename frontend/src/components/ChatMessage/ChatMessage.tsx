/* ChatMessage — individual message bubble with optional attribution badge */

import React from 'react';
import type { Attribution } from '../../hooks/useChat';

export type { Attribution };

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  attribution?: Attribution;
  isStreaming?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  role,
  content,
  attribution,
  isStreaming = false,
}) => {
  const attributionLabel = attribution
    ? `Response from ${attribution.provider} using model ${attribution.model}`
    : undefined;

  return (
    <div
      className={`chat-message chat-message--${role} ${isStreaming && role === 'assistant' ? 'chat-message--streaming' : ''}`}
      aria-role={role === 'user' ? 'presentation' : 'article'}
    >
      <div className="chat-message__bubble">
        <p className="chat-message__text">{content || (isStreaming ? '…' : '')}</p>
        {isStreaming && (
          <span className="chat-message__cursor" aria-hidden="true" />
        )}
      </div>
      {role === 'assistant' && (
        <div
          className="chat-message__attribution"
          aria-label={attributionLabel}
          title={attributionLabel}
        >
          {attribution ? (
            <>
              <span className="chat-message__provider">{attribution.provider}</span>
              <span className="chat-message__sep" aria-hidden="true"> · </span>
              <span className="chat-message__model">{attribution.model}</span>
            </>
          ) : (
            <span className="chat-message__provider-unknown">routing…</span>
          )}
        </div>
      )}
    </div>
  );
};
