// SensitiveActionConfirm — modal dialog for confirming sensitive skill actions
// Shown when a skill returns HTTP 403 with a confirmation token.

import React, { useState } from 'react';
import './SensitiveActionConfirm.css';

interface PendingConfirmation {
  token: string;
  skill: string;
  action: string;
}

interface SensitiveActionConfirmProps {
  pending: PendingConfirmation | null;
  onConfirm: (token: string) => Promise<void>;
  onCancel: () => void;
}

export const SensitiveActionConfirm: React.FC<SensitiveActionConfirmProps> = ({
  pending,
  onConfirm,
  onCancel,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!pending) return null;

  const handleConfirm = async () => {
    setLoading(true);
    setError(null);
    try {
      await onConfirm(pending.token);
    } catch (err) {
      setError((err as Error).message);
      setLoading(false);
    }
  };

  const actionIcon: Record<string, string> = {
    email_send: '📧',
    email_draft: '📧',
    browser_fill_form: '🌐',
    bank_connect: '🏦',
    schedule_job: '⏰',
  };

  return (
    <div className="sac__overlay" role="dialog" aria-modal="true" aria-labelledby="sac-title">
      <div className="sac__dialog">
        <div className="sac__header">
          <span className="sac__icon" aria-hidden="true">
            {actionIcon[pending.skill] ?? '⚠️'}
          </span>
          <h2 id="sac-title" className="sac__title">Confirm Action</h2>
        </div>

        <p className="sac__description">
          The following action requires your explicit confirmation before it can proceed:
        </p>

        <div className="sac__action-box">
          <p className="sac__action-text">{pending.action}</p>
          <p className="sac__skill-tag">Skill: {pending.skill}</p>
        </div>

        <p className="sac__warning">
          This action is irreversible. Please make sure you want to proceed.
        </p>

        {error && (
          <div className="sac__error" role="alert">
            {error}
          </div>
        )}

        <div className="sac__actions">
          <button
            type="button"
            className="sac__btn sac__btn--cancel"
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="sac__btn sac__btn--confirm"
            onClick={handleConfirm}
            disabled={loading}
          >
            {loading ? 'Confirming…' : '⚡ Confirm & Execute'}
          </button>
        </div>
      </div>
    </div>
  );
};

// Hook to manage the confirmation flow
const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

export interface UseSensitiveConfirmOptions {
  accessToken?: string | null;
}

export interface UseSensitiveConfirmReturn {
  pendingConfirmation: PendingConfirmation | null;
  triggerConfirmation: (token: string, skill: string, action: string) => void;
  clearConfirmation: () => void;
  confirm: (token: string) => Promise<void>;
}

export function useSensitiveConfirm(
  options: UseSensitiveConfirmOptions = {}
): UseSensitiveConfirmReturn {
  const [pending, setPending] = useState<PendingConfirmation | null>(null);

  const triggerConfirmation = (
    token: string,
    skill: string,
    action: string
  ) => {
    setPending({ token, skill, action });
  };

  const clearConfirmation = () => {
    setPending(null);
  };

  const confirm = async (token: string) => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (options.accessToken) {
      headers.Authorization = `Bearer ${options.accessToken}`;
    }

    const res = await fetch(`${API_BASE}/skills/confirm`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ token }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail ?? `HTTP ${res.status}`);
    }

    setPending(null);
  };

  return {
    pendingConfirmation: pending,
    triggerConfirmation,
    clearConfirmation,
    confirm,
  };
}
