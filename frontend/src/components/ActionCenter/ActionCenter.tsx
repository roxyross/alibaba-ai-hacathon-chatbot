import React, { useState, useEffect, useCallback } from 'react';
import './ActionCenter.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface ActionItem {
  id: string;
  user_id: string;
  task_id: string | null;
  step_id: string | null;
  tool_id: string;
  description: string;
  input_parameters: Record<string, unknown>;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  required_permission: string;
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'failed' | 'cancelled';
  result?: unknown;
  error?: string | null;
  created_at: string | null;
  resolved_at?: string | null;
}

interface ActionCenterProps {
  accessToken?: string | null;
  onActionResolved?: (action: ActionItem) => void;
}

export const ActionCenter: React.FC<ActionCenterProps> = ({
  accessToken,
  onActionResolved,
}) => {
  const [pendingActions, setPendingActions] = useState<ActionItem[]>([]);
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [editJson, setEditJson] = useState<string>('');
  const [editError, setEditError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const fetchPending = useCallback(async () => {
    if (!accessToken) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/actions/pending`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      if (res.ok) {
        const data: ActionItem[] = await res.json();
        setPendingActions(data);
      }
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchPending();
    const interval = setInterval(fetchPending, 4000);
    return () => clearInterval(interval);
  }, [fetchPending]);

  const handleApprove = async (actionId: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/actions/${actionId}/approve`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      if (res.ok) {
        const updated: ActionItem = await res.json();
        setPendingActions((prev) => prev.filter((a) => a.id !== actionId));
        onActionResolved?.(updated);
      }
    } catch {
      // Handle error
    }
  };

  const handleReject = async (actionId: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/actions/${actionId}/reject`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ reason: 'Rejected by user in Action Center' }),
      });
      if (res.ok) {
        const updated: ActionItem = await res.json();
        setPendingActions((prev) => prev.filter((a) => a.id !== actionId));
        onActionResolved?.(updated);
      }
    } catch {
      // Handle error
    }
  };

  const startEdit = (action: ActionItem) => {
    setEditingActionId(action.id);
    setEditJson(JSON.stringify(action.input_parameters, null, 2));
    setEditError(null);
  };

  const saveEdit = async (actionId: string) => {
    if (!accessToken) return;
    try {
      const parsed = JSON.parse(editJson);
      const res = await fetch(`${API_BASE}/actions/${actionId}/edit`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ input_parameters: parsed }),
      });
      if (res.ok) {
        const updated: ActionItem = await res.json();
        setPendingActions((prev) =>
          prev.map((a) => (a.id === actionId ? updated : a))
        );
        setEditingActionId(null);
      } else {
        const err = await res.json();
        setEditError(err.detail || 'Failed to update action');
      }
    } catch (e) {
      setEditError(`Invalid JSON: ${(e as Error).message}`);
    }
  };

  return (
    <div className="action-center" role="region" aria-label="Action Center">
      <div className="action-center__header">
        <div className="action-center__title-area">
          <span className="action-center__icon">🛡️</span>
          <h3 className="action-center__title">Action &amp; Approval Center</h3>
          {pendingActions.length > 0 && (
            <span className="action-center__badge">
              {pendingActions.length} Pending
            </span>
          )}
        </div>
        <button
          type="button"
          className="action-center__refresh-btn"
          onClick={fetchPending}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {pendingActions.length === 0 ? (
        <div className="action-center__empty">
          <span>✓ No pending actions requiring confirmation.</span>
        </div>
      ) : (
        pendingActions.map((action) => (
          <div
            key={action.id}
            className={`action-card action-card--${action.risk_level}`}
          >
            <div className="action-card__top">
              <span className="action-card__tool-name">
                ⚡ {action.tool_id}
              </span>
              <span
                className={`action-card__risk-tag risk-tag--${action.risk_level}`}
              >
                {action.risk_level} Risk
              </span>
            </div>

            <p className="action-card__description">{action.description}</p>

            {editingActionId === action.id ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <textarea
                  className="action-card__params-preview"
                  style={{ minHeight: '100px', width: '100%', resize: 'vertical' }}
                  value={editJson}
                  onChange={(e) => setEditJson(e.target.value)}
                />
                {editError && (
                  <span style={{ color: '#ef4444', fontSize: '0.78rem' }}>
                    {editError}
                  </span>
                )}
                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    className="action-btn action-btn--edit"
                    onClick={() => setEditingActionId(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="action-btn action-btn--approve"
                    onClick={() => saveEdit(action.id)}
                  >
                    Save Changes
                  </button>
                </div>
              </div>
            ) : (
              <div className="action-card__params-preview">
                <pre style={{ margin: 0 }}>
                  {JSON.stringify(action.input_parameters, null, 2)}
                </pre>
              </div>
            )}

            <div className="action-card__buttons">
              <button
                type="button"
                className="action-btn action-btn--edit"
                onClick={() => startEdit(action)}
              >
                Edit Payload
              </button>
              <button
                type="button"
                className="action-btn action-btn--reject"
                onClick={() => handleReject(action.id)}
              >
                Reject
              </button>
              <button
                type="button"
                className="action-btn action-btn--approve"
                onClick={() => handleApprove(action.id)}
              >
                Approve &amp; Run
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
};
