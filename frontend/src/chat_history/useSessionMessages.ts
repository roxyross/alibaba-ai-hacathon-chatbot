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

  const deleteMessage = useCallback(
    async (messageId: string) => {
      // Optimistic removal from local state
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
      if (!sessionId) return;
      try {
        await authedFetch<void>(`/sessions/${sessionId}/messages/${messageId}`, {
          method: 'DELETE',
        });
      } catch (err) {
        console.error('Failed to delete message on backend:', err);
        // Rollback on failure
        void reload();
        throw err;
      }
    },
    [authedFetch, sessionId, reload],
  );

  return { messages, loading, error, reload, setMessages, deleteMessage };
}
