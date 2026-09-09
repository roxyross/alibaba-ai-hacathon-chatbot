import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth';

export interface ChatSession {
  id: string;
  title: string | null;
  provider: string;
  model: string;
  session_type?: 'chat' | 'task';
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface CreateSessionInput {
  provider: string;
  model: string;
  title?: string;
  session_type?: 'chat' | 'task';
}

export const SESSIONS_CHANGED_EVENT = 'roxy:sessions_changed';

export function notifySessionsChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SESSIONS_CHANGED_EVENT));
  }
}

export function useSessions() {
  const { authedFetch } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (sessionType?: 'chat' | 'task') => {
    setLoading(true);
    setError(null);
    try {
      const url = sessionType ? `/sessions?session_type=${sessionType}` : '/sessions';
      const data = await authedFetch<ChatSession[]>(url);
      setSessions(data || []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [authedFetch]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Listen to cross-component session mutations so all sidebar/app instances stay in sync
  useEffect(() => {
    const handler = () => {
      void refresh();
    };
    window.addEventListener(SESSIONS_CHANGED_EVENT, handler);
    return () => window.removeEventListener(SESSIONS_CHANGED_EVENT, handler);
  }, [refresh]);

  const create = useCallback(
    async (input: CreateSessionInput): Promise<ChatSession> => {
      const created = await authedFetch<ChatSession>('/sessions', {
        method: 'POST',
        body: JSON.stringify(input),
      });
      // Optimistic instant update
      setSessions((prev) => [created, ...prev.filter((s) => s.id !== created.id)]);
      notifySessionsChanged();
      return created;
    },
    [authedFetch],
  );

  const rename = useCallback(
    async (id: string, title: string): Promise<ChatSession> => {
      const updated = await authedFetch<ChatSession>(`/sessions/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      });
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, ...updated } : s)),
      );
      notifySessionsChanged();
      return updated;
    },
    [authedFetch],
  );

  const remove = useCallback(
    async (id: string): Promise<void> => {
      // Optimistic update: remove immediately so UI updates in 0ms
      setSessions((prev) => prev.filter((s) => s.id !== id));
      notifySessionsChanged();
      try {
        await authedFetch<void>(`/sessions/${id}`, { method: 'DELETE' });
      } catch (err) {
        console.error('Failed to delete session on server:', err);
        // Rollback/refresh on error
        void refresh();
        throw err;
      }
    },
    [authedFetch, refresh],
  );

  return { sessions, loading, error, refresh, create, rename, remove };
}
