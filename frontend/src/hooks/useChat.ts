// useChat — Runtime Coordinator hook
// Calls POST /api/v1/runtime/chat (one-shot JSON) or
// POST /api/v1/runtime/chat/stream (SSE streaming) when streaming=true.

import { useCallback, useRef, useState } from 'react';

/** Attribution metadata for the last completed turn (Coordinator agent slug). */
export interface Attribution {
  agentSlug: string;
  provider?: string;
  model?: string;
}

export interface UseChatOptions {
  apiBase?: string;
  runtimeUrl?: string;
  provider?: string;
  model?: string;
  sessionId?: string | null;
  accessToken?: string | null;
  /** Use SSE streaming instead of one-shot (default: false) */
  streaming?: boolean;
}

export interface ChatState {
  messages: { role: 'user' | 'assistant'; content: string }[];
  attribution: Attribution | null;
  isStreaming: boolean;
  error: string | null;
  needsClarification: boolean;
  nextActions: string[];
  criticReview?: Record<string, unknown> | null;
}

const RUNTIME_CHAT_PATH = '/api/v1/runtime/chat';
const RUNTIME_STREAM_PATH = '/api/v1/runtime/chat/stream';

export function useChat(options: UseChatOptions = {}) {
  const [state, setState] = useState<ChatState>({
    messages: [],
    attribution: null,
    isStreaming: false,
    error: null,
    needsClarification: false,
    nextActions: [],
    criticReview: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string, overrideSessionId?: string) => {
      const useStreaming = options.streaming;
      const targetSessionId = overrideSessionId || options.sessionId;

      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, { role: 'user', content }],
        attribution: null,
        isStreaming: true,
        error: null,
        needsClarification: false,
        nextActions: [],
        criticReview: null,
      }));

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };
        if (options.accessToken) {
          headers.Authorization = `Bearer ${options.accessToken}`;
        }

        const baseUrl = options.runtimeUrl ?? options.apiBase ?? '/api/v1';
        const path = useStreaming ? RUNTIME_STREAM_PATH : RUNTIME_CHAT_PATH;

        if (useStreaming) {
          // SSE streaming
          const response = await fetch(`${baseUrl}${path}`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              message: content,
              ...(targetSessionId ? { session_id: targetSessionId } : {}),
              ...(options.provider ? { provider: options.provider } : {}),
              ...(options.model ? { model: options.model } : {}),
            }),
            signal: abortRef.current.signal,
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          if (!response.body) {
            throw new Error('No response body for streaming');
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let accumulated = '';
          let agentSlug = '';
          let provider = '';
          let model = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed.startsWith('data: ')) continue;
              const data = trimmed.slice('data: '.length);
              if (data.startsWith(': ')) continue;

              try {
                const parsed = JSON.parse(data);

                if (parsed.type === 'critic_review') {
                  setState((prev) => ({ ...prev, criticReview: parsed.review }));
                  continue;
                }

                if (parsed.event === 'attribution') {
                  setState((prev) => ({
                    ...prev,
                    attribution: {
                      agentSlug: parsed.agent_slug ?? agentSlug,
                      provider: parsed.provider ?? provider,
                      model: parsed.model ?? model,
                    },
                  }));
                  continue;
                }

                if (parsed.done) {
                  setState((prev) => ({
                    ...prev,
                    isStreaming: false,
                    attribution: {
                      agentSlug: parsed.agent_slug ?? agentSlug,
                      provider: parsed.provider ?? provider,
                      model: parsed.model ?? model,
                    },
                  }));
                  accumulated = '';
                  continue;
                }

                if (parsed.delta) {
                  accumulated += parsed.delta;
                  agentSlug = parsed.agent_slug ?? agentSlug;
                  provider = parsed.provider ?? provider;
                  model = parsed.model ?? model;

                  setState((prev) => {
                    const msgs = [...prev.messages];
                    const last = msgs[msgs.length - 1];
                    if (last?.role === 'assistant') {
                      msgs[msgs.length - 1] = { role: 'assistant', content: accumulated };
                    } else {
                      msgs.push({ role: 'assistant', content: accumulated });
                    }
                    return { ...prev, messages: msgs };
                  });
                }
              } catch {
                // Skip malformed JSON
              }
            }
          }
          setState((prev) => ({ ...prev, isStreaming: false }));
        } else {
          // One-shot JSON
          const response = await fetch(`${baseUrl}${path}`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              message: content,
              ...(targetSessionId ? { session_id: targetSessionId } : {}),
              ...(options.provider ? { provider: options.provider } : {}),
              ...(options.model ? { model: options.model } : {}),
            }),
            signal: abortRef.current.signal,
          });

          if (!response.ok) {
            const errText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errText || response.statusText}`);
          }

          const data = await response.json();

          if (data.status === 'error' || data.error) {
            const errorMsg = data.detail || data.error || 'Unknown error';
            setState((prev) => ({
              ...prev,
              isStreaming: false,
              error: errorMsg,
              messages: [
                ...prev.messages,
                { role: 'assistant', content: `Error: ${errorMsg}` },
              ],
            }));
            return;
          }

          let assistantContent = data.response || data.content || '';
          if (!assistantContent && data.next_actions && data.next_actions.length > 0) {
            assistantContent = data.next_actions.join('\n\n');
          }
          if (!assistantContent) {
            assistantContent = "Hello! I received your message. How can I assist you today?";
          }

          setState((prev) => ({
            ...prev,
            messages: [
              ...prev.messages,
              { role: 'assistant', content: assistantContent },
            ],
            attribution: data.agent_slug
              ? { agentSlug: data.agent_slug }
              : null,
            needsClarification: data.needs_clarification ?? false,
            nextActions: data.next_actions ?? [],
            criticReview: data.critic_review ?? null,
            isStreaming: false,
          }));
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        const msg = (err as Error).message || 'Failed to communicate with assistant';
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: msg,
          messages: [
            ...prev.messages,
            { role: 'assistant', content: `Unable to get response: ${msg}` },
          ],
        }));
      }
    },
    [
      options.apiBase,
      options.runtimeUrl,
      options.provider,
      options.model,
      options.sessionId,
      options.accessToken,
      options.streaming,
    ],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, isStreaming: false }));
  }, []);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setState({
      messages: [],
      attribution: null,
      isStreaming: false,
      error: null,
      needsClarification: false,
      nextActions: [],
      criticReview: null,
    });
  }, []);

  return { ...state, sendMessage, abort, clearMessages };
}

