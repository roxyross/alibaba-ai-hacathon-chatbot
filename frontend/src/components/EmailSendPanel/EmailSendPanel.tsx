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
    smtp_host?: string;
    smtp_port?: number;
    smtp_user?: string;
    smtp_pass?: string;
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

  // SMTP Settings State
  const [showSmtp, setShowSmtp] = useState(false);
  const [smtpUser, setSmtpUser] = useState(() => localStorage.getItem('roxy_smtp_user') || '');
  const [smtpPass, setSmtpPass] = useState(() => localStorage.getItem('roxy_smtp_pass') || '');
  const [smtpHost, setSmtpHost] = useState(() => localStorage.getItem('roxy_smtp_host') || 'smtp.gmail.com');
  const [smtpPort, setSmtpPort] = useState(() => localStorage.getItem('roxy_smtp_port') || '587');
  const [showPass, setShowPass] = useState(false);

  const reset = () => {
    setTo('');
    setSubject('');
    setBody('');
    setCc('');
    setBcc('');
    setError(null);
    setSent(null);
  };

  const saveSmtpSettings = (user: string, pass: string, host: string, port: string) => {
    localStorage.setItem('roxy_smtp_user', user);
    localStorage.setItem('roxy_smtp_pass', pass);
    localStorage.setItem('roxy_smtp_host', host);
    localStorage.setItem('roxy_smtp_port', port);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!to.trim() || !subject.trim() || !body.trim()) return;

    setSubmitting(true);
    setError(null);
    setSent(null);

    // Persist SMTP settings if entered
    if (smtpUser || smtpPass) {
      saveSmtpSettings(smtpUser, smtpPass, smtpHost, smtpPort);
    }

    try {
      const payload: Parameters<typeof sendEmail>[0] = {
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
        cc: cc.split(',').map((s) => s.trim()).filter(Boolean),
        bcc: bcc.split(',').map((s) => s.trim()).filter(Boolean),
        confirm: true,
      };

      if (smtpUser.trim() && smtpPass.trim()) {
        payload.smtp_user = smtpUser.trim();
        payload.smtp_pass = smtpPass.trim();
        payload.smtp_host = smtpHost.trim() || 'smtp.gmail.com';
        payload.smtp_port = Number(smtpPort) || 587;
      }

      const result = await sendEmail(payload, accessToken ?? null);

      if (result.success) {
        setSent({
          messageId: result.message_id ?? '',
          sentAt: result.sent_at ?? new Date().toISOString(),
          to: to.trim(),
        });
      } else if (result.error) {
        setError(result.error);
        if (result.error.toLowerCase().includes('smtp')) {
          setShowSmtp(true);
        }
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
        if (msg.toLowerCase().includes('smtp') || msg.toLowerCase().includes('password')) {
          setShowSmtp(true);
        }
      }
    } finally {
      setSubmitting(false);
    }
  };

  const hasConfiguredSmtp = Boolean(smtpUser.trim() && smtpPass.trim());

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
            {/* SMTP Settings Accordion */}
            <div className="esp__smtp-box">
              <button
                type="button"
                className="esp__smtp-toggle"
                onClick={() => setShowSmtp((prev) => !prev)}
                aria-expanded={showSmtp}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <span>⚙️</span>
                  <span style={{ fontWeight: 600 }}>SMTP / Mail Dispatch Configuration</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`esp__smtp-badge ${hasConfiguredSmtp ? 'esp__smtp-badge--active' : ''}`}>
                    {hasConfiguredSmtp ? '● Configured' : 'Optional / Setup'}
                  </span>
                  <span>{showSmtp ? '▲' : '▼'}</span>
                </div>
              </button>

              {showSmtp && (
                <div className="esp__smtp-content">
                  <p className="esp__smtp-guide">
                    💡 <strong>To ensure emails reach real inboxes:</strong> Enter your Gmail address and 16-character
                    <strong> Google App Password</strong> (from Google Account &gt; Security &gt; 2-Step Verification &gt; App passwords).
                    Credentials are saved safely in your browser.
                  </p>

                  <div className="esp__smtp-grid">
                    <label className="esp__field">
                      Email / SMTP Username
                      <input
                        type="email"
                        className="esp__input"
                        value={smtpUser}
                        onChange={(e) => setSmtpUser(e.target.value)}
                        placeholder="yourname@gmail.com"
                      />
                    </label>

                    <label className="esp__field">
                      SMTP App Password
                      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                        <input
                          type={showPass ? 'text' : 'password'}
                          className="esp__input"
                          value={smtpPass}
                          onChange={(e) => setSmtpPass(e.target.value)}
                          placeholder="16-character app password"
                          style={{ paddingRight: '2.5rem' }}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPass((p) => !p)}
                          style={{
                            position: 'absolute',
                            right: '0.5rem',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            fontSize: '0.85rem',
                          }}
                          title={showPass ? 'Hide password' : 'Show password'}
                        >
                          {showPass ? '🙈' : '👁️'}
                        </button>
                      </div>
                    </label>

                    <label className="esp__field">
                      SMTP Server Host
                      <input
                        type="text"
                        className="esp__input"
                        value={smtpHost}
                        onChange={(e) => setSmtpHost(e.target.value)}
                        placeholder="smtp.gmail.com"
                      />
                    </label>

                    <label className="esp__field">
                      SMTP Port
                      <input
                        type="text"
                        className="esp__input"
                        value={smtpPort}
                        onChange={(e) => setSmtpPort(e.target.value)}
                        placeholder="587 (or 465)"
                      />
                    </label>
                  </div>
                </div>
              )}
            </div>

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
                <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>⚠️ Delivery Note:</div>
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
