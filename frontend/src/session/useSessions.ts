import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth';

export interface ChatSession {
  id: string;
  title: string | null;
  provider: string;
  model: string;
  session_type?: 'chat' | 'task' | 'cowork';
  pinned?: boolean;
  archived_at?: string | null;
  project_id?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface CreateSessionInput {
  provider: string;
  model: string;
  title?: string;
  session_type?: 'chat' | 'task' | 'cowork';
  pinned?: boolean;
  project_id?: string | null;
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

  const refresh = useCallback(async (sessionType?: 'chat' | 'task', includeArchived = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (sessionType) params.append('session_type', sessionType);
      if (includeArchived) params.append('include_archived', 'true');
      const query = params.toString();
      const url = query ? `/sessions?${query}` : '/sessions';
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

  const togglePin = useCallback(
    async (id: string, pinned: boolean): Promise<ChatSession> => {
      // Optimistically update this view, but only notify other views after persistence succeeds.
      setSessions((prev) =>
        prev
          .map((s) => (s.id === id ? { ...s, pinned } : s))
          .sort((a, b) => (Number(b.pinned || false) - Number(a.pinned || false))),
      );
      try {
        const updated = await authedFetch<ChatSession>(`/sessions/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ pinned }),
        });
        setSessions((prev) =>
          prev.map((s) => (s.id === id ? { ...s, ...updated } : s)),
        );
        notifySessionsChanged();
        return updated;
      } catch (err) {
        // Reconcile optimistic state with the server after a failed write.
        await refresh();
        notifySessionsChanged();
        throw err;
      }
    },
    [authedFetch, refresh],
  );

  const toggleArchive = useCallback(
    async (id: string, archived: boolean): Promise<ChatSession> => {
      // Optimistically remove archived sessions from the active list.
      if (archived) {
        setSessions((prev) => prev.filter((s) => s.id !== id));
      }
      try {
        const updated = await authedFetch<ChatSession>(`/sessions/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ archived }),
        });
        // Refresh the active list so both archive and restore use server truth.
        await refresh();
        notifySessionsChanged();
        return updated;
      } catch (err) {
        // Restore the server-backed list if the archive operation failed.
        await refresh();
        notifySessionsChanged();
        throw err;
      }
    },
    [authedFetch, refresh],
  );

  const remove = useCallback(
    async (id: string): Promise<void> => {
      // Optimistic update: remove immediately so UI updates in 0ms.
      setSessions((prev) => prev.filter((s) => s.id !== id));
      try {
        await authedFetch<void>(`/sessions/${id}`, { method: 'DELETE' });
        notifySessionsChanged();
      } catch (err) {
        console.error('Failed to delete session on server:', err);
        // Reconcile the optimistic removal and notify other views after refresh.
        await refresh();
        notifySessionsChanged();
        throw err;
      }
    },
    [authedFetch, refresh],
  );

  const moveToProject = useCallback(
    async (id: string, projectId: string | null): Promise<ChatSession> => {
      // Optimistic state update
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, project_id: projectId } : s)),
      );
      try {
        const updated = await authedFetch<ChatSession>(`/sessions/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ project_id: projectId || '' }),
        });
        setSessions((prev) =>
          prev.map((s) => (s.id === id ? { ...s, ...updated } : s)),
        );
        notifySessionsChanged();
        return updated;
      } catch (err) {
        // Reconcile on failure
        await refresh();
        notifySessionsChanged();
        throw err;
      }
    },
    [authedFetch, refresh],
  );

  return { sessions, loading, error, refresh, create, rename, togglePin, toggleArchive, remove, moveToProject };
}
