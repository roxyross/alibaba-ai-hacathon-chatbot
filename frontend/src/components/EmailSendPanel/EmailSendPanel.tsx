// EmailSendPanel — Comprehensive Email & Communications Hub (Phase 12)
// Features: Compose, Outbox, Drafts, AI Smart Composer, Tone Polisher, Template Library

import React, { useCallback, useEffect, useState } from 'react';
import { VoiceInputControl, speakVoiceText } from '../common/VoiceInputControl';
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

interface EmailItem {
  id: string;
  user_id: string;
  to: string;
  subject: string;
  body: string;
  cc?: string[];
  bcc?: string[];
  status: 'draft' | 'sent' | 'failed' | 'queued';
  delivery_error?: string | null;
  message_id?: string | null;
  sent_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface EmailTemplate {
  id: string;
  title: string;
  category: string;
  subject: string;
  body: string;
}

export const EmailSendPanel: React.FC<EmailSendPanelProps> = ({
  accessToken,
  onBack,
  onConfirmRequired,
}) => {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<'compose' | 'drafts' | 'outbox' | 'templates'>('compose');

  // Composer fields
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [showCcBcc, setShowCcBcc] = useState(false);

  // AI Assistant state
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiTone, setAiTone] = useState<string>('professional');
  const [isAiLoading, setIsAiLoading] = useState(false);

