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
