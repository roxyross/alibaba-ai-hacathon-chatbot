import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth';

export interface ModelInfo {
  name: string;
  display_name: string;
  enabled: boolean;
  task_types: string[];
  max_tokens: number;
}

export interface ProviderModels {
  name: string;
  display_name: string;
  enabled: boolean;
  models: ModelInfo[];
}

export function useModels() {
  const { authedFetch } = useAuth();
  const [providers, setProviders] = useState<ProviderModels[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await authedFetch<{ providers: ProviderModels[] }>(
        '/models',
      );
      setProviders(data.providers);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [authedFetch]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { providers, loading, error, reload };
}
