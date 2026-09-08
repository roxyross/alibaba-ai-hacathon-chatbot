// EmailSendPanel — compose and send emails via the email_send skill

import React, { useState } from 'react';
import './EmailSendPanel.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

interface EmailSendPanelProps {
  accessToken?: string | null;
  onBack?: () => void;
  onConfirmRequired?: (token: string, skill: string, action: string) => void;
}

interface EmailSendResponse {
  success: boolean;
  delivery_status: string;
  message_id?: string;
  sent_at?: string;
  error?: string;
}

async function sendEmail(
  payload: {
    to: string;
    subject: string;
    body: string;
    cc: string[];
    bcc: string[];
    confirm: boolean;
  },
  accessToken: string | null
): Promise<EmailSendResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(`${API_BASE}/skills/email_send`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (res.status === 403) {
    const data = await res.json();
    throw Object.assign(new Error('CONFIRMATION_REQUIRED'), { data });
  }

  const result = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) {
    throw new Error(result.error || result.detail || `HTTP ${res.status}`);
  }
  return result as EmailSendResponse;
}

export const EmailSendPanel: React.FC<EmailSendPanelProps> = ({
  accessToken,
  onBack,
  onConfirmRequired,
}) => {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState<{ messageId: string; sentAt: string; to: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTo('');
    setSubject('');
    setBody('');
    setCc('');
    setBcc('');
    setError(null);
    setSent(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!to.trim() || !subject.trim() || !body.trim()) return;

    setSubmitting(true);
    setError(null);
    setSent(null);

    try {
      const payload: Parameters<typeof sendEmail>[0] = {
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
        cc: cc.split(',').map((s) => s.trim()).filter(Boolean),
        bcc: bcc.split(',').map((s) => s.trim()).filter(Boolean),
        confirm: true,
      };

      const result = await sendEmail(payload, accessToken ?? null);

      if (result.success) {
        setSent({
          messageId: result.message_id ?? '',
          sentAt: result.sent_at ?? new Date().toISOString(),
          to: to.trim(),
        });
      } else if (result.error) {
        setError(result.error);
      }
    } catch (err: unknown) {
      const error = err as { data?: { detail?: string }; message?: string };
      if (error.message === 'CONFIRMATION_REQUIRED' && error.data && onConfirmRequired) {
        const detail = error.data.detail ?? {};
        onConfirmRequired(
          typeof detail === 'object' && detail !== null && 'token' in detail ? (detail as { token: string }).token : '',
          'email_send',
          `Send email to "${to.trim()}": "${subject.trim()}"`
        );
        setError('Confirmation required — please confirm in the dialog.');
      } else {
        const msg = (err as Error).message ?? 'Failed to send email';
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="esp">
      <div className="esp__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {onBack && (
            <button type="button" className="view-back-btn" onClick={onBack} title="Back to Chat">
              ← Back to Chat
            </button>
          )}
          <h2 className="esp__title">📧 <span>Send Email</span></h2>
        </div>
      </div>

      <div className="esp__body">
        {sent ? (
          <div className="esp__success">
            <span className="esp__success-icon">✅</span>
            <p className="esp__success-title">Email Dispatched Successfully!</p>
            <p className="esp__success-meta">
              Delivered to: <strong>{sent.to}</strong>
            </p>
            <p className="esp__success-meta" style={{ fontSize: '0.85rem', opacity: 0.8 }}>
              Ref ID: {sent.messageId} · Sent at: {new Date(sent.sentAt).toLocaleTimeString()}
            </p>
            <button className="esp__new-btn" onClick={reset}>
              Send Another Email
            </button>
          </div>
        ) : (
          <form className="esp__form" onSubmit={handleSubmit}>
            <label className="esp__field">
              To *
              <input
                type="email"
                className="esp__input"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="recipient@example.com"
                required
              />
            </label>

            <label className="esp__field">
              Subject *
              <input
                type="text"
                className="esp__input"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Email subject"
                required
                maxLength={200}
              />
            </label>

            <label className="esp__field">
              Body *
              <textarea
                className="esp__textarea"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Write your message here…"
                required
                rows={8}
              />
            </label>

            <label className="esp__field">
              CC (comma-separated)
              <input
                type="text"
                className="esp__input"
                value={cc}
                onChange={(e) => setCc(e.target.value)}
                placeholder="cc@example.com, cc2@example.com"
              />
            </label>

            <label className="esp__field">
              BCC (comma-separated)
              <input
                type="text"
                className="esp__input"
                value={bcc}
                onChange={(e) => setBcc(e.target.value)}
                placeholder="bcc@example.com"
              />
            </label>

            {error && (
              <div className="esp__error" role="alert">
                {error}
              </div>
            )}

            <div className="esp__actions">
              <button
                type="submit"
                className="esp__send-btn"
                disabled={submitting || !to.trim() || !subject.trim() || !body.trim()}
              >
                {submitting ? 'Dispatching…' : '📤 Send Email'}
              </button>
              <button
                type="button"
                className="esp__cancel-btn"
                onClick={reset}
              >
                Clear
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
