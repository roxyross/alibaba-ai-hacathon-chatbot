"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";

export type ApprovalTier = "T1" | "T2" | "T3";
export type AuditStatusCode = "ok" | "caution" | "blocked" | "error";
export type RiskVerdict = "clear" | "caution" | "block";

interface AuditLogItem {
  id: string;
  user_id?: string;
  trace_id: string;
  agent_slug: string;
  action: string;
  skill_slug?: string | null;
  approval_tier: string;
  approved_by: string;
  model_used?: string | null;
  provider?: string | null;
  request_query?: string | null;
  response_summary?: string | null;
  decision: string;
  latency_ms: number;
  status_code: string;
  details?: Record<string, unknown>;
  created_at?: string | null;
}

interface AuditStats {
  total_events: number;
  today_events: number;
  by_agent: Record<string, number>;
  by_status: Record<string, number>;
  by_tier: Record<string, number>;
  avg_latency_ms: number;
  retention_days: number;
  last_event_at?: string | null;
}

interface RiskCheckResponse {
  action: string;
  risk_verdict: RiskVerdict;
  approval_tier: ApprovalTier;
  reason: string;
  warning_to_user: string;
  narrower_alternative?: string | null;
  blast_radius: string;
  is_reversible: boolean;
  blocking: boolean;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function AuditPage() {
  const [activeTab, setActiveTab] = useState<"timeline" | "risk_gate" | "compliance">("timeline");
  const [token, setToken] = useState<string | null>(null);

  // Timeline State
  const [events, setEvents] = useState<AuditLogItem[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Risk Gate Simulator State
  const [riskAction, setRiskAction] = useState("send_email");
  const [riskTarget, setRiskTarget] = useState("client@example.com");
  const [riskPrompt, setRiskPrompt] = useState("Send the proposal email with confidential pricing.");
  const [riskParamsJson, setRiskParamsJson] = useState('{\n  "recipient": "client@example.com",\n  "subject": "Q3 Proposal"\n}');
  const [riskVerdict, setRiskVerdict] = useState<RiskCheckResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);

  // Compliance Export State
  const [exporting, setExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState<string | null>(null);

  // Toast State
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }, []);

