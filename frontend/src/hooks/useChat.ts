// useChat — SSE streaming hook with session + auth support.
// Parses SSE comment lines for attribution, accumulates deltas, and
// surfaces a typed `Attribution` for the UI.

import { useCallback, useRef, useState } from 'react';

/** Attribution metadata for the last completed turn (provider + model). */
export interface Attribution {
  provider: string;
  model: string;
}

export interface UseChatOptions {
  apiBase?: string;
  provider?: string;
  model?: string;
  sessionId?: string | null;
  accessToken?: string | null;
}

export interface ChatState {
  messages: { role: 'user' | 'assistant'; content: string }[];
  attribution: Attribution | null;
  isStreaming: boolean;
  error: string | null;
}

const STREAM_PATH = '/ai/chat/stream';

export function useChat(options: UseChatOptions = {}) {
  const [state, setState] = useState<ChatState>({
    messages: [],
    attribution: null,
    isStreaming: false,
    error: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      setState((prev) => ({
        ...prev,
        messages: [...prev.messages, { role: 'user', content }],
        attribution: null,
        isStreaming: true,
        error: null,
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

        const response = await fetch(
          `${options.apiBase ?? '/api/v1'}${STREAM_PATH}`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify({
              messages: [{ role: 'user', content }],
              stream: true,
              ...(options.provider ? { provider: options.provider } : {}),
              ...(options.model ? { model: options.model } : {}),
              ...(options.sessionId ? { session_id: options.sessionId } : {}),
            }),
            signal: abortRef.current.signal,
          },
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        let attribution: Attribution | null = null;
        let assistantContent = '';
        let done = false;

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();

        while (!done) {
          const { value, done: doneReading } = await reader.read();
          done = doneReading;
          if (!value) continue;

          const chunk = decoder.decode(value, { stream: !done });

          for (const line of chunk.split('\n')) {
            if (line.startsWith(': ')) {
              const meta = line.slice(2);
              const match = meta.match(/provider=(\S+) model=(\S+)/);
              if (match) {
                attribution = { provider: match[1], model: match[2] };
              }
            } else if (line.startsWith('data: ')) {
              const data = line.slice(6).trim();
              if (data === '[DONE]') {
                done = true;
              } else {
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.error) {
                    setState((prev) => ({
                      ...prev,
                      isStreaming: false,
                      error: parsed.detail || parsed.error,
                    }));
                    done = true;
                    return;
                  }
                  if (parsed.delta) {
                    assistantContent += parsed.delta;
                    setState((prev) => {
                      const msgs = [...prev.messages];
                      const last = msgs[msgs.length - 1];
                      if (last?.role === 'assistant') {
                        msgs[msgs.length - 1] = {
                          ...last,
                          content: assistantContent,
                        };
                      } else {
                        msgs.push({ role: 'assistant', content: assistantContent });
                      }
                      return { ...prev, messages: msgs };
                    });
                  }
                  if (parsed.done) {
                    done = true;
                  }
                } catch {
                  /* ignore parse errors for incomplete JSON */
                }
              }
            }
          }
        }

        setState((prev) => ({
          ...prev,
          attribution,
          isStreaming: false,
        }));
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: (err as Error).message,
        }));
      }
    },
    [
      options.apiBase,
      options.provider,
      options.model,
      options.sessionId,
      options.accessToken,
    ],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, isStreaming: false }));
  }, []);

  return { ...state, sendMessage, abort, setMessages: setState };
}
