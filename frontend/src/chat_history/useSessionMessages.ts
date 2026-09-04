import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth';

export interface ChatMessageRecord {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  provider: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  created_at: string;
}

export function useSessionMessages(sessionId: string | null) {
  const { authedFetch } = useAuth();
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await authedFetch<{ messages: ChatMessageRecord[] }>(
        `/sessions/${sessionId}/messages`,
      );
      setMessages(data.messages);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [authedFetch, sessionId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { messages, loading, error, reload, setMessages };
}
