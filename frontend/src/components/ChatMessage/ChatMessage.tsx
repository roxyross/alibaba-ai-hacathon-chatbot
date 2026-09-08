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

interface MapCardData {
  place: string;
  query?: string;
  lat: number;
  lon: number;
  zoom?: number;
  embed_osm?: string;
  embed_google?: string;
  gmaps_search?: string;
  directions?: string;
  osm_url?: string;
}

function InteractiveMapCard({ data }: { data: MapCardData }) {
  const [provider, setProvider] = useState<'google' | 'osm'>('google');
  const [copied, setCopied] = useState(false);

  const lat = Number(data.lat) || 0;
  const lon = Number(data.lon) || 0;
  const zoom = Number(data.zoom) || 14;

  const osmUrl =
    data.embed_osm ||
    `https://www.openstreetmap.org/export/embed.html?bbox=${(lon - 0.015).toFixed(5)}%2C${(lat - 0.010).toFixed(5)}%2C${(lon + 0.015).toFixed(5)}%2C${(lat + 0.010).toFixed(5)}&layer=mapnik&marker=${lat.toFixed(5)}%2C${lon.toFixed(5)}`;

  const googleUrl =
    data.embed_google ||
    `https://maps.google.com/maps?q=${lat},${lon}&hl=en&z=${zoom}&output=embed`;

  const gmapsSearchUrl =
    data.gmaps_search ||
    `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(data.place || `${lat},${lon}`)}`;

  const directionsUrl =
    data.directions ||
    `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;

  const osmDirectUrl =
    data.osm_url ||
    `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=${zoom}/${lat}/${lon}`;

  const handleCopy = () => {
    const coords = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    navigator.clipboard.writeText(coords).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="chat-map-card">
      <div className="chat-map-card__header">
        <div className="chat-map-card__title-row">
          <span className="chat-map-card__pin-icon" aria-hidden="true">📍</span>
          <div className="chat-map-card__title-meta">
            <span className="chat-map-card__title">{data.place || 'Map Location'}</span>
            <button
              type="button"
              className="chat-map-card__coords"
              onClick={handleCopy}
              title="Click to copy coordinates"
            >
              {copied ? '✓ Copied' : `${lat.toFixed(4)}°, ${lon.toFixed(4)}°`}
            </button>
          </div>
        </div>

        <div className="chat-map-card__tabs" role="tablist">
          <button
            type="button"
            className={`chat-map-card__tab ${provider === 'google' ? 'chat-map-card__tab--active' : ''}`}
            onClick={() => setProvider('google')}
          >
            Google Maps
          </button>
          <button
            type="button"
            className={`chat-map-card__tab ${provider === 'osm' ? 'chat-map-card__tab--active' : ''}`}
            onClick={() => setProvider('osm')}
          >
            OpenStreetMap
          </button>
        </div>
      </div>

      <div className="chat-map-card__viewport">
        <iframe
          key={provider}
          src={provider === 'google' ? googleUrl : osmUrl}
          className="chat-map-card__iframe"
          title={`Map of ${data.place || 'location'}`}
          loading="lazy"
          allowFullScreen
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>

      <div className="chat-map-card__actions">
        <a
          href={gmapsSearchUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="chat-map-card__btn"
        >
          <span>📍</span> Open in Google Maps
        </a>
        <a
          href={directionsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="chat-map-card__btn"
        >
          <span>🧭</span> Directions
        </a>
        <a
          href={osmDirectUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="chat-map-card__btn"
        >
          <span>🌐</span> OpenStreetMap
        </a>
      </div>
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
    if (lang === 'map') {
      try {
        const mapData = JSON.parse(code.trim());
        tokens.push(
          <InteractiveMapCard key={`map-${match.index}`} data={mapData} />
        );
      } catch {
        tokens.push(
          <CodeBlock key={`code-${match.index}`} lang={lang} code={code} />
        );
      }
    } else {
      tokens.push(
        <CodeBlock key={`code-${match.index}`} lang={lang} code={code} />
      );
    }
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
  const [displayContent, setDisplayContent] = useState(content);
  const [isEditing, setIsEditing] = useState(false);
  const [draftContent, setDraftContent] = useState(content);
  const [copied, setCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  React.useEffect(() => {
    setDisplayContent(content);
    setDraftContent(content);
  }, [content]);

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
    a.download = `response-${new Date().toISOString().slice(0, 10)}.md`;
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

  const attributionLabel = attribution
    ? `Response from ${attribution.agentSlug} agent`
    : undefined;

  return (
    <>
      <div
        className={`chat-message chat-message--${role} ${isStreaming && role === 'assistant' ? 'chat-message--streaming' : ''} ${isExpanded ? 'chat-message--expanded' : ''}`}
        aria-role={role === 'user' ? 'presentation' : 'article'}
      >
        <div className="chat-message__bubble">
          {role === 'assistant' && !isStreaming && (
            <div className="chat-message__topbar">
              <div className="chat-message__topbar-left">
                <button
                  type="button"
                  className={`chat-message__edit-btn ${isEditing ? 'chat-message__edit-btn--active' : ''}`}
                  onClick={() => setIsEditing(!isEditing)}
                  title="Edit response"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
                  </svg>
                  <span>Edit</span>
                </button>
              </div>

              <div className="chat-message__topbar-right">
                <button
                  type="button"
                  className="chat-message__icon-btn"
                  onClick={handleCopy}
                  title={copied ? "Copied to clipboard!" : "Copy response"}
                  aria-label="Copy response"
                >
                  {copied ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  )}
                </button>

                <button
                  type="button"
                  className="chat-message__icon-btn"
                  onClick={handleDownload}
                  title="Download as markdown"
                  aria-label="Download response"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                </button>

                <button
                  type="button"
                  className={`chat-message__icon-btn ${isExpanded ? 'chat-message__icon-btn--active' : ''}`}
                  onClick={() => setIsExpanded(!isExpanded)}
                  title={isExpanded ? "Exit full screen" : "Expand response"}
                  aria-label="Expand response"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 3 21 3 21 9" />
                    <polyline points="9 21 3 21 3 15" />
                    <line x1="21" y1="3" x2="14" y2="10" />
                    <line x1="3" y1="21" x2="10" y2="14" />
                  </svg>
                </button>
              </div>
            </div>
          )}

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
                <span className="chat-message__cursor" aria-hidden="true" />
              ) : null}
              {isStreaming && displayContent && (
                <span className="chat-message__cursor" aria-hidden="true" />
              )}
            </>
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

      {/* Fullscreen modal expanded view */}
      {isExpanded && (
        <div className="chat-message__modal-overlay" onClick={() => setIsExpanded(false)}>
          <div className="chat-message__modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="chat-message__modal-header">
              <span className="chat-message__modal-title">Expanded Response</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <button type="button" className="chat-message__modal-action-btn" onClick={handleCopy}>
                  {copied ? '✓ Copied' : 'Copy'}
                </button>
                <button type="button" className="chat-message__modal-action-btn" onClick={handleDownload}>
                  Download
                </button>
                <button type="button" className="chat-message__modal-close" onClick={() => setIsExpanded(false)}>
                  ✕ Close
                </button>
              </div>
            </div>
            <div className="chat-message__modal-body">
              <FormattedContent content={displayContent} />
            </div>
          </div>
        </div>
      )}
    </>
  );
};
