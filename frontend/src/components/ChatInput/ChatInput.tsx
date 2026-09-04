/* ChatInput — text area with send button. */

import React, { useRef, useState } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  /** When true, the input is disabled with a "choose a model first" hint. */
  disabledNoModel?: boolean;
  /** Optional element rendered to the left of the textarea (e.g. a model picker). */
  leftSlot?: React.ReactNode;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  disabled = false,
  isStreaming = false,
  disabledNoModel = false,
  leftSlot,
}) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = value.trim();
    if (!text || disabled || isStreaming || disabledNoModel) return;
    onSend(text);
    setValue('');
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  };

  const placeholder = disabledNoModel
    ? 'Choose a model to start chatting…'
    : isStreaming
      ? 'Waiting for response…'
      : 'Type a message…';

  return (
    <form className="chat-input" onSubmit={handleSubmit} aria-label="Send message">
      <div className="chat-input__row">
        {leftSlot}
        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isStreaming || disabledNoModel}
          rows={1}
          aria-label="Message input"
          aria-multiline="true"
        />
        <button
          type="submit"
          className="chat-input__send"
          disabled={
            !value.trim() || disabled || isStreaming || disabledNoModel
          }
          aria-label="Send message"
        >
          {isStreaming ? (
            <span className="chat-input__spinner" aria-hidden="true" />
          ) : (
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" />
            </svg>
          )}
        </button>
      </div>
      <p className="chat-input__hint" aria-live="polite">
        Press Enter to send · Shift+Enter for new line
      </p>
    </form>
  );
};
