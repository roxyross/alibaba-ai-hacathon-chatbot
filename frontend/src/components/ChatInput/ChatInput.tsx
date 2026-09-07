/* ChatInput — modern ChatGPT/Claude style input capsule with + flyout tools menu */

import React, { useEffect, useRef, useState } from 'react';
import './ChatInput.css';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  /** When true, the input is disabled with a "choose a model first" hint. */
  disabledNoModel?: boolean;
  /** Optional element rendered to the left of the textarea (e.g. a model picker). */
  leftSlot?: React.ReactNode;
  /** Callback to trigger interactive live voice session */
  onVoiceClick?: () => void;
  /** Callback to trigger document attachment / upload view */
  onAttachmentClick?: () => void;
  /** Custom placeholder override */
  placeholder?: string;
}

// Check for Web Speech API
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  disabled = false,
  isStreaming = false,
  disabledNoModel = false,
  leftSlot,
  onVoiceClick,
  onAttachmentClick,
  placeholder: customPlaceholder,
}) => {
  const [value, setValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [showToolsMenu, setShowToolsMenu] = useState(false);
  const [thinkMode, setThinkMode] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const actionBtnRef = useRef<HTMLButtonElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);

  // Close flyout menu on click outside
  useEffect(() => {
    if (!showToolsMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        actionBtnRef.current &&
        !actionBtnRef.current.contains(target)
      ) {
        setShowToolsMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showToolsMenu]);

  // Initialize Web Speech API if supported
  useEffect(() => {
    if (!SpeechRecognitionClass) return;

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onresult = (event: any) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        if (transcript) {
          setValue((prev) => {
            const separator = prev && !prev.endsWith(' ') ? ' ' : '';
            return prev + separator + transcript;
          });
          adjustHeight();
        }
      };

      recognition.onerror = () => {
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
    } catch {
      // Speech recognition not available
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const toggleVoiceDictation = () => {
    if (disabled || isStreaming || disabledNoModel) return;

    if (!SpeechRecognitionClass) {
      onVoiceClick?.();
      return;
    }

    if (isListening) {
      try {
        recognitionRef.current?.stop();
      } catch {
        // ignore
      }
      setIsListening(false);
    } else {
      try {
        recognitionRef.current?.start();
        setIsListening(true);
      } catch {
        setIsListening(false);
      }
    }
  };

  const adjustHeight = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  };

  const handleFilesSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setAttachedFiles((prev) => [...prev, ...newFiles]);
    }
    e.target.value = '';
  };

  const removeAttachedFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const text = value.trim();
    if ((!text && attachedFiles.length === 0) || disabled || isStreaming || disabledNoModel) return;

    if (isListening) {
      try {
        recognitionRef.current?.stop();
      } catch {
        // ignore
      }
      setIsListening(false);
    }

    let messageToSend = text;
    if (thinkMode) {
      messageToSend = `[Deep Reasoning Mode]\n${messageToSend}`;
    }
    if (attachedFiles.length > 0) {
      const fileListDesc = attachedFiles
        .map((f) => `• ${f.name} (${(f.size / 1024).toFixed(1)} KB, ${f.type || 'file'})`)
        .join('\n');
      messageToSend = messageToSend
        ? `${messageToSend}\n\n[Attached files from device]:\n${fileListDesc}`
        : `[Attached files from device]:\n${fileListDesc}\nPlease analyze the attached files.`;
    }

    onSend(messageToSend);
    setValue('');
    setAttachedFiles([]);

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.currentTarget;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newValue = value.substring(0, start) + '  ' + value.substring(end);
      setValue(newValue);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
        adjustHeight();
      });
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    adjustHeight();
  };

  const placeholder =
    customPlaceholder ||
    (disabledNoModel
      ? 'Choose a model to start chatting…'
      : isStreaming
        ? 'ROXY AI is thinking…'
        : isListening
          ? 'Listening... speak now'
          : 'Ask anything, chat, or paste code…');

  const hasContent = value.trim().length > 0 || attachedFiles.length > 0;

  return (
    <form className="chat-input" onSubmit={handleSubmit} aria-label="Send message">
      {/* Hidden file input for native computer file access */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFilesSelected}
        multiple
        style={{ display: 'none' }}
      />

      {/* Floating Tools Popover (+ Menu) */}
      {showToolsMenu && (
        <div className="chat-input__flyout" ref={menuRef} role="menu" aria-label="Add options">
          {/* 1. Add photos & files (upload from computer) */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              fileInputRef.current?.click();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--gray">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Add photos &amp; files</span>
              <span className="chat-input__flyout-subtitle">Upload from computer</span>
            </div>
          </button>

          {/* 2. Add from library */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              onAttachmentClick?.();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--orange">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Add from library</span>
              <span className="chat-input__flyout-subtitle">Browse and search your files</span>
            </div>
          </button>

          {/* 3. Create image */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Create an image of: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--cyan">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Create image</span>
              <span className="chat-input__flyout-subtitle">Visualize anything</span>
            </div>
          </button>

          {/* 4. Web search */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Search the web for: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--blue">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Web search</span>
              <span className="chat-input__flyout-subtitle">Find real-time news and info</span>
            </div>
          </button>

          {/* 5. Maps */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Find places near: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--pin">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Maps</span>
              <span className="chat-input__flyout-subtitle">Find Nearby Places</span>
            </div>
          </button>

          {/* 6. Deep research */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Conduct deep research on: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--telescope">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
                <line x1="11" y1="8" x2="11" y2="14" />
                <line x1="8" y1="11" x2="14" y2="11" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Deep research</span>
              <span className="chat-input__flyout-subtitle">Get a detailed report</span>
            </div>
          </button>

        </div>
      )}

      {/* Attached Files Chips Bar */}
      {attachedFiles.length > 0 && (
        <div className="chat-input__attached-bar">
          {attachedFiles.map((file, idx) => (
            <div key={`${file.name}-${idx}`} className="chat-input__file-chip">
              <span className="chat-input__chip-icon">📎</span>
              <span className="chat-input__chip-name" title={file.name}>{file.name}</span>
              <button
                type="button"
                className="chat-input__chip-remove"
                onClick={() => removeAttachedFile(idx)}
                aria-label={`Remove ${file.name}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className={`chat-input__capsule ${isListening ? 'chat-input__capsule--listening' : ''}`}>
        {/* Left tools slot: Attachment (+) and ModelPicker */}
        <div className="chat-input__left">
          <button
            ref={actionBtnRef}
            type="button"
            className={`chat-input__action-btn ${showToolsMenu ? 'chat-input__action-btn--active' : ''}`}
            onClick={() => setShowToolsMenu((prev) => !prev)}
            title="Add files, tools, and search"
            aria-label="Add files, tools, and search"
            aria-expanded={showToolsMenu}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
          {leftSlot}
        </div>

        {/* Text & Code Textarea */}
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

        {/* Right tools slot: Think button, Mic button, and Send / Voice Mode button */}
        <div className="chat-input__right">
          {/* Think Toggle Button */}
          <button
            type="button"
            className={`chat-input__think-btn ${thinkMode ? 'chat-input__think-btn--active' : ''}`}
            onClick={() => setThinkMode((prev) => !prev)}
            title={thinkMode ? 'Deep reasoning enabled' : 'Enable deep reasoning (Think)'}
            aria-label={thinkMode ? 'Deep reasoning enabled' : 'Enable deep reasoning (Think)'}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span>Think</span>
          </button>

          {/* Voice dictation mic button */}
          <button
            type="button"
            className={`chat-input__mic-btn ${isListening ? 'chat-input__mic-btn--active' : ''}`}
            onClick={toggleVoiceDictation}
            title={isListening ? 'Stop listening' : 'Dictate with voice'}
            aria-label={isListening ? 'Stop listening' : 'Dictate with voice'}
            disabled={disabled || isStreaming || disabledNoModel}
          >
            {isListening ? (
              <span className="chat-input__mic-pulse" aria-hidden="true" />
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            )}
          </button>

          {/* If there is content: show Send (↑) button. If empty and onVoiceClick provided: show interactive Voice button */}
          {hasContent || isStreaming || !onVoiceClick ? (
            <button
              type="submit"
              className={`chat-input__send-btn ${hasContent ? 'chat-input__send-btn--ready' : ''}`}
              disabled={!hasContent || disabled || isStreaming || disabledNoModel}
              aria-label="Send message"
            >
              {isStreaming ? (
                <span className="chat-input__spinner" aria-hidden="true" />
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="19" x2="12" y2="5" />
                  <polyline points="5 12 12 5 19 12" />
                </svg>
              )}
            </button>
          ) : (
            <button
              type="button"
              className="chat-input__voice-mode-btn"
              onClick={onVoiceClick}
              title="Talk out loud with ROXY AI using Voice"
              aria-label="Talk out loud with ROXY AI using Voice"
            >
              <div className="chat-input__waveform">
                <span />
                <span />
                <span />
                <span />
              </div>
            </button>
          )}
        </div>
      </div>

      <div className="chat-input__footer">
        <span className="chat-input__shortcut-hint">
          <strong>Enter</strong> to send · <strong>Shift + Enter</strong> for new line · <strong>Tab</strong> to indent code
        </span>
      </div>
    </form>
  );
};
