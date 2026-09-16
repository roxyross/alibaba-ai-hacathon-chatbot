/* ChatMessage — Professional, minimalist message bubble with sleek bottom action bar */

import React, { useState } from 'react';
import type { Attribution } from '../../hooks/useChat';
import './ChatMessage.css';

export type { Attribution };

interface CriticWeakness {
  name: string;
  why_it_matters?: string;
}

export interface CriticReviewData {
  verdict: string;
  overall: string;
  strengths: string[];
  weaknesses: CriticWeakness[];
  summary: string;
}

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  attribution?: Attribution;
  criticReview?: CriticReviewData | Record<string, unknown> | null;
  isStreaming?: boolean;
  onRegenerate?: () => void;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="chat-message__code-block">
      <div className="chat-message__code-header">
        <span className="chat-message__code-lang">{lang || 'code'}</span>
        <button
          type="button"
          className="chat-message__code-copy"
          onClick={handleCopy}
          aria-label="Copy code"
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <pre className="chat-message__code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function FormattedContent({ content }: { content: string }) {
  if (!content) return null;

  const tokens: React.ReactNode[] = [];
  const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  const processText = (text: string, keyPrefix: string): React.ReactNode[] => {
    const imgRegex = /!\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g;
    const parts: React.ReactNode[] = [];
    let imgLastIndex = 0;
    let imgMatch: RegExpExecArray | null;

    while ((imgMatch = imgRegex.exec(text)) !== null) {
      if (imgMatch.index > imgLastIndex) {
        const textBefore = text.substring(imgLastIndex, imgMatch.index);
        parts.push(renderTextWithFormatting(textBefore, `${keyPrefix}-t-${imgLastIndex}`));
      }
      const alt = imgMatch[1] || 'Generated image';
      const url = imgMatch[2];
      parts.push(
        <div key={`${keyPrefix}-img-${imgMatch.index}`} className="chat-message__image-container">
          <img src={url} alt={alt} className="chat-message__image" loading="lazy" />
          {alt && alt !== 'Generated image' && (
            <div className="chat-message__image-caption">{alt}</div>
          )}
        </div>
      );
      imgLastIndex = imgMatch.index + imgMatch[0].length;
    }

    if (imgLastIndex < text.length) {
      parts.push(renderTextWithFormatting(text.substring(imgLastIndex), `${keyPrefix}-t-${imgLastIndex}`));
    }

    return parts;
  };

  const renderTextWithFormatting = (text: string, key: string): React.ReactNode => {
    const lines = text.split('\n');
    return (
      <span key={key}>
        {lines.map((line, lIdx) => {
          const isBullet = line.trim().startsWith('- ') || line.trim().startsWith('* ');
          const lineContent = isBullet ? line.trim().substring(2) : line;

          const formattedParts: React.ReactNode[] = [];
          const inlineRegex = /(\*\*.*?\*\*|`.*?`|\[.*?\]\(https?:\/\/[^\s)]+\))/g;
          let inlineLast = 0;
          let inlineMatch: RegExpExecArray | null;

          while ((inlineMatch = inlineRegex.exec(lineContent)) !== null) {
            if (inlineMatch.index > inlineLast) {
              formattedParts.push(lineContent.substring(inlineLast, inlineMatch.index));
            }
            const matchedToken = inlineMatch[0];
            if (matchedToken.startsWith('**') && matchedToken.endsWith('**')) {
              formattedParts.push(<strong key={inlineMatch.index}>{matchedToken.slice(2, -2)}</strong>);
            } else if (matchedToken.startsWith('`') && matchedToken.endsWith('`')) {
              formattedParts.push(<code key={inlineMatch.index} className="chat-message__inline-code">{matchedToken.slice(1, -1)}</code>);
            } else if (matchedToken.startsWith('[') && matchedToken.includes('](')) {
              const linkMatch = /^\[(.*?)\]\((https?:\/\/[^\s)]+)\)$/.exec(matchedToken);
              if (linkMatch) {
                formattedParts.push(
                  <a
                    key={inlineMatch.index}
                    href={linkMatch[2]}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="chat-message__link"
                  >
                    {linkMatch[1]}
                  </a>
                );
              } else {
                formattedParts.push(matchedToken);
              }
            }
            inlineLast = inlineMatch.index + matchedToken.length;
          }
          if (inlineLast < lineContent.length) {
            formattedParts.push(lineContent.substring(inlineLast));
          }

          return (
            <React.Fragment key={lIdx}>
              {isBullet ? (
                <div className="chat-message__bullet-item">
                  <span className="chat-message__bullet-dot">•</span>
                  <span>{formattedParts}</span>
                </div>
              ) : (
                <span>{formattedParts}</span>
              )}
              {lIdx < lines.length - 1 && !isBullet && <br />}
            </React.Fragment>
          );
        })}
      </span>
    );
  };

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      const textBefore = content.substring(lastIndex, match.index);
      tokens.push(...processText(textBefore, `pre-${lastIndex}`));
    }
    const lang = match[1] || 'code';
    const code = match[2];
    tokens.push(
      <CodeBlock key={`code-${match.index}`} lang={lang} code={code} />
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    tokens.push(...processText(content.substring(lastIndex), `post-${lastIndex}`));
  }

  return <div className="chat-message__formatted">{tokens}</div>;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  role,
  content,
  attribution,
  isStreaming = false,
  onRegenerate,
}) => {
  const [displayContent, setDisplayContent] = useState(content);
  const [isEditing, setIsEditing] = useState(false);
  const [draftContent, setDraftContent] = useState(content);
  const [copied, setCopied] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  React.useEffect(() => {
    setDisplayContent(content);
    setDraftContent(content);
  }, [content]);

  React.useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const handleReadAloud = () => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      alert('Text-to-speech is not supported in this browser.');
      return;
    }

    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    window.speechSynthesis.cancel();

    const textToSpeak = displayContent
      .replace(/```[\s\S]*?```/g, 'Code block omitted.')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/[*#_~>\[\]]/g, '')
      .replace(/\(http[^\)]+\)/g, '')
      .trim();

    if (!textToSpeak) return;

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(displayContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = displayContent;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([displayContent], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `roxy-response-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleSaveEdit = () => {
    setDisplayContent(draftContent);
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setDraftContent(displayContent);
    setIsEditing(false);
  };

  return (
    <div
      className={`chat-message chat-message--${role} ${isStreaming && role === 'assistant' ? 'chat-message--streaming' : ''}`}
      aria-role={role === 'user' ? 'presentation' : 'article'}
    >
      <div className="chat-message__bubble">
        {isEditing ? (
          <div className="chat-message__edit-box">
            <textarea
              className="chat-message__edit-textarea"
              value={draftContent}
              onChange={(e) => setDraftContent(e.target.value)}
              rows={Math.max(4, draftContent.split('\n').length)}
            />
            <div className="chat-message__edit-actions">
              <button type="button" className="chat-message__edit-save" onClick={handleSaveEdit}>
                Save
              </button>
              <button type="button" className="chat-message__edit-cancel" onClick={handleCancelEdit}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            {displayContent ? (
              <FormattedContent content={displayContent} />
            ) : isStreaming ? (
              <div className="chat-message__shimmer-skeleton" aria-label="Thinking...">
                <div className="chat-message__shimmer-line chat-message__shimmer-line--long" />
                <div className="chat-message__shimmer-line chat-message__shimmer-line--medium" />
                <div className="chat-message__shimmer-line chat-message__shimmer-line--short" />
              </div>
            ) : null}
            {isStreaming && displayContent && (
              <span className="chat-message__cursor" aria-hidden="true" />
            )}
          </>
        )}
      </div>

      {/* Sleek, minimal action toolbar placed below completed assistant responses */}
      {role === 'assistant' && !isStreaming && (
        <div className="chat-message__action-row">
          <div className="chat-message__attribution-badge">
            <span className="chat-message__attribution-dot" />
            <span className="chat-message__attribution-text">
              {attribution?.model || attribution?.agentSlug || 'Roxy AI'}
            </span>
          </div>

          <div className="chat-message__tools">
            <button
              type="button"
              className="chat-message__tool-btn"
              onClick={handleCopy}
              title={copied ? 'Copied!' : 'Copy response'}
              aria-label="Copy response"
            >
              {copied ? (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0d9488" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span style={{ color: '#0d9488' }}>Copied</span>
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                  <span>Copy</span>
                </>
              )}
            </button>

            <button
              type="button"
              className={`chat-message__tool-btn ${isSpeaking ? 'chat-message__tool-btn--active' : ''}`}
              onClick={handleReadAloud}
              title={isSpeaking ? 'Stop speaking' : 'Read aloud'}
              aria-label="Read aloud"
            >
              {isSpeaking ? (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                  <span>Stop</span>
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
                  </svg>
                  <span>Listen</span>
                </>
              )}
            </button>

            {onRegenerate && (
              <button
                type="button"
                className="chat-message__tool-btn"
                onClick={onRegenerate}
                title="Regenerate this response"
                aria-label="Regenerate response"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                <span>Retry</span>
              </button>
            )}

            <button
              type="button"
              className="chat-message__tool-btn"
              onClick={handleDownload}
              title="Download as Markdown"
              aria-label="Download response"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span>Export</span>
            </button>

            <button
              type="button"
              className={`chat-message__tool-btn ${isEditing ? 'chat-message__tool-btn--active' : ''}`}
              onClick={() => setIsEditing(!isEditing)}
              title="Edit response text"
              aria-label="Edit response"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
              </svg>
              <span>Edit</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