  // Submission & status
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState<{ messageId: string; sentAt: string; to: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  // Lists state
  const [drafts, setDrafts] = useState<EmailItem[]>([]);
  const [sentEmails, setSentEmails] = useState<EmailItem[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  // Optional SMTP Credentials configuration (for users without Google OAuth)
  const [showSettings, setShowSettings] = useState(false);
  const [senderEmail, setSenderEmail] = useState(() => localStorage.getItem('roxy_smtp_user') || 'rijjienterprise@gmail.com');
  const [appPassword, setAppPassword] = useState(() => localStorage.getItem('roxy_smtp_pass') || '');
  const [savedSettings, setSavedSettings] = useState(false);

  // Fetch emails list (drafts or sent)
  const loadEmails = useCallback(async () => {
    if (!accessToken) return;
    setLoadingList(true);
    try {
      const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
      const [draftRes, sentRes] = await Promise.all([
        fetch(`${API_BASE}/emails?status=draft`, { headers }),
        fetch(`${API_BASE}/emails?status=sent`, { headers }),
      ]);
      if (draftRes.ok) {
        const d = await draftRes.json();
        setDrafts(d.emails || []);
      }
      if (sentRes.ok) {
        const s = await sentRes.json();
        setSentEmails(s.emails || []);
      }
    } catch {
      // ignore network error
    } finally {
      setLoadingList(false);
    }
  }, [accessToken]);

  // Fetch template library
  const loadTemplates = useCallback(async () => {
    if (!accessToken) return;
    try {
      const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
      const res = await fetch(`${API_BASE}/emails/templates`, { headers });
      if (res.ok) {
        const data = await res.json();
        setTemplates(data.templates || []);
      }
    } catch {
      // ignore template fetch error
    }
  }, [accessToken]);

  useEffect(() => {
    void loadEmails();
    void loadTemplates();
  }, [loadEmails, loadTemplates]);

  const resetComposer = () => {
    setEditingDraftId(null);
    setTo('');
    setSubject('');
    setBody('');
    setCc('');
    setBcc('');
    setError(null);
    setSent(null);
    setInfoMessage(null);
    setAiPrompt('');
  };

  // ── AI Compose Draft ──────────────────────────────────────────────────────
  const handleAiCompose = async () => {
    if (!aiPrompt.trim()) return;
    setIsAiLoading(true);
    setError(null);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(`${API_BASE}/emails/compose-ai`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          prompt: aiPrompt.trim(),
          tone: aiTone,
        }),
      });
      if (!res.ok) throw new Error('AI compose failed.');
      const data = await res.json();
      setSubject(data.subject || subject);
      setBody(data.body || body);
      setInfoMessage(`✓ Draft generated in ${aiTone} tone.`);
      void speakVoiceText(`Draft generated in ${aiTone} tone.`);
    } catch (err) {
      setError((err as Error).message || 'Failed to compose draft with AI.');
    } finally {
      setIsAiLoading(false);
    }
  };

  // ── AI Polish Draft ───────────────────────────────────────────────────────
  const handleAiPolish = async () => {
    if (!body.trim()) return;
    setIsAiLoading(true);
    setError(null);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(`${API_BASE}/emails/polish-ai`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          subject: subject.trim() || 'Follow-Up',
          body: body.trim(),
          tone: aiTone,
        }),
      });
      if (!res.ok) throw new Error('AI polish failed.');
      const data = await res.json();
      setSubject(data.subject);
      setBody(data.body);
      setInfoMessage(`✓ Email copy polished in ${aiTone} tone.`);
      void speakVoiceText('Email copy polished.');
    } catch (err) {
      setError((err as Error).message || 'Failed to polish email.');
    } finally {
      setIsAiLoading(false);
    }
  };

  // ── Save as Draft ─────────────────────────────────────────────────────────
  const handleSaveDraft = async () => {
    if (!subject.trim() && !body.trim() && !to.trim()) return;
    setSubmitting(true);
    setError(null);
    setInfoMessage(null);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const payload = {
        to: to.trim() || 'draft@unspecified',
        subject: subject.trim() || 'Untitled Draft',
        body: body.trim(),
        cc: cc ? cc.split(',').map((s) => s.trim()).filter(Boolean) : undefined,
        bcc: bcc ? bcc.split(',').map((s) => s.trim()).filter(Boolean) : undefined,
        status: 'draft',
      };

      if (editingDraftId) {
        // Update existing draft
        const res = await fetch(`${API_BASE}/emails/${editingDraftId}`, {
          method: 'PATCH',
          headers,
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('Failed to update draft');
        setInfoMessage('✓ Draft updated successfully.');
      } else {
        // Create new draft
        const res = await fetch(`${API_BASE}/emails`, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('Failed to save draft');
        const d = await res.json();
        setEditingDraftId(d.email.id);
        setInfoMessage('✓ Draft saved to outbox hub.');
      }
      void loadEmails();
    } catch (err) {
      setError((err as Error).message || 'Failed to save draft.');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Send Email ────────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!to.trim() || !subject.trim() || !body.trim()) return;

    setSubmitting(true);
    setError(null);
    setSent(null);
    setInfoMessage(null);

    try {
      const storedSmtpUser = localStorage.getItem('roxy_smtp_user');
      const storedSmtpPass = localStorage.getItem('roxy_smtp_pass');

      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      // If we have an existing draft id, send it via draft dispatch endpoint
      let result: any = null;

      if (editingDraftId) {
        // Update draft first
        await fetch(`${API_BASE}/emails/${editingDraftId}`, {
          method: 'PATCH',
          headers,
          body: JSON.stringify({
            to: to.trim(),
            subject: subject.trim(),
            body: body.trim(),
          }),
        });

        // Dispatch via /send
        const sendRes = await fetch(`${API_BASE}/emails/${editingDraftId}/send`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            smtp_user: senderEmail.trim() || storedSmtpUser || undefined,
            smtp_pass: appPassword.trim() || storedSmtpPass || undefined,
          }),
        });
        result = await sendRes.json();
      } else {
        // Direct skill dispatch & persistence
        const payload = {
          to: to.trim(),
          subject: subject.trim(),
          body: body.trim(),
          cc: cc ? cc.split(',').map((s) => s.trim()).filter(Boolean) : [],
          bcc: bcc ? bcc.split(',').map((s) => s.trim()).filter(Boolean) : [],
          confirm: true,
          smtp_user: senderEmail.trim() || storedSmtpUser || undefined,
          smtp_pass: appPassword.trim() || storedSmtpPass || undefined,
        };

        const res = await fetch(`${API_BASE}/skills/email_send`, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });

        if (res.status === 403) {
          const data = await res.json();
          throw Object.assign(new Error('CONFIRMATION_REQUIRED'), { data });
        }

        result = await res.json().catch(() => ({ detail: res.statusText }));
        if (!res.ok) {
          throw new Error(result.error || result.detail || `HTTP ${res.status}`);
        }

        // Persist sent email to repository
        if (result.success) {
          await fetch(`${API_BASE}/emails`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              to: to.trim(),
              subject: subject.trim(),
              body: body.trim(),
              status: 'sent',
            }),
          });
        }
      }

      if (result.success) {
        setSent({
          messageId: result.message_id || result.messageId || 'SENT-MSG',
          sentAt: result.sent_at || new Date().toISOString(),
          to: to.trim(),
        });
        void speakVoiceText(`Email dispatched successfully to ${to.trim()}`);
        void loadEmails();
      } else if (result.error) {
        setError(result.error);
        void speakVoiceText(`Email send failed: ${result.error}`);
      }
    } catch (err: unknown) {
      const errorObj = err as { data?: { detail?: string }; message?: string };
      if (errorObj.message === 'CONFIRMATION_REQUIRED' && errorObj.data && onConfirmRequired) {
        const detail = errorObj.data.detail ?? {};
        onConfirmRequired(
          typeof detail === 'object' && detail !== null && 'token' in detail ? (detail as { token: string }).token : '',
          'email_send',
          `Send email to "${to.trim()}": "${subject.trim()}"`
        );
        setError('Confirmation required — please confirm in the security gate.');
        void speakVoiceText('Confirmation required before sending this email.');
      } else {
        const msg = (err as Error).message ?? 'Failed to send email';
        setError(msg);
        void speakVoiceText(`Email failed: ${msg}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ── Open Draft in Composer ────────────────────────────────────────────────
  const handleOpenDraft = (draft: EmailItem) => {
    setEditingDraftId(draft.id);
    setTo(draft.to || '');
    setSubject(draft.subject || '');
    setBody(draft.body || '');
    setCc(draft.cc ? draft.cc.join(', ') : '');
    setBcc(draft.bcc ? draft.bcc.join(', ') : '');
    setActiveTab('compose');
    setSent(null);
    setError(null);
    setInfoMessage(`Opened draft: "${draft.subject || 'Untitled'}"`);
  };

  // ── Delete Draft/Message ──────────────────────────────────────────────────
  const handleDelete = async (id: string) => {
    if (!accessToken) return;
    try {
      const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
      await fetch(`${API_BASE}/emails/${id}`, { method: 'DELETE', headers });
      if (editingDraftId === id) resetComposer();
      void loadEmails();
    } catch {
      // ignore
    }
  };

  // ── Use Template ──────────────────────────────────────────────────────────
  const handleUseTemplate = (tpl: EmailTemplate) => {
    setSubject(tpl.subject);
    setBody(tpl.body);
    setEditingDraftId(null);
    setActiveTab('compose');
    setInfoMessage(`Applied template: "${tpl.title}"`);
  };

  return (
    <div className="esp">
      {/* Header */}
      <div className="esp__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {onBack && (
            <button type="button" className="view-back-btn" onClick={onBack} title="Back to Chat">
              ← Back to Chat
            </button>
          )}
          <h2 className="esp__title">📧 <span>Email & Communications</span></h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ fontSize: '0.82rem', color: '#94a3b8' }}>Voice Mode:</span>
          <VoiceInputControl
            size="sm"
            showLangPicker={true}
            showReadAloud={true}
            readAloudText={
              subject || body
                ? (subject ? `Subject: ${subject}. Message: ${body}` : body)
                : 'Compose an email or click the microphone to dictate.'
            }
            onTranscript={(spoken) => {
              if (!subject) setSubject(spoken);
              else setBody((prev) => (prev ? `${prev}\n${spoken}` : spoken));
            }}
            label="Dictate into email"
          />
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="esp__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'compose'}
          className={`esp__tab ${activeTab === 'compose' ? 'esp__tab--active' : ''}`}
          onClick={() => setActiveTab('compose')}
        >
          ✍️ Compose
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'drafts'}
          className={`esp__tab ${activeTab === 'drafts' ? 'esp__tab--active' : ''}`}
          onClick={() => {
            setActiveTab('drafts');
            void loadEmails();
          }}
        >
          📝 Drafts <span className="esp__tab-count">{drafts.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'outbox'}
          className={`esp__tab ${activeTab === 'outbox' ? 'esp__tab--active' : ''}`}
          onClick={() => {
            setActiveTab('outbox');
            void loadEmails();
          }}
        >
          📤 Sent Outbox <span className="esp__tab-count">{sentEmails.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'templates'}
          className={`esp__tab ${activeTab === 'templates' ? 'esp__tab--active' : ''}`}
          onClick={() => {
            setActiveTab('templates');
            void loadTemplates();
          }}
        >
          📋 Templates <span className="esp__tab-count">{templates.length}</span>
        </button>
      </div>

      <div className="esp__body">
        {/* TAB 1: COMPOSE */}
        {activeTab === 'compose' && (
          <>
            {sent ? (
              <div className="esp__success">
                <span className="esp__success-icon">✅</span>
                <p className="esp__success-title">Email Dispatched Successfully!</p>
                <p className="esp__success-meta">
                  Delivered to: <strong>{sent.to}</strong>
                </p>
                <p className="esp__success-meta" style={{ fontSize: '0.85rem', opacity: 0.8 }}>
                  Ref ID: {sent.messageId} · Dispatched at: {new Date(sent.sentAt).toLocaleTimeString()}
                </p>
                <button type="button" className="esp__new-btn" onClick={resetComposer}>
                  Compose Another Email
                </button>
              </div>
            ) : (
              <>
                {/* AI Smart Drafting Assistant Bar */}
                <div className="esp__ai-bar">
                  <div className="esp__ai-header">
                    <span>✨ AI Smart Composer & Tone Assistant</span>
                    <span style={{ fontSize: '0.75rem', opacity: 0.8 }}>Turn notes into professional emails</span>
                  </div>
                  <div className="esp__ai-controls">
                    <input
                      type="text"
                      className="esp__ai-input"
                      placeholder="e.g., follow up on Q3 report, request approval by Friday, thank team..."
                      value={aiPrompt}
                      onChange={(e) => setAiPrompt(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          void handleAiCompose();
                        }
                      }}
                    />
                    <select
                      className="esp__ai-select"
                      value={aiTone}
                      onChange={(e) => setAiTone(e.target.value)}
                      title="Select Tone"
                    >
                      <option value="professional">Professional</option>
                      <option value="executive">Executive Brief</option>
                      <option value="casual">Casual & Warm</option>
                      <option value="persuasive">Persuasive Pitch</option>
                      <option value="friendly">Friendly</option>
                      <option value="apologetic">Apologetic</option>
                    </select>
                    <button
                      type="button"
                      className="esp__ai-btn"
                      onClick={() => void handleAiCompose()}
                      disabled={isAiLoading || !aiPrompt.trim()}
                    >
                      {isAiLoading ? 'Drafting…' : '✨ Draft with AI'}
                    </button>
                  </div>
                </div>

                {/* Sender Settings Dropdown */}
                <div style={{ marginBottom: '1rem', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '0.6rem 0.85rem', background: 'rgba(30, 41, 59, 0.4)', maxWidth: '760px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                      ⚙️ Sender Settings: {appPassword ? '✅ App Password Active' : 'ℹ️ Direct Gmail App Password (Optional)'}
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowSettings(!showSettings)}
                      style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', fontSize: '0.82rem' }}
                    >
                      {showSettings ? 'Hide ▲' : 'Configure ▼'}
                    </button>
                  </div>
                  {showSettings && (
                    <div style={{ marginTop: '0.65rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      <p style={{ margin: 0, fontSize: '0.78rem', color: '#94a3b8', lineHeight: 1.4 }}>
                        If you have not connected Google OAuth, you can provide a 16-character <strong>Google App Password</strong> to dispatch directly:
                      </p>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                        <input
                          type="email"
                          className="esp__input"
                          style={{ fontSize: '0.82rem', padding: '0.4rem 0.6rem' }}
                          placeholder="Sender Gmail"
                          value={senderEmail}
                          onChange={(e) => {
                            setSenderEmail(e.target.value);
                            localStorage.setItem('roxy_smtp_user', e.target.value);
                          }}
                        />
                        <input
                          type="password"
                          className="esp__input"
                          style={{ fontSize: '0.82rem', padding: '0.4rem 0.6rem' }}
                          placeholder="16-character App Password"
                          value={appPassword}
                          onChange={(e) => {
                            setAppPassword(e.target.value);
                            localStorage.setItem('roxy_smtp_pass', e.target.value);
                            setSavedSettings(true);
                          }}
                        />
                      </div>
                      {savedSettings && (
                        <span style={{ fontSize: '0.75rem', color: '#34d399' }}>✓ Saved to browser storage</span>
                      )}
                    </div>
                  )}
                </div>

                {infoMessage && (
                  <div style={{ maxWidth: '760px', marginBottom: '0.75rem', padding: '0.5rem 0.75rem', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '6px', color: '#34d399', fontSize: '0.82rem' }}>
                    {infoMessage}
                  </div>
                )}

                {error && <div className="esp__error" style={{ maxWidth: '760px', marginBottom: '0.75rem' }}>{error}</div>}

                {/* Compose Form */}
                <form className="esp__form" onSubmit={handleSubmit}>
                  <div className="esp__field">
                    <label htmlFor="esp-to">Recipient To *</label>
                    <input
                      id="esp-to"
                      type="email"
                      className="esp__input"
                      placeholder="recipient@example.com"
                      value={to}
                      onChange={(e) => setTo(e.target.value)}
                      required
                    />
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <button
                      type="button"
                      onClick={() => setShowCcBcc(!showCcBcc)}
                      style={{ background: 'none', border: 'none', color: '#818cf8', fontSize: '0.78rem', cursor: 'pointer', padding: 0 }}
                    >
                      {showCcBcc ? 'Hide CC / BCC ▲' : '+ Add CC / BCC ▼'}
                    </button>
                  </div>

                  {showCcBcc && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                      <div className="esp__field">
                        <label htmlFor="esp-cc">CC (optional)</label>
                        <input
                          id="esp-cc"
                          type="text"
                          className="esp__input"
                          placeholder="comma-separated"
                          value={cc}
                          onChange={(e) => setCc(e.target.value)}
                        />
                      </div>
                      <div className="esp__field">
                        <label htmlFor="esp-bcc">BCC (optional)</label>
                        <input
                          id="esp-bcc"
                          type="text"
                          className="esp__input"
                          placeholder="comma-separated"
                          value={bcc}
                          onChange={(e) => setBcc(e.target.value)}
                        />
                      </div>
                    </div>
                  )}

                  <div className="esp__field">
                    <label htmlFor="esp-subject">Subject *</label>
                    <input
                      id="esp-subject"
                      type="text"
                      className="esp__input"
                      placeholder="e.g. Project Sprint Update & Next Steps"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      required
                    />
                  </div>

                  <div className="esp__field">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <label htmlFor="esp-body">Message Body *</label>
                      <button
                        type="button"
                        className="esp__polish-btn"
                        onClick={() => void handleAiPolish()}
                        disabled={isAiLoading || !body.trim()}
                        title="Polish and elevate phrasing using AI"
                      >
                        {isAiLoading ? 'Polishing…' : '✨ Polish with AI'}
                      </button>
                    </div>
                    <textarea
                      id="esp-body"
                      className="esp__textarea"
                      placeholder="Write your email message here or dictate above..."
                      value={body}
                      onChange={(e) => setBody(e.target.value)}
                      required
                    />
                  </div>

                  <div className="esp__actions">
                    <button
                      type="submit"
                      className="esp__send-btn"
                      disabled={submitting || !to.trim() || !subject.trim() || !body.trim()}
                    >
                      {submitting ? 'Sending…' : 'Send Email'}
                    </button>
                    <button
                      type="button"
                      className="esp__draft-btn"
                      onClick={() => void handleSaveDraft()}
                      disabled={submitting || (!to.trim() && !subject.trim() && !body.trim())}
                    >
                      Save as Draft
                    </button>
                    <button
                      type="button"
                      className="esp__reset-btn"
                      onClick={resetComposer}
                    >
                      Clear
                    </button>
                  </div>
                </form>
              </>
            )}
          </>
        )}

        {/* TAB 2: DRAFTS */}
        {activeTab === 'drafts' && (
          <div>
            {loadingList ? (
              <p style={{ color: 'var(--color-muted)', fontSize: '0.85rem' }}>Loading drafts…</p>
            ) : drafts.length === 0 ? (
              <div className="esp__empty">
                <div className="esp__empty-icon">📝</div>
                <div className="esp__empty-title">No saved drafts yet</div>
                <div className="esp__empty-sub">
                  Drafts you save while composing will be stored here across all your sessions.
                </div>
                <button
                  type="button"
                  className="esp__send-btn"
                  style={{ fontSize: '0.82rem', padding: '0.45rem 1rem' }}
                  onClick={() => setActiveTab('compose')}
                >
                  Start Composing
                </button>
              </div>
            ) : (
              <div className="esp__list">
                {drafts.map((d) => (
                  <div key={d.id} className="esp__card">
                    <div className="esp__card-content">
                      <div className="esp__card-header">
                        <span className="esp__card-subj">{d.subject || '(Untitled Draft)'}</span>
                        <span className="esp__card-badge esp__card-badge--draft">Draft</span>
                      </div>
                      <div className="esp__card-to">To: {d.to || 'Unspecified'}</div>
                      <div className="esp__card-body-snippet">{d.body || '(Empty body)'}</div>
                      <div className="esp__card-time">
                        Last updated: {d.updated_at ? new Date(d.updated_at).toLocaleString() : 'Recently'}
                      </div>
                    </div>
                    <div className="esp__card-actions">
                      <button
                        type="button"
                        className="esp__card-btn"
                        onClick={() => handleOpenDraft(d)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="esp__card-btn esp__card-btn--danger"
                        onClick={() => void handleDelete(d.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: SENT OUTBOX */}
        {activeTab === 'outbox' && (
          <div>
            {loadingList ? (
              <p style={{ color: 'var(--color-muted)', fontSize: '0.85rem' }}>Loading outbox…</p>
            ) : sentEmails.length === 0 ? (
              <div className="esp__empty">
                <div className="esp__empty-icon">📤</div>
                <div className="esp__empty-title">No sent messages yet</div>
                <div className="esp__empty-sub">
                  Emails dispatched through Roxy will appear here with delivery timestamps and recipient details.
                </div>
                <button
                  type="button"
                  className="esp__send-btn"
                  style={{ fontSize: '0.82rem', padding: '0.45rem 1rem' }}
                  onClick={() => setActiveTab('compose')}
                >
                  Send an Email
                </button>
              </div>
            ) : (
              <div className="esp__list">
                {sentEmails.map((s) => (
                  <div key={s.id} className="esp__card">
                    <div className="esp__card-content">
                      <div className="esp__card-header">
                        <span className="esp__card-subj">{s.subject}</span>
                        <span className={`esp__card-badge esp__card-badge--${s.status}`}>
                          {s.status}
                        </span>
                      </div>
                      <div className="esp__card-to">To: {s.to}</div>
                      <div className="esp__card-body-snippet">{s.body}</div>
                      <div className="esp__card-time">
                        Dispatched: {s.sent_at ? new Date(s.sent_at).toLocaleString() : (s.created_at ? new Date(s.created_at).toLocaleString() : 'Recently')}
                        {s.message_id && ` · Ref: ${s.message_id}`}
                      </div>
                    </div>
                    <div className="esp__card-actions">
                      <button
                        type="button"
                        className="esp__card-btn"
                        onClick={() => {
                          setTo(s.to);
                          setSubject(`Fwd: ${s.subject}`);
                          setBody(`\n\n--- Original Message ---\n${s.body}`);
                          setActiveTab('compose');
                        }}
                      >
                        Forward
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: TEMPLATES */}
        {activeTab === 'templates' && (
          <div className="esp__templates-grid">
            {templates.map((tpl) => (
              <div key={tpl.id} className="esp__template-card">
                <div>
                  <h4 className="esp__template-title">{tpl.title}</h4>
                  <div className="esp__template-subj">{tpl.subject}</div>
                  <div className="esp__template-preview">{tpl.body}</div>
                </div>
                <button
                  type="button"
                  className="esp__template-use-btn"
                  onClick={() => handleUseTemplate(tpl)}
                >
                  Use Template →
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
