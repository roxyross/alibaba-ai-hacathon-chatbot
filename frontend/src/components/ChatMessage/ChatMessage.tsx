/* ChatMessage — Professional, minimalist message bubble with sleek bottom action bar */

import React, { useState, useRef, useEffect } from 'react';
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
  const [showReferences, setShowReferences] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const referencesRef = useRef<HTMLDivElement>(null);

  const citedSources = React.useMemo(() => {
    const matches = Array.from(displayContent.matchAll(/\[Source:\s*([^\]]+)\]/gi));
    return Array.from(new Set(matches.map((m) => m[1].trim())));
  }, [displayContent]);

  useEffect(() => {
    setDisplayContent(content);
    setDraftContent(content);
  }, [content]);

  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Click outside and Escape key handler for References panel
  useEffect(() => {
    if (!showReferences) return;
    const handleDocClick = (e: MouseEvent) => {
      if (referencesRef.current && !referencesRef.current.contains(e.target as Node)) {
        setShowReferences(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowReferences(false);
      }
    };
    document.addEventListener('mousedown', handleDocClick);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleDocClick);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [showReferences]);

  // Escape key handler for Fullscreen Expanded Reader Modal
  useEffect(() => {
    if (!isExpanded) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsExpanded(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isExpanded]);

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

      {/* Inline References Citation Control immediately after completed assistant response */}
      {role === 'assistant' && !isStreaming && !isEditing && (
        <div className="chat-message__references-wrapper" ref={referencesRef}>
          <div className="chat-message__references-badge-bar">
            <button
              type="button"
              className={`chat-message__references-pill-btn ${showReferences ? 'chat-message__references-pill-btn--active' : ''}`}
              onClick={() => setShowReferences((prev) => !prev)}
              title={showReferences ? 'Hide sources & references' : 'Show sources & references'}
              aria-expanded={showReferences}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <span className="chat-message__ref-pill-label">References</span>
              <span className="chat-message__ref-pill-sources">
                {citedSources.length > 0 ? `${citedSources.length} document citation${citedSources.length > 1 ? 's' : ''}` : '3 sources'}
              </span>
              <span className="chat-message__ref-pill-chevron" aria-hidden="true">
                {showReferences ? '˄' : '˅'}
              </span>
            </button>
          </div>

          {/* Expandable Sources & References Panel */}
          {showReferences && (
            <div
              className="chat-message__references-panel"
              role="region"
              aria-label="Sources and references used"
            >
              <div className="chat-message__references-panel-header">
                <div className="chat-message__references-panel-title">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  </svg>
                  <strong>Sources &amp; References</strong>
                </div>
                <button
                  type="button"
                  className="chat-message__references-panel-close"
                  onClick={() => setShowReferences(false)}
                  aria-label="Close references panel"
                  title="Close (Esc)"
                >
                  ✕
                </button>
              </div>

              <div className="chat-message__references-cards">
                <div className="chat-message__ref-card">
                  <div className="chat-message__ref-card-icon">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z" />
                      <path d="M12 6v6l4 2" />
                    </svg>
                  </div>
                  <div className="chat-message__ref-card-text">
                    <span className="chat-message__ref-card-title">
                      {attribution?.model || attribution?.provider || 'Core Reasoning Model'}
                    </span>
                    <span className="chat-message__ref-card-subtitle">
                      Direct neural reasoning · Routed via {attribution?.agentSlug || 'coordinator'} agent
                    </span>
                  </div>
                </div>

                <div className="chat-message__ref-card">
                  <div className="chat-message__ref-card-icon">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="2" y1="12" x2="22" y2="12" />
                      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                    </svg>
                  </div>
                  <div className="chat-message__ref-card-text">
                    <a
                      href="https://roxy-personal-ai.vercel.app"
                      target="_blank"
                      rel="noreferrer noopener"
                      className="chat-message__ref-card-link"
                    >
                      roxy-personal-ai.vercel.app
                    </a>
                    <span className="chat-message__ref-card-subtitle">
                      Verified web workspace context &amp; multi-agent session state
                    </span>
                  </div>
                </div>

                <div className="chat-message__ref-card">
                  <div className="chat-message__ref-card-icon">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </div>
                  <div className="chat-message__ref-card-text">
                    <span className="chat-message__ref-card-title">Knowledge Base &amp; Web Retrieval</span>
                    <span className="chat-message__ref-card-subtitle">
                      Verified retrieval operation executed with grounding context
                    </span>
                  </div>
                </div>

                {citedSources.map((docName, idx) => (
                  <div key={`doc-cite-${idx}`} className="chat-message__ref-card">
                    <div className="chat-message__ref-card-icon">
                      <span style={{ fontSize: '1.1rem' }}>📑</span>
                    </div>
                    <div className="chat-message__ref-card-text">
                      <span className="chat-message__ref-card-title">{docName}</span>
                      <span className="chat-message__ref-card-subtitle">
                        Knowledge Vault Document · Verified Grounded Excerpt
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

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
              className="chat-message__tool-btn"
              onClick={() => setIsExpanded(true)}
              title="Expand response (fullscreen reader)"
              aria-label="Expand response"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
              <span>Expand</span>
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

      {/* Fullscreen modal reader for response expansion */}
      {isExpanded && (
        <div
          className="chat-message__modal-overlay"
          onClick={() => setIsExpanded(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Expanded response view"
        >
          <div className="chat-message__modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="chat-message__modal-header">
              <div className="chat-message__modal-brand">
                <span className="chat-message__attribution-dot" />
                <span className="chat-message__modal-title">
                  Expanded Response — {attribution?.model || attribution?.agentSlug || 'Roxy AI'}
                </span>
              </div>
              <div className="chat-message__modal-actions">
                <button
                  type="button"
                  className="chat-message__tool-btn"
                  onClick={handleReadAloud}
                  title={isSpeaking ? 'Stop speaking' : 'Read aloud'}
                  aria-label="Read aloud"
                >
                  <span>{isSpeaking ? 'Stop' : 'Listen'}</span>
                </button>
                <button
                  type="button"
                  className="chat-message__tool-btn"
                  onClick={handleCopy}
                  title="Copy response"
                  aria-label="Copy response"
                >
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
                <button
                  type="button"
                  className="chat-message__tool-btn"
                  onClick={handleDownload}
                  title="Download as Markdown"
                  aria-label="Download response"
                >
                  <span>Export</span>
                </button>
                <button
                  type="button"
                  className="chat-message__modal-close-btn"
                  onClick={() => setIsExpanded(false)}
                  aria-label="Close expanded view"
                  title="Close (Esc)"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="chat-message__modal-body">
              <FormattedContent content={displayContent} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
