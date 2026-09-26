/* ChatWindow — Modern ChatGPT/Claude Style Chat Interface with Developer Task Workspace */

import React, { useCallback, useRef, useState, useEffect } from 'react';
import { Code2, Zap } from 'lucide-react';
import { ChatMessage } from '../ChatMessage';
import { ChatInput } from '../ChatInput';
import { AgentActivityTimeline } from '../AgentActivityTimeline';
import { TaskActivityCard } from '../TaskActivityCard';
import { TaskWorkspacePanel } from '../TaskWorkspacePanel';
import { ModelPicker, type ModelSelection } from '../../model_provider';
import type { ChatState } from '../../hooks/useChat';
import './ChatWindow.css';

interface ChatWindowProps extends ChatState {
  onSend: (message: string) => void;
  modelSelection?: ModelSelection | null;
  onModelChange?: (model: ModelSelection) => void;
  onVoiceClick?: () => void;
  onAttachmentClick?: () => void;
  disabledNoModel?: boolean;
  mode?: 'chat' | 'task';
  accessToken?: string | null;
  activeSessionId?: string | null;
  taskTitle?: string;
  onNavigateView?: (view: 'finance' | 'jobs' | 'email' | 'calculator' | 'calendar') => void;
  onStop?: () => void;
  onClearConversation?: () => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  attribution,
  isStreaming,
  error,
  criticReview,
  nextActions,
  onSend,
  modelSelection,
  onModelChange,
  onVoiceClick,
  onAttachmentClick,
  disabledNoModel = false,
  mode = 'chat',
  accessToken,
  activeSessionId,
  taskTitle,
  onNavigateView,
  onStop,
  onClearConversation,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Developer Workspace open state in task mode
  const [isWorkspaceOpen, setIsWorkspaceOpen] = useState(false);

  // Auto-open workspace when code actions or events are dispatched from Chat code blocks
  useEffect(() => {
    const handleAutoOpenWorkspace = () => {
      setIsWorkspaceOpen(true);
    };

    window.addEventListener('roxy-open-editor' as any, handleAutoOpenWorkspace);
    window.addEventListener('roxy-run-terminal' as any, handleAutoOpenWorkspace);
    window.addEventListener('roxy-open-diff' as any, handleAutoOpenWorkspace);

    return () => {
      window.removeEventListener('roxy-open-editor' as any, handleAutoOpenWorkspace);
      window.removeEventListener('roxy-run-terminal' as any, handleAutoOpenWorkspace);
      window.removeEventListener('roxy-open-diff' as any, handleAutoOpenWorkspace);
    };
  }, []);

