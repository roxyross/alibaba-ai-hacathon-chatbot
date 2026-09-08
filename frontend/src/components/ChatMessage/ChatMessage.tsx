/* ChatMessage — individual message bubble with optional attribution + critic review */

import React, { useState } from 'react';
import type { Attribution } from '../../hooks/useChat';

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
}

const VERDICT_COLORS: Record<string, string> = {
  strong: '#a6e3a1',
  adequate: '#f9e2af',
  weak: '#f38ba8',
  flawed: '#f38ba8',
};

function CriticReviewBadge({ review }: { review: CriticReviewData | Record<string, unknown> | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!review) return null;

  const verdict = typeof review.verdict === 'string' ? review.verdict : 'unknown';
  const overall = typeof review.overall === 'string' ? review.overall : '';
  const strengths = Array.isArray(review.strengths) ? review.strengths : [];
  const weaknesses = Array.isArray(review.weaknesses) ? review.weaknesses : [];
  const summary = typeof review.summary === 'string' ? review.summary : '';
  const verdictColor = VERDICT_COLORS[verdict] ?? '#f9e2af';

  return (
    <div className="critic-badge" aria-label="Critic review">
      <button
        type="button"
        className="critic-badge__toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="critic-badge__icon">🔍</span>
        <span className="critic-badge__label">Critic Review</span>
        <span
          className="critic-badge__verdict"
          style={{ color: verdictColor }}
        >
          {verdict}
        </span>
        <span className={`critic-badge__chevron ${expanded ? 'critic-badge__chevron--up' : ''}`}>
          ▾
        </span>
      </button>

      {expanded && (
        <div className="critic-badge__body">
          {overall && (
            <p className="critic-badge__overall">
              <strong>Overall:</strong> {overall}
            </p>
          )}

          {strengths.length > 0 && (
            <div className="critic-badge__section">
              <span className="critic-badge__section-title critic-badge__section-title--strong">✓ Strengths</span>
              <ul className="critic-badge__list">
                {strengths.map((s, i) => (
                  <li key={i}>{String(s)}</li>
                ))}
              </ul>
            </div>
          )}

          {weaknesses.length > 0 && (
            <div className="critic-badge__section">
              <span className="critic-badge__section-title critic-badge__section-title--weak">✗ Issues</span>
              <ul className="critic-badge__list">
                {weaknesses.map((w, i) => (
                  <li key={i}>
                    <strong>{typeof w === 'string' ? w : w.name}</strong>
                    {typeof w === 'object' && w.why_it_matters && (
                      <span className="critic-badge__why"> → {w.why_it_matters}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {summary && (
            <p className="critic-badge__summary">
              <em>{summary}</em>
            </p>
          )}
        </div>
      )}
    </div>
  );
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
  criticReview,
  isStreaming = false,
}) => {
  const attributionLabel = attribution
    ? `Response from ${attribution.agentSlug} agent`
    : undefined;

  return (
    <div
      className={`chat-message chat-message--${role} ${isStreaming && role === 'assistant' ? 'chat-message--streaming' : ''}`}
      aria-role={role === 'user' ? 'presentation' : 'article'}
    >
      <div className="chat-message__bubble">
        {content ? (
          <FormattedContent content={content} />
        ) : isStreaming ? (
          <span className="chat-message__cursor" aria-hidden="true" />
        ) : null}
        {isStreaming && content && (
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
              <span className="chat-message__provider">{attribution.agentSlug}</span>
            </>
          ) : (
            <span className="chat-message__provider-unknown">routing…</span>
          )}
        </div>
      )}

      {role === 'assistant' && criticReview && (
        <CriticReviewBadge review={criticReview as CriticReviewData | Record<string, unknown>} />
      )}
    </div>
  );
};
