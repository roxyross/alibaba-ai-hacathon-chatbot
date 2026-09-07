// useStreamingChat — SSE streaming Coordinator hook
// Calls POST /api/v1/runtime/chat/stream and renders deltas as they arrive.

import { useCallback, useRef, useState } from 'react';

export interface StreamingAttribution {
  agentSlug: string;
  provider?: string;
  model?: string;
}

export interface StreamingChatOptions {
  runtimeUrl?: string;
  sessionId?: string | null;
  accessToken?: string | null;
}

export interface StreamingChatState {
  messages: { role: 'user' | 'assistant'; content: string }[];
  attribution: StreamingAttribution | null;
  isStreaming: boolean;
  error: string | null;
  needsClarification: boolean;
  nextActions: string[];
  criticReview: Record<string, unknown> | null;
}

const RUNTIME_STREAM_PATH = '/api/v1/runtime/chat/stream';

export function useStreamingChat(options: StreamingChatOptions = {}) {
  const [state, setState] = useState<StreamingChatState>({
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
    async (content: string) => {
      // Add user message immediately
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

      const baseUrl = options.runtimeUrl ?? 'http://localhost:8000';

      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };
        if (options.accessToken) {
          headers.Authorization = `Bearer ${options.accessToken}`;
        }

        const response = await fetch(
          `${baseUrl}${RUNTIME_STREAM_PATH}`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify({
              message: content,
              ...(options.sessionId ? { session_id: options.sessionId } : {}),
            }),
            signal: abortRef.current.signal,
          },
        );

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

        // Accumulate partial assistant message
        let partialContent = '';

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
            if (data.startsWith(': ')) continue; // SSE comment

            try {
              const parsed = JSON.parse(data);

              if (parsed.type === 'critic_review') {
                setState((prev) => ({
                  ...prev,
                  criticReview: parsed.review,
                }));
                continue;
              }

              if (parsed.event === 'attribution') {
                // Final attribution
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
                // Final chunk — replace partial with complete
                setState((prev) => {
                  const msgs = [...prev.messages];
                  const last = msgs[msgs.length - 1];
                  if (last?.role === 'assistant') {
                    msgs[msgs.length - 1] = {
                      role: 'assistant',
                      content: accumulated || parsed.delta || partialContent,
                    };
                  } else {
                    msgs.push({
                      role: 'assistant',
                      content: accumulated || parsed.delta || partialContent,
                    });
                  }
                  return {
                    ...prev,
                    messages: msgs,
                    isStreaming: false,
                    attribution: {
                      agentSlug: parsed.agent_slug ?? agentSlug,
                      provider: parsed.provider ?? provider,
                      model: parsed.model ?? model,
                    },
                  };
                });
                accumulated = '';
                partialContent = '';
                continue;
              }

              if (parsed.delta) {
                partialContent += parsed.delta;
                accumulated += parsed.delta;
                agentSlug = parsed.agent_slug ?? agentSlug;
                provider = parsed.provider ?? provider;
                model = parsed.model ?? model;

                // Update the last message with partial content
                setState((prev) => {
                  const msgs = [...prev.messages];
                  const last = msgs[msgs.length - 1];
                  if (last?.role === 'assistant') {
                    msgs[msgs.length - 1] = {
                      role: 'assistant',
                      content: accumulated,
                    };
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

        // If stream ended without done=true, mark as done
        setState((prev) => ({ ...prev, isStreaming: false }));
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: (err as Error).message,
        }));
      }
    },
    [options.runtimeUrl, options.sessionId, options.accessToken],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, isStreaming: false }));
  }, []);

  return { ...state, sendMessage, abort };
}
