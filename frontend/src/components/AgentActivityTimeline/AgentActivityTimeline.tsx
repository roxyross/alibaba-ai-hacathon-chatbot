import React, { useEffect, useState } from 'react';
import './AgentActivityTimeline.css';

interface AgentActivityTimelineProps {
  isStreaming: boolean;
  prompt?: string;
  onStop?: () => void;
  onReplyNow?: () => void;
  agentSlug?: string;
}

export const AgentActivityTimeline: React.FC<AgentActivityTimelineProps> = ({
  isStreaming,
  prompt,
  onStop,
  onReplyNow,
  agentSlug = 'coordinator',
}) => {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!isStreaming) {
      return;
    }
    setSeconds(0);
    const timer = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [isStreaming]);

  if (!isStreaming) return null;

  // Extract a brief contextual task name from the prompt if available
  const taskLabel = prompt
    ? prompt.length > 36
      ? prompt.slice(0, 36).trim() + '…'
      : prompt
    : 'agent status response';

  return (
    <div className="agent-timeline" role="region" aria-label="Agent generating status">
      <div className="agent-timeline__steps">
        {/* Step 1: Idea / Reasoning */}
        <div className="agent-timeline__step agent-timeline__step--complete">
          <div className="agent-timeline__icon-wrapper">
            <span className="agent-timeline__icon">💡</span>
          </div>
          <div className="agent-timeline__content">
            <span className="agent-timeline__title">
              Generating the {taskLabel.toLowerCase()}
            </span>
          </div>
        </div>

        <div className="agent-timeline__connector" />

        {/* Step 2: Browsed Tab / Context */}
        <div className="agent-timeline__step agent-timeline__step--complete">
          <div className="agent-timeline__icon-wrapper">
            <span className="agent-timeline__icon">🌐</span>
          </div>
          <div className="agent-timeline__content">
            <span className="agent-timeline__title">
              Browsed tab <code className="agent-timeline__code">roxy-personal-ai.vercel.app</code>
            </span>
          </div>
        </div>

        <div className="agent-timeline__connector" />

        {/* Step 3: Search / Retrieval */}
        <div className="agent-timeline__step agent-timeline__step--complete">
          <div className="agent-timeline__icon-wrapper">
            <span className="agent-timeline__icon">🔍</span>
          </div>
          <div className="agent-timeline__content">
            <span className="agent-timeline__title">
              Ran 1 search {agentSlug !== 'general' && `(${agentSlug})`}
            </span>
          </div>
        </div>

        {/* Live Stopwatch Badge & Action Buttons */}
        <div className="agent-timeline__footer">
          <div className="agent-timeline__timer">
            <span className="agent-timeline__pulse-dot" />
            <span className="agent-timeline__timer-text">
              Working for {seconds}s
            </span>
          </div>

          <div className="agent-timeline__controls">
            {onReplyNow && (
              <button
                type="button"
                className="agent-timeline__btn agent-timeline__btn--reply"
                onClick={onReplyNow}
                title="Jump directly to the live response"
              >
                <span>⚡ Reply now</span>
              </button>
            )}

            {onStop && (
              <button
                type="button"
                className="agent-timeline__btn agent-timeline__btn--stop"
                onClick={onStop}
                title="Stop generating"
              >
                <span>⏹ Stop</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
