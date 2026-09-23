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

export interface SourceItem {
  id: string;
  title: string;
  url?: string;
  domain?: string;
  snippet?: string;
  type: 'youtube' | 'search' | 'pdf' | 'vault' | 'web';
  citationNumber?: number;
}

function parseDomain(urlStr?: string): string | undefined {
  if (!urlStr) return undefined;
  try {
    const parsed = new URL(urlStr);
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return undefined;
  }
}

function determineSourceType(urlStr?: string, title?: string): SourceItem['type'] {
  const target = `${urlStr || ''} ${title || ''}`.toLowerCase();
  if (target.includes('youtube.com') || target.includes('youtu.be')) return 'youtube';
  if (target.includes('google.com/search') || target.includes('bing.com') || target.includes('duckduckgo.com')) return 'search';
  if (target.includes('.pdf') || target.includes('/pdf/')) return 'pdf';
  if (target.includes('vault') || target.includes('document') || target.includes('knowledge')) return 'vault';
  return 'web';
}

function extractSources(content: string, attribution?: Attribution): SourceItem[] {
  const sourcesMap = new Map<string, SourceItem>();

  // 1. Any sources from backend attribution
  const attrRecord = attribution as unknown as Record<string, unknown> | undefined;
  if (attrRecord && Array.isArray(attrRecord.sources)) {
    for (const src of attrRecord.sources as Array<Record<string, unknown> | string>) {
      if (!src) continue;
      const url = typeof src === 'string' ? src : (src.url as string | undefined);
      const title = typeof src === 'object' && src.title ? (src.title as string) : url || 'Document';
      const key = (url || title).trim().toLowerCase();
      if (!sourcesMap.has(key)) {
        const domain = parseDomain(url) || (typeof src === 'object' && src.type === 'vault' ? 'Knowledge Vault' : undefined);
        sourcesMap.set(key, {
          id: `src-${sourcesMap.size + 1}`,
          title: typeof src === 'object' && src.title ? (src.title as string) : title,
          url,
          domain,
          snippet: typeof src === 'object' && src.snippet ? (src.snippet as string) : undefined,
          type: (typeof src === 'object' && src.type as SourceItem['type']) || determineSourceType(url, title),
          citationNumber: sourcesMap.size + 1,
        });
      }
    }
  }

  // 2. Bracketed sources in content: [Source: ...], [Sources: ...], [Vault: ...]
  const bracketRegex = /\[(?:Source|Sources|Vault|Document|Ref):\s*([^\]]+)\]/gi;
  let bMatch: RegExpExecArray | null;
  while ((bMatch = bracketRegex.exec(content)) !== null) {
    const rawContent = bMatch[1].trim();
    const parts = rawContent.split(/[,;]\s*(?=[A-Za-z0-9])/);
    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed) continue;
      const titleUrlMatch = /^(.*?)\s*\((https?:\/\/[^\s)]+)\)$/.exec(trimmed);
      let title = trimmed;
      let url: string | undefined = undefined;
      if (titleUrlMatch) {
        title = titleUrlMatch[1].trim() || titleUrlMatch[2];
        url = titleUrlMatch[2].trim();
      } else if (/^https?:\/\//i.test(trimmed)) {
        url = trimmed;
        title = parseDomain(trimmed) || trimmed;
      }
      const key = (url || title).trim().toLowerCase();
      if (!sourcesMap.has(key)) {
        const domain = parseDomain(url) || (!url ? 'Knowledge Vault' : undefined);
        sourcesMap.set(key, {
          id: `src-${sourcesMap.size + 1}`,
          title,
          url,
          domain,
          type: determineSourceType(url, title),
          citationNumber: sourcesMap.size + 1,
        });
      }
    }
  }

  // 3. Markdown links: [Title](https://...)
  const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let lMatch: RegExpExecArray | null;
  while ((lMatch = linkRegex.exec(content)) !== null) {
    const title = lMatch[1].trim();
    const url = lMatch[2].trim();
    if (url.startsWith('http://') || url.startsWith('https://')) {
      const key = url.toLowerCase();
      if (!sourcesMap.has(key)) {
        const domain = parseDomain(url);
        sourcesMap.set(key, {
          id: `src-${sourcesMap.size + 1}`,
          title: title || domain || url,
          url,
          domain,
          type: determineSourceType(url, title),
          citationNumber: sourcesMap.size + 1,
        });
      }
    }
  }

  return Array.from(sourcesMap.values());
}

