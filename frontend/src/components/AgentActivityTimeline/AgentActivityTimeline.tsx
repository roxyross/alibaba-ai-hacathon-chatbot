import React, { useEffect, useState } from 'react';
import './AgentActivityTimeline.css';

interface AgentActivityTimelineProps {
  isStreaming: boolean;
  prompt?: string;
  agentSlug?: string;
}

export const AgentActivityTimeline: React.FC<AgentActivityTimelineProps> = ({
  isStreaming,
  agentSlug = 'roxy',
}) => {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!isStreaming) return;
    setSeconds(0);
    const timer = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [isStreaming]);

  if (!isStreaming) return null;

  return (
    <div className="agent-timeline" role="region" aria-label="Agent generating response">
      <div className="agent-timeline__inner">
        <div className="agent-timeline__status">
          <span className="agent-timeline__pulse-dot" />
          <span className="agent-timeline__label">
            Thinking &amp; synthesizing
          </span>
          <span className="agent-timeline__time">{seconds}s</span>
          {agentSlug && agentSlug !== 'general' && agentSlug !== 'coordinator' && (
            <span className="agent-timeline__agent-tag">{agentSlug}</span>
          )}
        </div>
      </div>
    </div>
  );
};
