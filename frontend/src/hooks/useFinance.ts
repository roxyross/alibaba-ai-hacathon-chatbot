// useFinance — Finance Dashboard data hook
// Calls GET /api/v1/finance/summary and related endpoints

import { useCallback, useEffect, useState } from 'react';

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

export interface AccountSummary {
  connection_id: string;
  institution: string | null;
  account_id: string;
  name: string;
  type: string;
  mask: string | null;
  balance: number | null;
}

export interface Budget {
  id: string;
  category: string;
  monthly_limit: number;
  alert_threshold: number;
  current_spent: number;
  pct_used: number;
  created_at: string;
}

export interface SpendingAlert {
  id: string;
  name: string;
  alert_type: 'over_budget' | 'unusual_charge' | 'bill_reminder';
  threshold_amount: number | null;
  category: string | null;
  institution: string | null;
  enabled: boolean;
  last_triggered_at: string | null;
  created_at: string;
}

export interface Transaction {
  account_id: string;
  date: string;
  description: string;
  amount: number;
  category: string;
  pending: boolean;
}

export interface FinanceSummary {
  accounts: AccountSummary[];
  total_balance: number;
  budgets: Budget[];
  alerts: SpendingAlert[];
  month_spending: number;
}

export interface TransactionList {
  transactions: Transaction[];
  total: number;
}

export interface UseFinanceOptions {
  accessToken?: string | null;
}

async function fetchJSON<T>(
  url: string,
  accessToken: string | null | undefined,
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(`${API_BASE}${url}`, { headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function useFinance(options: UseFinanceOptions = {}) {
  const { accessToken } = options;

  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [transactions, setTransactions] = useState<TransactionList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJSON<FinanceSummary>('/finance/summary', accessToken);
      setSummary(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  const fetchTransactions = useCallback(
    async (startDate?: string, endDate?: string) => {
      const params = new URLSearchParams();
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
      const qs = params.toString();
      try {
        const data = await fetchJSON<TransactionList>(
          `/finance/transactions${qs ? `?${qs}` : ''}`,
          accessToken,
        );
        setTransactions(data);
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [accessToken],
  );

  // Create budget
  const createBudget = useCallback(
    async (category: string, monthlyLimit: number, alertThreshold = 0.8) => {
      const res = await fetch(`${API_BASE}/finance/budgets`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({
          category,
          monthly_limit: monthlyLimit,
          alert_threshold: alertThreshold,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      await fetchSummary();
    },
    [accessToken, fetchSummary],
  );

  // Delete budget
  const deleteBudget = useCallback(
    async (budgetId: string) => {
      const res = await fetch(`${API_BASE}/finance/budgets/${budgetId}`, {
        method: 'DELETE',
        headers: accessToken
          ? { Authorization: `Bearer ${accessToken}` }
          : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchSummary();
    },
    [accessToken, fetchSummary],
  );

  // Create alert
  const createAlert = useCallback(
    async (alert: Omit<SpendingAlert, 'id' | 'last_triggered_at' | 'created_at'>) => {
      const res = await fetch(`${API_BASE}/finance/alerts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify(alert),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      await fetchSummary();
    },
    [accessToken, fetchSummary],
  );

  // Delete alert
  const deleteAlert = useCallback(
    async (alertId: string) => {
      const res = await fetch(`${API_BASE}/finance/alerts/${alertId}`, {
        method: 'DELETE',
        headers: accessToken
          ? { Authorization: `Bearer ${accessToken}` }
          : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchSummary();
    },
    [accessToken, fetchSummary],
  );

  // Initial load — fetch summary and transactions in parallel
  useEffect(() => {
    void fetchSummary();
    void fetchTransactions();
  }, [fetchSummary, fetchTransactions]);

  return {
    summary,
    transactions,
    loading,
    error,
    fetchSummary,
    fetchTransactions,
    createBudget,
    deleteBudget,
    createAlert,
    deleteAlert,
  };
}