  // Auto-scroll to bottom on new messages or streaming
  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Reply now: reliably locate the active streaming response, scroll into view, and focus
  const handleReplyNow = useCallback(() => {
    const activeEl =
      document.querySelector('.chat-message--streaming .chat-message__cursor') ||
      document.querySelector('.chat-message--streaming .chat-message__bubble') ||
      document.querySelector('.chat-message--streaming') ||
      document.querySelector('.task-activity-card') ||
      document.querySelector('.agent-timeline') ||
      bottomRef.current;

    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'end', inline: 'nearest' });
      if (activeEl instanceof HTMLElement) {
        activeEl.tabIndex = -1;
        activeEl.focus({ preventScroll: true });
      }
    } else if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, []);

  useEffect(() => {
    if (isStreaming || messages.length > 0) {
      scrollToBottom();
    }
  }, [messages, isStreaming, scrollToBottom]);

  const modelPickerSlot = onModelChange ? (
    <ModelPicker value={modelSelection ?? null} onChange={onModelChange} />
  ) : undefined;

  const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user');
  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <main className="chat-window" aria-label="Chat window">
      {isEmpty ? (
        /* ─── Modern ChatGPT-Style Centered Hero (Empty State) ─── */
        <div className="chat-window__hero">
          <div className="chat-window__hero-content">
            <div className="chat-window__hero-badge">
              <span className="chat-window__hero-badge-spark">
                {mode === 'task' ? '⚡' : '✨'}
              </span>
              <span>
                {mode === 'task' ? 'Autonomous Coding Agent & Developer Studio' : 'Next-Gen Multi-Agent Intelligence'}
              </span>
            </div>

            <h1 className="chat-window__hero-title">
              {mode === 'task' ? 'What code shall we build today?' : 'What would you like to accomplish?'}
            </h1>

            <p className="chat-window__hero-subtitle">
              {mode === 'task'
                ? 'Multi-file code generation, TypeScript bug diagnosis, script automation, sandboxed terminal runner, and unified diff review.'
                : 'Fast streaming reasoning, live web context, document understanding, and multi-model synthesis.'}
            </p>

            {/* Centered Single Input Capsule */}
            <div className="chat-window__hero-input-wrapper">
              <ChatInput
                onSend={onSend}
                disabled={false}
                isStreaming={isStreaming}
                disabledNoModel={disabledNoModel}
                leftSlot={modelPickerSlot}
                onVoiceClick={onVoiceClick}
                onAttachmentClick={onAttachmentClick}
                onStop={onStop}
                placeholder={
                  mode === 'task'
                    ? 'Ask to write code, build a script, or debug…'
                    : 'Ask anything, chat, or paste code…'
                }
                onNavigateView={onNavigateView}
              />
            </div>

            {/* 4 Categorized Suggestion Cards */}
            <div className="chat-window__suggestions" role="region" aria-label="Suggested prompts">
              {mode === 'task' ? (
                <>
                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Build a type-safe FastAPI service with JWT authentication, rate limiting, and health checks')}
                  >
                    <div className="chat-window__suggestion-icon">⚡</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">FastAPI &amp; Backend</span>
                      <span className="chat-window__suggestion-text">Build a type-safe FastAPI service with JWT auth</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Debug and fix the TypeScript compilation error in the authentication callback and form validation')}
                  >
                    <div className="chat-window__suggestion-icon">🐞</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Debug &amp; Fix</span>
                      <span className="chat-window__suggestion-text">Fix TypeScript compilation error in auth flow</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Build a Python script that parses, cleans, and aggregates CSV sales data with schema validation')}
                  >
                    <div className="chat-window__suggestion-icon">🐍</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Python &amp; Data Script</span>
                      <span className="chat-window__suggestion-text">Build Python script to parse and aggregate CSV data</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Refactor this React state component into clean custom hooks and verify test coverage')}
                  >
                    <div className="chat-window__suggestion-icon">⚛️</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Refactor &amp; Test</span>
                      <span className="chat-window__suggestion-text">Refactor React component into custom hooks</span>
                    </div>
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Build a type-safe FastAPI service with JWT authentication, rate limiting, and health checks')}
                  >
                    <div className="chat-window__suggestion-icon">⚡</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Code &amp; Architecture</span>
                      <span className="chat-window__suggestion-text">Build a type-safe FastAPI service with JWT auth</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Analyze key performance indicators and revenue growth patterns in modern SaaS platforms')}
                  >
                    <div className="chat-window__suggestion-icon">📊</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Data &amp; Analysis</span>
                      <span className="chat-window__suggestion-text">Analyze KPI metrics and SaaS revenue patterns</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Synthesize the latest research breakthroughs in small reasoning models and test-time compute')}
                  >
                    <div className="chat-window__suggestion-icon">🔍</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Research &amp; Grounding</span>
                      <span className="chat-window__suggestion-text">Synthesize breakthrough research in reasoning models</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className="chat-window__suggestion-card"
                    onClick={() => onSend('Draft a comprehensive launch plan and technical documentation roadmap for a developer product')}
                  >
                    <div className="chat-window__suggestion-icon">💡</div>
                    <div className="chat-window__suggestion-content">
                      <span className="chat-window__suggestion-category">Brainstorm &amp; Strategy</span>
                      <span className="chat-window__suggestion-text">Draft a launch strategy and documentation roadmap</span>
                    </div>
                  </button>
                </>
              )}
            </div>

            {/* Capability Badges */}
            <div className="chat-window__capabilities">
              {mode === 'task' ? (
                <>
                  <span className="chat-window__capability-chip">💻 Sandboxed Subprocess</span>
                  <span className="chat-window__capability-chip">📁 Workspace Files</span>
                  <span className="chat-window__capability-chip">📝 Code Editor</span>
                  <span className="chat-window__capability-chip">🔄 Unified Diff</span>
                  <span className="chat-window__capability-chip">⚡ Subprocess Terminal</span>
                </>
              ) : (
                <>
                  <span className="chat-window__capability-chip">🌐 Live Web Search</span>
                  <span className="chat-window__capability-chip">📑 Document Vision</span>
                  <span className="chat-window__capability-chip">🎙️ Voice Mode</span>
                  <span className="chat-window__capability-chip">🧠 Deep Reasoning</span>
                </>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* ─── Active Conversation View with Optional Side-by-Side Workspace ─── */
        <div className={`chat-window__container ${isWorkspaceOpen && mode === 'task' ? 'chat-window__container--split' : ''}`}>
          <div className="chat-window__chat-pane">
            <section
              ref={scrollContainerRef}
              className="chat-window__messages"
              aria-label="Messages"
              aria-live="polite"
              aria-atomic="false"
            >
              {/* In-chat Context Pill & Action Bar */}
              <div className="chat-window__context-bar">
                {mode === 'task' ? (
                  <div className="chat-window__context-pill chat-window__context-pill--task">
                    <Zap size={12} className="chat-window__context-task-icon" />
                    <span>Task Mode</span>
                    <span className="chat-window__context-dot">·</span>
                    <span className="chat-window__context-model">
                      {taskTitle || modelSelection?.model || 'Coding Agent'}
                    </span>
                    <span className="chat-window__context-dot">·</span>
                    <span className="chat-window__context-status">Workspace: main</span>
                  </div>
                ) : (
                  <div className="chat-window__context-pill">
                    <span className="chat-window__context-icon">🧠</span>
                    <span>Active Context: {messages.length} messages</span>
                    <span className="chat-window__context-dot">·</span>
                    <span className="chat-window__context-model">
                      {modelSelection?.model || 'Coordinator Agent'}
                    </span>
                    <span className="chat-window__context-dot">·</span>
                    <span className="chat-window__context-status">Memory Active</span>
                  </div>
                )}

                <div className="chat-window__context-actions">
                  {mode === 'task' && (
                    <button
                      type="button"
                      className={`chat-window__workspace-toggle ${isWorkspaceOpen ? 'chat-window__workspace-toggle--active' : ''}`}
                      onClick={() => setIsWorkspaceOpen((v) => !v)}
                      title="Toggle Developer Workspace (Files, Editor, Terminal, Diff, Preview)"
                      aria-label="Toggle Developer Workspace"
                    >
                      <Code2 size={13} />
                      <span>{isWorkspaceOpen ? 'Hide Workspace' : 'Workspace'}</span>
                    </button>
                  )}

                  {onClearConversation && (
                    <button
                      type="button"
                      className="chat-window__clear-btn"
                      onClick={() => {
                        if (window.confirm('Clear active conversation messages?')) {
                          onClearConversation();
                        }
                      }}
                      title="Clear active conversation"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                      <span>Clear</span>
                    </button>
                  )}
                </div>
              </div>

              <div className="chat-window__messages-inner">
                {messages.map((msg, i) => {
                  const isLastAssistant =
                    msg.role === 'assistant' &&
                    i === messages.findIndex((m) => m.role === 'assistant') + messages.filter((m) => m.role === 'assistant').length - 1;
                  const showAttribution =
                    msg.role === 'assistant' && (attribution !== null || !isStreaming);

                  return (
                    <ChatMessage
                      key={i}
                      role={msg.role}
                      content={msg.content}
                      attribution={msg.role === 'assistant' && showAttribution ? attribution ?? undefined : undefined}
                      criticReview={msg.role === 'assistant' ? criticReview ?? null : null}
                      isStreaming={isLastAssistant && isStreaming}
                      onRegenerate={
                        isLastAssistant && !isStreaming
                          ? () => {
                              if (lastUserMessage?.content) onSend(lastUserMessage.content);
                            }
                          : undefined
                      }
                    />
                  );
                })}

                {/* Truthful Agent Activity Timeline during streaming */}
                {isStreaming && (
                  mode === 'task' ? (
                    <TaskActivityCard
                      isStreaming={isStreaming}
                      prompt={lastUserMessage?.content}
                      activeSessionId={activeSessionId}
                      onOpenWorkspace={() => setIsWorkspaceOpen(true)}
                    />
                  ) : (
                    <AgentActivityTimeline
                      isStreaming={isStreaming}
                      prompt={lastUserMessage?.content}
                      agentSlug={attribution?.agentSlug || 'coordinator'}
                    />
                  )
                )}

                {/* Error card with inline Retry */}
                {error && (
                  <div className="chat-window__error-card" role="alert" aria-live="assertive">
                    <div className="chat-window__error-content">
                      <span className="chat-window__error-icon">⚠️</span>
                      <div className="chat-window__error-text">
                        <strong>Generation Error:</strong> {error}
                      </div>
                    </div>
                    {lastUserMessage?.content && (
                      <button
                        type="button"
                        className="chat-window__error-retry-btn"
                        onClick={() => onSend(lastUserMessage.content)}
                        title="Retry sending previous prompt"
                      >
                        🔄 Retry Turn
                      </button>
                    )}
                  </div>
                )}

                <div ref={bottomRef} aria-hidden="true" />
              </div>
            </section>

            {/* Coordinator Next-Action Chips */}
            {nextActions && nextActions.length > 0 && (
              <div className="chat-window__next-actions" role="toolbar" aria-label="Suggested next actions">
                {nextActions.map((action, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="chat-window__action-chip"
                    onClick={() => onSend(action)}
                  >
                    {action}
                  </button>
                ))}
              </div>
            )}

            {/* Floating Bottom Single Input */}
            <div className="chat-window__bottom-bar">
              <div className="chat-window__bottom-bar-inner">
                {isStreaming && (
                  <div className="chat-window__floating-reply-pill">
                    <button
                      type="button"
                      className="chat-window__reply-pill-btn"
                      onClick={handleReplyNow}
                      title="Jump to live response"
                      aria-label="Jump to live response"
                    >
                      <span className="chat-window__reply-pill-dot" />
                      <span>Reply now</span>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <polyline points="19 12 12 19 5 12" />
                      </svg>
                    </button>
                  </div>
                )}

                <ChatInput
                  onSend={onSend}
                  disabled={false}
                  isStreaming={isStreaming}
                  disabledNoModel={disabledNoModel}
                  leftSlot={modelPickerSlot}
                  onVoiceClick={onVoiceClick}
                  onAttachmentClick={onAttachmentClick}
                  onStop={onStop}
                  placeholder={
                    mode === 'task'
                      ? 'Ask to write code, build a script, or debug…'
                      : 'Ask anything, chat, or paste code…'
                  }
                  onNavigateView={onNavigateView}
                />
              </div>
            </div>
          </div>

          {/* Docked / Split Developer Workspace Pane */}
          {isWorkspaceOpen && mode === 'task' && (
            <div className="chat-window__workspace-pane">
              <TaskWorkspacePanel
                isOpen={isWorkspaceOpen}
                onClose={() => setIsWorkspaceOpen(false)}
                accessToken={accessToken}
                activeSessionId={activeSessionId}
                taskTitle={taskTitle}
                onSendToChat={onSend}
              />
            </div>
          )}
        </div>
      )}
    </main>
  );
};