function parseContentWithReasoning(rawContent: string): {
  reasoning: string | null;
  mainContent: string;
  isThinkingActive: boolean;
} {
  if (!rawContent) {
    return { reasoning: null, mainContent: '', isThinkingActive: false };
  }

  const openTagIdx = rawContent.indexOf('<think>');
  if (openTagIdx === -1) {
    return { reasoning: null, mainContent: rawContent, isThinkingActive: false };
  }

  const beforeThink = rawContent.substring(0, openTagIdx).trim();
  const afterOpenTag = rawContent.substring(openTagIdx + '<think>'.length);
  const closeTagIdx = afterOpenTag.indexOf('</think>');

  if (closeTagIdx !== -1) {
    const reasoning = afterOpenTag.substring(0, closeTagIdx).trim();
    const afterThink = afterOpenTag.substring(closeTagIdx + '</think>'.length).trim();
    const mainContent = beforeThink ? `${beforeThink}\n\n${afterThink}` : afterThink;
    return {
      reasoning: reasoning || null,
      mainContent,
      isThinkingActive: false,
    };
  } else {
    // Unclosed <think> — actively streaming reasoning
    const reasoning = afterOpenTag.trim();
    return {
      reasoning: reasoning || null,
      mainContent: beforeThink,
      isThinkingActive: true,
    };
  }
}

