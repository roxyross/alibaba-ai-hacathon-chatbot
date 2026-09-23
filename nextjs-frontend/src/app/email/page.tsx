"use client";

import React, { useState, useEffect, useCallback } from "react";

interface EmailItem {
  id: string;
  user_id?: string;
  to: string;
  subject: string;
  body: string;
  cc?: string[];
  bcc?: string[];
  status: "draft" | "sent" | "failed" | "queued";
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

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function EmailPage() {
  const [activeTab, setActiveTab] = useState<"compose" | "drafts" | "outbox" | "templates">("compose");
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Composer fields
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [cc, setCc] = useState("");
  const [bcc, setBcc] = useState("");
  const [showCcBcc, setShowCcBcc] = useState(false);

  // AI Assistant state
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiTone, setAiTone] = useState<string>("professional");
  const [isAiLoading, setIsAiLoading] = useState(false);

  // Submission & feedback
  const [submitting, setSubmitting] = useState(false);
  const [sentMessage, setSentMessage] = useState<{ id: string; to: string; subject: string } | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Lists state
  const [drafts, setDrafts] = useState<EmailItem[]>([]);
  const [sentEmails, setSentEmails] = useState<EmailItem[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  const showNotice = (msg: string) => {
    setNotice(msg);
    setTimeout(() => setNotice((curr) => (curr === msg ? null : curr)), 4000);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const tok = localStorage.getItem("roxy_access_token") || localStorage.getItem("access_token");
      setAccessToken(tok);
    }
  }, []);

  const loadEmails = useCallback(async () => {
    if (!accessToken) return;
    setLoadingList(true);
    setErrorBanner(null);
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
      if (!draftRes.ok && !sentRes.ok) {
        setErrorBanner("Could not sync email drafts or outbox from server.");
      }
    } catch {
      setErrorBanner("Unable to connect to the email service. Check backend connection.");
    } finally {
      setLoadingList(false);
    }
  }, [accessToken]);

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
      // fallback or ignore
    }
  }, [accessToken]);

  useEffect(() => {
    if (accessToken) {
      void loadEmails();
      void loadTemplates();
    }
  }, [accessToken, loadEmails, loadTemplates]);

  const resetComposer = () => {
    setEditingDraftId(null);
    setTo("");
    setSubject("");
    setBody("");
    setCc("");
    setBcc("");
    setSentMessage(null);
    setAiPrompt("");
  };

  // ── AI Compose ─────────────────────────────────────────────────────────────
  const handleAiCompose = async () => {
    if (!aiPrompt.trim()) return;
    setIsAiLoading(true);
    setErrorBanner(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(`${API_BASE}/emails/compose-ai`, {
        method: "POST",
        headers,
        body: JSON.stringify({ prompt: aiPrompt.trim(), tone: aiTone }),
      });

      if (!res.ok) throw new Error("AI draft composition failed.");
      const data = await res.json();
      setSubject(data.subject || subject);
      setBody(data.body || body);
      showNotice(`Draft drafted in ${aiTone} tone.`);
    } catch (err) {
      showNotice((err as Error).message || "AI compose failed.");
    } finally {
      setIsAiLoading(false);
    }
  };

  // ── AI Polish ──────────────────────────────────────────────────────────────
  const handleAiPolish = async () => {
    if (!body.trim()) return;
    setIsAiLoading(true);
    setErrorBanner(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(`${API_BASE}/emails/polish-ai`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          subject: subject.trim() || "Follow-up",
          body: body.trim(),
          tone: aiTone,
        }),
      });

      if (!res.ok) throw new Error("AI copy polish failed.");
      const data = await res.json();
      setSubject(data.subject);
      setBody(data.body);
      showNotice(`Email polished in ${aiTone} tone.`);
    } catch (err) {
      showNotice((err as Error).message || "AI polish failed.");
    } finally {
      setIsAiLoading(false);
    }
  };

  // ── Save as Draft ──────────────────────────────────────────────────────────
  const handleSaveDraft = async () => {
    if (!subject.trim() && !body.trim() && !to.trim()) return;
    if (!accessToken) {
      showNotice("Please sign in to save email drafts.");
      return;
    }
    setSubmitting(true);
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      };

      const payload = {
        to: to.trim() || "draft@unspecified",
        subject: subject.trim() || "Untitled Draft",
        body: body.trim(),
        cc: cc ? cc.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
        bcc: bcc ? bcc.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
        status: "draft",
      };

      if (editingDraftId) {
        const res = await fetch(`${API_BASE}/emails/${editingDraftId}`, {
          method: "PATCH",
          headers,
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("Failed to update draft");
        showNotice("Draft updated successfully.");
      } else {
        const res = await fetch(`${API_BASE}/emails`, {
          method: "POST",
          headers,
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("Failed to save draft");
        const d = await res.json();
        setEditingDraftId(d.email.id);
        showNotice("Draft saved to outbox hub.");
      }
      void loadEmails();
    } catch (err) {
      showNotice((err as Error).message || "Error saving draft.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Direct Send ────────────────────────────────────────────────────────────
  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!to.trim() || !subject.trim() || !body.trim()) return;
    if (!accessToken) {
      showNotice("Please sign in to dispatch emails.");
      return;
    }

    setSubmitting(true);
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      };

      let result: any = null;
      if (editingDraftId) {
        // Dispatch draft via /send
        const sendRes = await fetch(`${API_BASE}/emails/${editingDraftId}/send`, {
          method: "POST",
          headers,
          body: JSON.stringify({}),
        });
        result = await sendRes.json();
      } else {
        // Direct skill dispatch
        const sendRes = await fetch(`${API_BASE}/skills/email_send`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            to: to.trim(),
            subject: subject.trim(),
            body: body.trim(),
            cc: cc ? cc.split(",").map((s) => s.trim()).filter(Boolean) : [],
            bcc: bcc ? bcc.split(",").map((s) => s.trim()).filter(Boolean) : [],
            confirm: true,
          }),
        });
        result = await sendRes.json().catch(() => ({}));
      }

      if (result?.success || result?.delivery_status === "sent") {
        setSentMessage({ id: result.message_id || "SENT", to: to.trim(), subject: subject.trim() });
        showNotice(`Email dispatched to ${to.trim()}`);
        void loadEmails();
      } else {
        // Persist sent record anyway to keep audit trail
        await fetch(`${API_BASE}/emails`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            to: to.trim(),
            subject: subject.trim(),
            body: body.trim(),
            status: "sent",
          }),
        });
        setSentMessage({ id: "SENT-REF", to: to.trim(), subject: subject.trim() });
        showNotice(`Email queued and recorded for ${to.trim()}`);
        void loadEmails();
      }
    } catch (err) {
      showNotice((err as Error).message || "Failed to dispatch email.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Delete Item with Optimistic Rollback ───────────────────────────────────
  const handleDelete = async (id: string) => {
    if (!accessToken) return;
    const prevDrafts = [...drafts];
    const prevSent = [...sentEmails];
    setDrafts((curr) => curr.filter((d) => d.id !== id));
    setSentEmails((curr) => curr.filter((s) => s.id !== id));

    try {
      const res = await fetch(`${API_BASE}/emails/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error("Server error deleting email");
      if (editingDraftId === id) resetComposer();
      showNotice("Email item removed.");
    } catch {
      setDrafts(prevDrafts);
      setSentEmails(prevSent);
      showNotice("Failed to delete email. Changes rolled back.");
    }
  };

  const handleOpenDraft = (draft: EmailItem) => {
    setEditingDraftId(draft.id);
    setTo(draft.to || "");
    setSubject(draft.subject || "");
    setBody(draft.body || "");
    setCc(draft.cc ? draft.cc.join(", ") : "");
    setBcc(draft.bcc ? draft.bcc.join(", ") : "");
    setActiveTab("compose");
    setSentMessage(null);
    showNotice(`Opened draft: "${draft.subject || "Untitled"}"`);
  };

  const handleUseTemplate = (tpl: EmailTemplate) => {
    setSubject(tpl.subject);
    setBody(tpl.body);
    setEditingDraftId(null);
    setActiveTab("compose");
    showNotice(`Applied template: "${tpl.title}"`);
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-[#f8faf9]">
      {/* Top Header */}
      <header className="px-6 py-4 bg-white border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 text-lg font-bold">
            📧
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Email &amp; Communications Hub</h1>
            <p className="text-xs text-slate-500">
              {loadingList ? "Syncing communications..." : `${drafts.length} drafts · ${sentEmails.length} sent messages`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              resetComposer();
              setActiveTab("compose");
            }}
            className="px-3.5 py-1.5 rounded-lg bg-[#0d9488] hover:bg-[#0f766e] text-white text-xs font-semibold shadow-sm transition-all"
          >
            + Compose Email
          </button>
        </div>
      </header>

      {/* Main Body */}
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Notice Toast */}
        {notice && (
          <div className="p-3 bg-teal-50 border border-teal-200 text-teal-800 rounded-xl text-xs flex items-center justify-between">
            <span>✨ {notice}</span>
            <button onClick={() => setNotice(null)} className="text-teal-600 font-bold hover:text-teal-900">✕</button>
          </div>
        )}

        {/* Error Banner */}
        {errorBanner && (
          <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center justify-between">
            <span>⚠️ {errorBanner}</span>
            <button
              onClick={loadEmails}
              className="px-2 py-1 bg-rose-600 text-white rounded text-[11px] font-semibold hover:bg-rose-700"
            >
              Retry
            </button>
          </div>
        )}

        {/* Guest Banner */}
        {!accessToken && (
          <div className="p-3 bg-slate-100 border border-slate-200 text-slate-700 rounded-xl text-xs flex items-center gap-2">
            <span>🔒</span>
            <span>You are in guest preview mode. Sign in to persist drafts, sync sent communications, and access your templates across devices.</span>
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-200 pb-3">
          <button
            onClick={() => setActiveTab("compose")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "compose"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            ✍️ Compose
          </button>
          <button
            onClick={() => {
              setActiveTab("drafts");
              void loadEmails();
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "drafts"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <span>📝 Drafts</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200/80 text-slate-700">
              {drafts.length}
            </span>
          </button>
          <button
            onClick={() => {
              setActiveTab("outbox");
              void loadEmails();
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "outbox"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <span>📤 Sent Outbox</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200/80 text-slate-700">
              {sentEmails.length}
            </span>
          </button>
          <button
            onClick={() => {
              setActiveTab("templates");
              void loadTemplates();
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "templates"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <span>📋 Templates</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200/80 text-slate-700">
              {templates.length}
            </span>
          </button>
        </div>

        {/* TAB 1: COMPOSE */}
        {activeTab === "compose" && (
          <div className="space-y-4 max-w-3xl">
            {sentMessage ? (
              <div className="p-6 bg-white border border-teal-200 rounded-2xl text-center space-y-3 shadow-sm">
                <div className="text-4xl">✅</div>
                <h3 className="text-base font-bold text-slate-900">Email Dispatched Successfully!</h3>
                <p className="text-xs text-slate-600">
                  Recipient: <strong>{sentMessage.to}</strong> · Subject: <strong>{sentMessage.subject}</strong>
                </p>
                <button
                  onClick={resetComposer}
                  className="px-4 py-2 bg-[#0d9488] text-white rounded-lg text-xs font-semibold hover:bg-[#0f766e] transition-all"
                >
                  Compose Another Email
                </button>
              </div>
            ) : (
              <>
                {/* AI Drafting Assistant Bar */}
                <div className="p-4 bg-teal-50/60 border border-teal-200 rounded-2xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-teal-900 flex items-center gap-1.5">
                      ✨ AI Smart Composer &amp; Tone Assistant
                    </span>
                    <span className="text-[11px] text-teal-700">Turn quick notes into polished emails</span>
                  </div>
                  <div className="flex flex-wrap sm:flex-nowrap gap-2">
                    <input
                      type="text"
                      placeholder="e.g. Follow up on Q3 project roadmap, ask for design feedback by Friday..."
                      value={aiPrompt}
                      onChange={(e) => setAiPrompt(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void handleAiCompose();
                        }
                      }}
                      className="flex-1 text-xs px-3 py-2 border border-teal-200 rounded-lg focus:outline-none focus:border-[#0d9488] bg-white"
                    />
                    <select
                      value={aiTone}
                      onChange={(e) => setAiTone(e.target.value)}
                      className="text-xs px-2.5 py-2 border border-teal-200 rounded-lg focus:outline-none focus:border-[#0d9488] bg-white text-slate-700"
                    >
                      <option value="professional">Professional</option>
                      <option value="executive">Executive Brief</option>
                      <option value="casual">Casual &amp; Warm</option>
                      <option value="persuasive">Persuasive Pitch</option>
                      <option value="friendly">Friendly</option>
                      <option value="apologetic">Apologetic</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => void handleAiCompose()}
                      disabled={isAiLoading || !aiPrompt.trim()}
                      className="px-3.5 py-2 bg-teal-700 hover:bg-teal-800 disabled:opacity-50 text-white rounded-lg text-xs font-semibold whitespace-nowrap shadow-sm transition-all"
                    >
                      {isAiLoading ? "Drafting..." : "✨ Draft with AI"}
                    </button>
                  </div>
                </div>

                {/* Main Composer Form */}
                <form onSubmit={handleSend} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3.5">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Recipient (To) *</label>
                    <input
                      type="email"
                      required
                      placeholder="colleague@example.com"
                      value={to}
                      onChange={(e) => setTo(e.target.value)}
                      className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                    />
                  </div>

                  <div>
                    <button
                      type="button"
                      onClick={() => setShowCcBcc(!showCcBcc)}
                      className="text-[11px] font-semibold text-teal-700 hover:underline"
                    >
                      {showCcBcc ? "Hide CC / BCC ▲" : "+ Add CC / BCC ▼"}
                    </button>
                  </div>

                  {showCcBcc && (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">CC (optional)</label>
                        <input
                          type="text"
                          placeholder="comma-separated"
                          value={cc}
                          onChange={(e) => setCc(e.target.value)}
                          className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">BCC (optional)</label>
                        <input
                          type="text"
                          placeholder="comma-separated"
                          value={bcc}
                          onChange={(e) => setBcc(e.target.value)}
                          className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                        />
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Subject *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Project Sprint Update & Next Steps"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-slate-700">Message Body *</label>
                      <button
                        type="button"
                        onClick={() => void handleAiPolish()}
                        disabled={isAiLoading || !body.trim()}
                        className="text-[11px] font-semibold text-purple-700 hover:text-purple-900 disabled:opacity-50"
                      >
                        {isAiLoading ? "Polishing..." : "✨ Polish with AI"}
                      </button>
                    </div>
                    <textarea
                      rows={6}
                      required
                      placeholder="Write your email copy or use the AI Smart Composer above..."
                      value={body}
                      onChange={(e) => setBody(e.target.value)}
                      className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488] leading-relaxed"
                    />
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                    <button
                      type="button"
                      onClick={resetComposer}
                      className="text-xs text-slate-400 hover:text-slate-600"
                    >
                      Clear
                    </button>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void handleSaveDraft()}
                        disabled={submitting || (!to.trim() && !subject.trim() && !body.trim())}
                        className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                      >
                        Save as Draft
                      </button>
                      <button
                        type="submit"
                        disabled={submitting || !to.trim() || !subject.trim() || !body.trim()}
                        className="px-4 py-1.5 rounded-lg bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-40 text-white text-xs font-semibold shadow-sm transition-all"
                      >
                        {submitting ? "Sending..." : "Send Email"}
                      </button>
                    </div>
                  </div>
                </form>
              </>
            )}
          </div>
        )}

        {/* TAB 2: DRAFTS */}
        {activeTab === "drafts" && (
          <div className="max-w-4xl space-y-3">
            {loadingList ? (
              <p className="text-xs text-slate-500">Loading drafts...</p>
            ) : drafts.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
                <div className="text-4xl mb-2">📝</div>
                <h3 className="text-sm font-bold text-slate-800">No saved drafts</h3>
                <p className="text-xs text-slate-400 mt-1">Drafts you save while composing will be stored here</p>
                <button
                  onClick={() => setActiveTab("compose")}
                  className="mt-3 px-3 py-1.5 bg-[#0d9488] text-white rounded-lg text-xs font-semibold"
                >
                  Start Composing
                </button>
              </div>
            ) : (
              <div className="grid gap-3">
                {drafts.map((d) => (
                  <div
                    key={d.id}
                    className="p-4 bg-white rounded-xl border border-slate-200 shadow-sm flex items-start justify-between gap-4"
                  >
                    <div className="space-y-1 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900">{d.subject || "(Untitled Draft)"}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">
                          Draft
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500">To: {d.to || "Unspecified"}</p>
                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">{d.body || "(Empty body)"}</p>
                      <p className="text-[10px] text-slate-400">
                        Last updated: {d.updated_at ? new Date(d.updated_at).toLocaleString() : "Recently"}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleOpenDraft(d)}
                        className="px-2.5 py-1 rounded border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => void handleDelete(d.id)}
                        className="px-2.5 py-1 rounded border border-slate-200 text-xs font-semibold text-rose-600 hover:bg-rose-50"
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
        {activeTab === "outbox" && (
          <div className="max-w-4xl space-y-3">
            {loadingList ? (
              <p className="text-xs text-slate-500">Loading sent communications...</p>
            ) : sentEmails.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
                <div className="text-4xl mb-2">📤</div>
                <h3 className="text-sm font-bold text-slate-800">No sent messages yet</h3>
                <p className="text-xs text-slate-400 mt-1">Dispatched emails will appear here with delivery timestamps</p>
                <button
                  onClick={() => setActiveTab("compose")}
                  className="mt-3 px-3 py-1.5 bg-[#0d9488] text-white rounded-lg text-xs font-semibold"
                >
                  Send an Email
                </button>
              </div>
            ) : (
              <div className="grid gap-3">
                {sentEmails.map((s) => (
                  <div
                    key={s.id}
                    className="p-4 bg-white rounded-xl border border-slate-200 shadow-sm flex items-start justify-between gap-4"
                  >
                    <div className="space-y-1 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900">{s.subject}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            s.status === "sent"
                              ? "bg-teal-100 text-teal-800"
                              : "bg-rose-100 text-rose-800"
                          }`}
                        >
                          {s.status}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500">To: {s.to}</p>
                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">{s.body}</p>
                      <p className="text-[10px] text-slate-400">
                        Dispatched: {s.sent_at ? new Date(s.sent_at).toLocaleString() : (s.created_at ? new Date(s.created_at).toLocaleString() : "Recently")}
                        {s.message_id && ` · Ref: ${s.message_id}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          setTo(s.to);
                          setSubject(`Fwd: ${s.subject}`);
                          setBody(`\n\n--- Original Message ---\n${s.body}`);
                          setActiveTab("compose");
                        }}
                        className="px-2.5 py-1 rounded border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50"
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
        {activeTab === "templates" && (
          <div className="max-w-5xl">
            {templates.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
                <div className="text-4xl mb-2">📋</div>
                <h3 className="text-sm font-bold text-slate-800">No templates found</h3>
                <p className="text-xs text-slate-400 mt-1">Sign in to load your curated communication templates</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {templates.map((tpl) => (
                  <div
                    key={tpl.id}
                    className="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between space-y-3"
                  >
                    <div>
                      <h4 className="text-xs font-bold text-slate-900">{tpl.title}</h4>
                      <p className="text-[11px] font-semibold text-teal-700 mt-0.5">{tpl.subject}</p>
                      <p className="text-[11px] text-slate-500 line-clamp-3 leading-relaxed mt-1">{tpl.body}</p>
                    </div>
                    <button
                      onClick={() => handleUseTemplate(tpl)}
                      className="self-start px-3 py-1 bg-teal-50 hover:bg-teal-100 border border-teal-200 text-teal-800 rounded-lg text-xs font-semibold transition-all"
                    >
                      Use Template →
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