  // Auth initialization
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("access_token") || localStorage.getItem("auth_token");
      if (stored) setToken(stored);
    }
  }, []);

  const authHeaders = useMemo(() => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }, [token]);

  // Fetch Stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/audit/stats`, { headers: authHeaders });
      if (res.ok) {
        const data = (await res.json()) as AuditStats;
        setStats(data);
      }
    } catch {
      // Non-blocking telemetry
    }
  }, [authHeaders]);

  // Fetch Events
  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (agentFilter !== "all") params.append("agent_slug", agentFilter);
      if (tierFilter !== "all") params.append("approval_tier", tierFilter);
      if (statusFilter !== "all") params.append("status_code", statusFilter);
      if (searchQuery.trim()) params.append("search", searchQuery.trim());
      params.append("limit", "50");

      const res = await fetch(`${API_BASE}/audit?${params.toString()}`, { headers: authHeaders });
      if (!res.ok) throw new Error(`Failed to load audit logs (${res.status})`);
      const data = await res.json();
      setEvents(data.items || []);
    } catch (err: any) {
      const msg = err.message || "Failed to load audit logs";
      setError(msg);
      showToast("error", msg);
    } finally {
      setLoading(false);
    }
  }, [agentFilter, tierFilter, statusFilter, searchQuery, authHeaders, showToast]);

  useEffect(() => {
    void fetchEvents();
    void fetchStats();
  }, [fetchEvents, fetchStats]);

  // Run Risk Gate Check
  const handleEvaluateRisk = async (e: React.FormEvent) => {
    e.preventDefault();
    setRiskLoading(true);
    setRiskError(null);
    setRiskVerdict(null);

    let parsedParams: Record<string, unknown> = {};
    try {
      if (riskParamsJson.trim()) {
        parsedParams = JSON.parse(riskParamsJson);
      }
    } catch {
      setRiskError("Invalid JSON parameters format");
      setRiskLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/audit/risk-check`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          action_type: riskAction.trim(),
          target: riskTarget.trim() || undefined,
          params: parsedParams,
          user_prompt: riskPrompt.trim() || undefined,
        }),
      });

      if (!res.ok) throw new Error(`Risk evaluation failed (${res.status})`);
      const verdict = (await res.json()) as RiskCheckResponse;
      setRiskVerdict(verdict);
      showToast("success", `Risk verdict computed: ${verdict.risk_verdict.toUpperCase()}`);
    } catch (err: any) {
      const msg = err.message || "Risk evaluation failed";
      setRiskError(msg);
      showToast("error", msg);
    } finally {
      setRiskLoading(false);
    }
  };

  // Export Audit Archive
  const handleExportArchive = async () => {
    setExporting(true);
    setExportSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/audit/export`, { headers: authHeaders });
      if (!res.ok) throw new Error(`Export request failed (${res.status})`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `roxy_audit_archive_${new Date().toISOString().slice(0, 10)}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setExportSuccess("Audit archive exported successfully (GDPR & CCPA Compliant).");
      showToast("success", "Audit archive exported successfully.");
    } catch (err: any) {
      showToast("error", err.message || "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case "T3":
        return "bg-rose-950/60 text-rose-300 border-rose-800";
      case "T2":
        return "bg-amber-950/60 text-amber-300 border-amber-800";
      default:
        return "bg-teal-950/60 text-teal-300 border-teal-800";
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "blocked":
        return "bg-rose-950/80 text-rose-300 border-rose-800";
      case "caution":
        return "bg-amber-950/80 text-amber-300 border-amber-800";
      case "error":
        return "bg-orange-950/80 text-orange-300 border-orange-800";
      default:
        return "bg-emerald-950/80 text-emerald-300 border-emerald-800";
    }
  };

  return (
    <div className="min-h-screen bg-[#0e1515] text-[#e0e7e7] pb-16">
      {/* Toast Notification */}
      {toast && (
        <div
          role="status"
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl border shadow-2xl backdrop-blur-md flex items-center gap-3 text-sm transition-all duration-300 ${
            toast.type === "success"
              ? "bg-emerald-950/90 text-emerald-200 border-emerald-700/80"
              : "bg-rose-950/90 text-rose-200 border-rose-700/80"
          }`}
        >
          <span>{toast.type === "success" ? "✓" : "⚠️"}</span>
          <span>{toast.message}</span>
          <button
            type="button"
            onClick={() => setToast(null)}
            className="ml-2 text-slate-400 hover:text-white"
          >
            ✕
          </button>
        </div>
      )}

      {/* Top Banner Header */}
      <header className="border-b border-[#273636] bg-[#141d1d]/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="text-2xl">🛡️</span>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                Audit, Security & Autonomous Activity Studio
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                  §10.12 Immutable Trail
                </span>
              </h1>
            </div>
            <p className="text-xs text-[#95a8a8] mt-1">
              Append-only audit trail with 1-year compliance retention, pre-execution risk gate verification, and action observability.
            </p>
          </div>

          {/* Telemetry Counter Chips */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Total Actions:</span>
              <span className="text-sm font-semibold text-emerald-400">
                {stats?.total_events ?? events.length}
              </span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Today:</span>
              <span className="text-sm font-semibold text-teal-400">
                {stats?.today_events ?? 0}
              </span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">T3 High-Stakes:</span>
              <span className="text-sm font-semibold text-rose-400">
                {stats?.by_tier?.T3 ?? 0}
              </span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Avg Latency:</span>
              <span className="text-sm font-semibold text-slate-300">
                {stats?.avg_latency_ms ? `${stats.avg_latency_ms} ms` : "0 ms"}
              </span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Retention:</span>
              <span className="text-sm font-semibold text-emerald-400">365 Days</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {/* Guest Authentication Banner */}
        {!token && (
          <div className="mb-6 p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-emerald-200 text-xs flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-base">ℹ️</span>
              <span>
                <strong>Guest Mode:</strong> Autonomous activity is logged ephemerally. Sign in with a verified account to enforce 1-year immutable audit retention and GDPR compliance reporting.
              </span>
            </div>
          </div>
        )}

        {/* Connection Error Banner */}
        {error && (
          <div className="mb-6 p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-200 text-xs flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-base">⚠️</span>
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => {
                void fetchEvents();
                void fetchStats();
              }}
              className="px-3 py-1 bg-rose-900/60 hover:bg-rose-900 border border-rose-700 rounded-lg font-medium text-xs transition-colors"
            >
              ↻ Retry Connection
            </button>
          </div>
        )}

        {/* Studio Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-[#273636] pb-3 mb-6 overflow-x-auto">
          <button
            type="button"
            onClick={() => setActiveTab("timeline")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "timeline"
                ? "bg-emerald-950/60 text-emerald-300 border border-emerald-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>📋</span>
            <span>Activity Timeline</span>
            <span className="text-xs px-1.5 py-0.2 bg-[#273636] rounded-full text-slate-300">
              {events.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("risk_gate")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "risk_gate"
                ? "bg-emerald-950/60 text-emerald-300 border border-emerald-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>⚡</span>
            <span>Risk Gate Simulator</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("compliance")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "compliance"
                ? "bg-emerald-950/60 text-emerald-300 border border-emerald-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>📜</span>
            <span>Compliance & Export</span>
          </button>
        </div>

        {/* ========================================================================= */}
        {/* TAB 1: ACTIVITY TIMELINE */}
        {/* ========================================================================= */}
        {activeTab === "timeline" && (
          <div className="space-y-6">
            {/* Filter Bar */}
            <div className="p-4 rounded-xl bg-[#141d1d] border border-[#273636] flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-3 flex-wrap flex-1">
                {/* Search Input */}
                <div className="relative min-w-[220px] flex-1 max-w-sm">
                  <span className="absolute left-3 top-2.5 text-slate-500 text-sm">🔍</span>
                  <input
                    type="text"
                    placeholder="Search action, query, or trace ID..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                {/* Agent Slug Selector */}
                <select
                  value={agentFilter}
                  onChange={(e) => setAgentFilter(e.target.value)}
                  className="px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500"
                >
                  <option value="all">All Agents</option>
                  <option value="coordinator">Coordinator</option>
                  <option value="coding">Coding Agent</option>
                  <option value="memory">Memory Curator</option>
                  <option value="browser">Browser Agent</option>
                  <option value="research">Research Agent</option>
                  <option value="finance">Finance Agent</option>
                  <option value="security">Security & Privacy</option>
                </select>

                {/* Approval Tier Selector */}
                <select
                  value={tierFilter}
                  onChange={(e) => setTierFilter(e.target.value)}
                  className="px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500"
                >
                  <option value="all">All Tiers</option>
                  <option value="T1">T1 (Safe Read)</option>
                  <option value="T2">T2 (Caution Action)</option>
                  <option value="T3">T3 (High-Stakes Block)</option>
                </select>

                {/* Status Code Selector */}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="ok">OK</option>
                  <option value="caution">Caution</option>
                  <option value="blocked">Blocked</option>
                  <option value="error">Error</option>
                </select>
              </div>

              <button
                type="button"
                onClick={() => {
                  void fetchEvents();
                  void fetchStats();
                }}
                className="px-3 py-2 bg-[#1a2525] hover:bg-[#273636] border border-[#273636] rounded-lg text-xs text-slate-300 font-medium transition-colors flex items-center justify-center gap-1.5"
              >
                <span>↻</span>
                <span>Refresh Logs</span>
              </button>
            </div>

            {/* Events Timeline List */}
            {loading ? (
              <div className="py-20 text-center text-slate-500 text-sm">
                <span className="inline-block animate-spin mr-2">↻</span> Loading audit logs...
              </div>
            ) : events.length === 0 ? (
              <div className="py-20 text-center rounded-2xl border border-dashed border-[#273636] bg-[#141d1d]/40 p-8">
                <span className="text-4xl block mb-3">🛡️</span>
                <h3 className="text-base font-semibold text-white mb-1">
                  {searchQuery || agentFilter !== "all" || tierFilter !== "all" || statusFilter !== "all"
                    ? "No matching audit events found"
                    : "No audit records logged yet"}
                </h3>
                <p className="text-xs text-[#95a8a8] max-w-sm mx-auto mb-4">
                  {searchQuery || agentFilter !== "all" || tierFilter !== "all" || statusFilter !== "all"
                    ? "Try adjusting your search query or reset your filter dropdowns."
                    : "Every tool call, autonomous execution, and security risk check across ROXY agents will be permanently recorded here."}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {events.map((event) => {
                  const isExpanded = expandedId === event.id;
                  return (
                    <div
                      key={event.id}
                      className="rounded-xl border border-[#273636] bg-[#141d1d] hover:border-emerald-700/60 transition-all overflow-hidden"
                    >
                      {/* Event Row Summary */}
                      <div
                        onClick={() => setExpandedId(isExpanded ? null : event.id)}
                        className="p-4 cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-3 select-none"
                      >
                        <div className="flex items-center gap-3 flex-wrap">
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider ${getTierBadge(
                              event.approval_tier
                            )}`}
                          >
                            {event.approval_tier}
                          </span>
                          <span
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-md border uppercase ${getStatusBadge(
                              event.status_code
                            )}`}
                          >
                            {event.status_code}
                          </span>
                          <span className="text-xs font-semibold text-white">
                            {event.action}
                          </span>
                          <span className="text-xs text-emerald-400 font-mono">
                            @{event.agent_slug}
                          </span>
                          {event.skill_slug && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1a2525] text-slate-400 border border-[#273636]">
                              {event.skill_slug}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-4 text-xs text-slate-400">
                          <span className="font-mono text-[11px]">
                            {event.latency_ms} ms
                          </span>
                          <span className="text-[11px]">
                            {event.created_at
                              ? new Date(event.created_at).toLocaleTimeString()
                              : "Just now"}
                          </span>
                          <span className="text-slate-500">
                            {isExpanded ? "▲" : "▼"}
                          </span>
                        </div>
                      </div>

                      {/* Expandable Drawer */}
                      {isExpanded && (
                        <div className="border-t border-[#273636] bg-[#0e1515] p-4 text-xs space-y-3">
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-[11px] text-slate-400">
                            <div>
                              <span className="text-slate-500 block">Trace ID:</span>
                              <span className="font-mono text-slate-200">{event.trace_id}</span>
                            </div>
                            <div>
                              <span className="text-slate-500 block">Approved By:</span>
                              <span className="text-slate-200">{event.approved_by}</span>
                            </div>
                            <div>
                              <span className="text-slate-500 block">Model / Provider:</span>
                              <span className="text-slate-200">
                                {event.model_used || "default"} ({event.provider || "internal"})
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-500 block">Decision:</span>
                              <span className="text-slate-200">{event.decision}</span>
                            </div>
                          </div>

                          {event.request_query && (
                            <div>
                              <span className="text-slate-500 block mb-1 text-[11px]">
                                Request Query:
                              </span>
                              <div className="p-2 rounded bg-black/40 font-mono text-[11px] text-slate-300 border border-[#273636] break-words">
                                {event.request_query}
                              </div>
                            </div>
                          )}

                          {event.response_summary && (
                            <div>
                              <span className="text-slate-500 block mb-1 text-[11px]">
                                Response Summary:
                              </span>
                              <div className="p-2 rounded bg-black/40 text-[11px] text-slate-300 border border-[#273636] break-words">
                                {event.response_summary}
                              </div>
                            </div>
                          )}

                          {event.details && Object.keys(event.details).length > 0 && (
                            <div>
                              <span className="text-slate-500 block mb-1 text-[11px]">
                                Execution Details:
                              </span>
                              <pre className="p-2 rounded bg-black/40 font-mono text-[10px] text-teal-300 border border-[#273636] overflow-x-auto">
                                {JSON.stringify(event.details, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: RISK GATE SIMULATOR */}
        {/* ========================================================================= */}
        {activeTab === "risk_gate" && (
          <div className="space-y-6">
            <div className="p-6 rounded-2xl bg-[#141d1d] border border-[#273636]">
              <h2 className="text-base font-bold text-white flex items-center gap-2 mb-2">
                <span>⚡</span> Pre-Execution Risk Gate Simulator
              </h2>
              <p className="text-xs text-[#95a8a8] mb-6 leading-relaxed">
                Test the autonomous Security &amp; Privacy guardrails that evaluate high-stakes autonomous tool calls before execution. Safe actions are cleared (T1), sensitive actions require user confirmation (T2), and destructive actions or secret exfiltration are blocked outright (T3).
              </p>

              <form onSubmit={handleEvaluateRisk} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Action Type:
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g., send_email, execute_code, drop_database, read_calendar"
                      value={riskAction}
                      onChange={(e) => setRiskAction(e.target.value)}
                      className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Target Resource (Optional):
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., client@example.com, users_table, aws_s3"
                      value={riskTarget}
                      onChange={(e) => setRiskTarget(e.target.value)}
                      className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    User Prompt / Intent Context:
                  </label>
                  <input
                    type="text"
                    placeholder="e.g., Send the invoice proposal to client with pricing"
                    value={riskPrompt}
                    onChange={(e) => setRiskPrompt(e.target.value)}
                    className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Parameters JSON Payload:
                  </label>
                  <textarea
                    rows={4}
                    value={riskParamsJson}
                    onChange={(e) => setRiskParamsJson(e.target.value)}
                    className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-emerald-300 font-mono focus:outline-none focus:border-emerald-500"
                  />
                </div>

                {riskError && (
                  <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">
                    ⚠️ {riskError}
                  </div>
                )}

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={riskLoading}
                    className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold shadow-lg transition-all disabled:opacity-50 inline-flex items-center gap-2"
                  >
                    {riskLoading ? "Evaluating Risk..." : "Evaluate Risk Verdict"}
                  </button>
                </div>
              </form>
            </div>

            {/* Verdict Display */}
            {riskVerdict && (
              <div
                className={`p-6 rounded-2xl border transition-all ${
                  riskVerdict.risk_verdict === "block"
                    ? "bg-rose-950/20 border-rose-800"
                    : riskVerdict.risk_verdict === "caution"
                    ? "bg-amber-950/20 border-amber-800"
                    : "bg-emerald-950/20 border-emerald-800"
                }`}
              >
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">
                      {riskVerdict.risk_verdict === "block"
                        ? "🚫"
                        : riskVerdict.risk_verdict === "caution"
                        ? "⚠️"
                        : "✅"}
                    </span>
                    <div>
                      <h3
                        className={`text-base font-bold capitalize ${
                          riskVerdict.risk_verdict === "block"
                            ? "text-rose-400"
                            : riskVerdict.risk_verdict === "caution"
                            ? "text-amber-400"
                            : "text-emerald-400"
                        }`}
                      >
                        Verdict: {riskVerdict.risk_verdict.toUpperCase()} ({riskVerdict.approval_tier})
                      </h3>
                      <p className="text-xs text-slate-300 mt-0.5">{riskVerdict.reason}</p>
                    </div>
                  </div>

                  <span
                    className={`text-xs font-bold px-3 py-1 rounded-full border ${getTierBadge(
                      riskVerdict.approval_tier
                    )}`}
                  >
                    {riskVerdict.approval_tier} Gate
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs mb-4">
                  <div className="p-3 rounded-lg bg-[#0e1515] border border-[#273636]">
                    <span className="text-slate-500 block text-[11px]">Blast Radius:</span>
                    <span className="font-semibold text-white capitalize">{riskVerdict.blast_radius}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-[#0e1515] border border-[#273636]">
                    <span className="text-slate-500 block text-[11px]">Reversible:</span>
                    <span className="font-semibold text-white">
                      {riskVerdict.is_reversible ? "Yes" : "No (Permanent)"}
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-[#0e1515] border border-[#273636]">
                    <span className="text-slate-500 block text-[11px]">Execution Blocked:</span>
                    <span className="font-semibold text-white">
                      {riskVerdict.blocking ? "Yes (Halted)" : "No (Allowed)"}
                    </span>
                  </div>
                </div>

                {riskVerdict.warning_to_user && (
                  <div className="p-3 rounded-lg bg-black/40 border border-[#273636] text-xs text-amber-200 mb-3">
                    <strong>User Warning:</strong> {riskVerdict.warning_to_user}
                  </div>
                )}

                {riskVerdict.narrower_alternative && (
                  <div className="p-3 rounded-lg bg-black/40 border border-[#273636] text-xs text-teal-200">
                    <strong>Recommended Narrower Alternative:</strong> {riskVerdict.narrower_alternative}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: COMPLIANCE & EXPORT */}
        {/* ========================================================================= */}
        {activeTab === "compliance" && (
          <div className="space-y-6 max-w-4xl">
            {/* Immutability Guarantee Banner */}
            <div className="p-5 rounded-xl bg-emerald-950/20 border border-emerald-800/40 space-y-3">
              <h2 className="text-sm font-semibold text-emerald-400 flex items-center gap-2">
                <span>📜</span> Immutability & Retention Policy (§10.12)
              </h2>
              <p className="text-xs text-[#95a8a8] leading-relaxed">
                All autonomous agent actions, tool calls, and risk gate verdicts are saved into an append-only audit ledger with 1-year retention. Mutation or deletion requests on audit entries are strictly prohibited and rejected by the API protocol to ensure verifiable compliance.
              </p>
            </div>

            {/* GDPR Export Card */}
            <div className="p-5 rounded-xl bg-[#141d1d] border border-[#273636] space-y-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>📥</span> GDPR & CCPA Compliance Archive Export
              </h2>
              <p className="text-xs text-[#95a8a8] leading-relaxed">
                Download your full autonomous activity audit history in a standardized portable JSON package. Includes trace IDs, tool parameters, execution latency, approval tiers, and risk verdicts.
              </p>
              <button
                type="button"
                disabled={exporting}
                onClick={handleExportArchive}
                className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 inline-flex items-center gap-2 shadow-sm"
              >
                {exporting ? "Generating Archive..." : "Download Audit Archive (JSON)"}
              </button>
              {exportSuccess && (
                <p className="text-xs text-emerald-400 mt-2">✓ {exportSuccess}</p>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