function FormattedContent({
  content,
  onSelectCitation,
}: {
  content: string;
  onSelectCitation?: (num: number) => void;
}) {
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
          const inlineRegex = /(\*\*.*?\*\*|`.*?`|\[.*?\]\(https?:\/\/[^\s)]+\)|\[\^?\d+\]|\[(?:Source|Sources|Vault|Document|Ref):\s*[^\]]+\])/gi;
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
            } else if (/^\[\^?\d+\]$/.test(matchedToken)) {
              const num = parseInt(matchedToken.replace(/[^0-9]/g, ''), 10);
              formattedParts.push(
                <button
                  key={`cite-${inlineMatch.index}`}
                  type="button"
                  className="chat-message__citation-chip"
                  onClick={() => onSelectCitation?.(num)}
                  title={`Jump to source [${num}]`}
                  aria-label={`Citation ${num}`}
                >
                  {num}
                </button>
              );
            } else if (/^\[(?:Source|Sources|Vault|Document|Ref):\s*[^\]]+\]$/i.test(matchedToken)) {
              const srcMatch = /^\[(?:Source|Sources|Vault|Document|Ref):\s*([^\]]+)\]$/i.exec(matchedToken);
              const label = srcMatch ? srcMatch[1].trim() : matchedToken;
              formattedParts.push(
                <span key={`src-badge-${inlineMatch.index}`} className="chat-message__inline-source-badge">
                  <span className="chat-message__inline-source-icon">📑</span>
                  <span>{label}</span>
                </span>
              );
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
                    <svg className="chat-message__inline-link-icon" viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
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
  const [showReasoning, setShowReasoning] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const referencesRef = useRef<HTMLDivElement>(null);

  const { reasoning, mainContent, isThinkingActive } = React.useMemo(() => {
    return parseContentWithReasoning(displayContent);
  }, [displayContent]);

  const extractedSources = React.useMemo(() => {
    return extractSources(displayContent, attribution);
  }, [displayContent, attribution]);

  // Keep reasoning accordion open during active streaming of thinking
  useEffect(() => {
    if (isThinkingActive) {
      setShowReasoning(true);
    }
  }, [isThinkingActive]);

  const handleSelectCitation = (citationNum: number) => {
    setShowReferences(true);
    setTimeout(() => {
      const el = document.getElementById(`ref-card-${citationNum}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        el.classList.add('chat-message__ref-card--highlight');
        setTimeout(() => el.classList.remove('chat-message__ref-card--highlight'), 2000);
      }
    }, 100);
  };

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

    const textToSpeak = (mainContent || displayContent)
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
      await navigator.clipboard.writeText(mainContent || displayContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = mainContent || displayContent;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([mainContent || displayContent], { type: 'text/markdown;charset=utf-8' });
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
            {reasoning && (
              <div className="chat-message__reasoning-accordion">
                <button
                  type="button"
                  className={`chat-message__reasoning-toggle ${showReasoning ? 'chat-message__reasoning-toggle--open' : ''}`}
                  onClick={() => setShowReasoning((prev) => !prev)}
                  aria-expanded={showReasoning}
                  title={showReasoning ? 'Collapse thought process' : 'Expand thought process'}
                >
                  <span className="chat-message__reasoning-icon">🧠</span>
                  <span className="chat-message__reasoning-title">
                    {isThinkingActive ? 'Thinking & reasoning...' : 'Thought Process'}
                  </span>
                  {isThinkingActive && <span className="chat-message__reasoning-pulse" />}
                  <span className="chat-message__reasoning-chevron">
                    {showReasoning ? '▲' : '▼'}
                  </span>
                </button>
                {showReasoning && (
                  <div className="chat-message__reasoning-body">
                    <pre className="chat-message__reasoning-text">{reasoning}</pre>
                  </div>
                )}
              </div>
            )}

            {mainContent ? (
              <FormattedContent content={mainContent} onSelectCitation={handleSelectCitation} />
            ) : isStreaming && !reasoning ? (
              <div className="chat-message__shimmer-skeleton" aria-label="Thinking...">
                <div className="chat-message__shimmer-line chat-message__shimmer-line--long" />
                <div className="chat-message__shimmer-line chat-message__shimmer-line--medium" />
                <div className="chat-message__shimmer-line chat-message__shimmer-line--short" />
              </div>
            ) : null}
            {isStreaming && (mainContent || reasoning) && (
              <span className="chat-message__cursor" aria-hidden="true" />
            )}
          </>
        )}
      </div>

      {/* Inline References Citation Control immediately after completed assistant response */}
      {role === 'assistant' && !isStreaming && !isEditing && extractedSources.length > 0 && (
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
                {extractedSources.length} source{extractedSources.length > 1 ? 's' : ''}
              </span>
              <span className="chat-message__ref-pill-chevron" aria-hidden="true">
                {showReferences ? '▲' : '▼'}
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
                  <strong>Sources &amp; References ({extractedSources.length})</strong>
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
                {extractedSources.map((source, idx) => (
                  <div
                    key={source.id || idx}
                    id={`ref-card-${source.citationNumber || idx + 1}`}
                    className="chat-message__ref-card"
                  >
                    <div className="chat-message__ref-card-icon">
                      {source.type === 'youtube' ? (
                        <span className="chat-message__ref-icon--youtube" title="YouTube video">▶</span>
                      ) : source.type === 'pdf' ? (
                        <span className="chat-message__ref-icon--pdf" title="PDF document">📕</span>
                      ) : source.type === 'vault' ? (
                        <span className="chat-message__ref-icon--vault" title="Knowledge Vault document">📑</span>
                      ) : source.type === 'search' ? (
                        <span className="chat-message__ref-icon--search" title="Web search">🔍</span>
                      ) : source.domain ? (
                        <img
                          src={`https://www.google.com/s2/favicons?domain=${source.domain}&sz=32`}
                          alt=""
                          className="chat-message__ref-favicon"
                          onError={(e) => {
                            (e.currentTarget as HTMLElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <span className="chat-message__ref-icon--web">🌐</span>
                      )}
                    </div>

                    <div className="chat-message__ref-card-text">
                      <div className="chat-message__ref-card-header-row">
                        {source.citationNumber && (
                          <span className="chat-message__ref-card-num">[{source.citationNumber}]</span>
                        )}
                        {source.url ? (
                          <a
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="chat-message__ref-card-title-link"
                            title={source.url}
                          >
                            {source.title}
                            <svg className="chat-message__ref-external-icon" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                              <polyline points="15 3 21 3 21 9" />
                              <line x1="10" y1="14" x2="21" y2="3" />
                            </svg>
                          </a>
                        ) : (
                          <span className="chat-message__ref-card-title">{source.title}</span>
                        )}
                      </div>

                      <div className="chat-message__ref-card-meta">
                        {source.domain && (
                          <span className="chat-message__ref-card-domain">{source.domain}</span>
                        )}
                        <span className="chat-message__ref-card-type-badge">
                          {source.type === 'vault' ? 'Vault Document' : source.type === 'youtube' ? 'Video' : source.type === 'pdf' ? 'PDF' : source.type === 'search' ? 'Search Result' : 'Web Page'}
                        </span>
                      </div>

                      {source.snippet && (
                        <p className="chat-message__ref-card-snippet">{source.snippet}</p>
                      )}
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
              {reasoning && (
                <div className="chat-message__reasoning-accordion chat-message__reasoning-accordion--modal">
                  <div className="chat-message__reasoning-toggle" style={{ cursor: 'default' }}>
                    <span className="chat-message__reasoning-icon">🧠</span>
                    <span className="chat-message__reasoning-title">Thought Process</span>
                  </div>
                  <div className="chat-message__reasoning-body">
                    <pre className="chat-message__reasoning-text">{reasoning}</pre>
                  </div>
                </div>
              )}
              <FormattedContent content={mainContent || displayContent} onSelectCitation={handleSelectCitation} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
