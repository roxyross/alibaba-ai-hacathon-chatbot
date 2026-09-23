"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";

interface BrowserTaskItem {
  id: string;
  user_id?: string;
  title: string;
  url: string;
  status: "pending" | "running" | "completed" | "failed" | string;
  action_type: "navigate" | "extract" | "fill_form" | "screenshot" | "multi_step" | string;
  actions: Array<{ type: string; [key: string]: unknown }>;
  result_data?: {
    steps?: Array<{ step: number; action: string; status: string; details?: Record<string, unknown> }>;
    data?: {
      page_title?: string;
      content_preview?: string;
      tables?: Array<{ headers: string[]; rows: string[][] }>;
      links?: Array<{ text: string; href: string }>;
      headings?: Array<{ level: number; text: string }>;
      screenshot_url?: string;
    };
    [key: string]: unknown;
  };
  error_message?: string | null;
  requires_confirmation?: boolean;
  is_sensitive?: boolean;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

interface InspectResponse {
  url: string;
  title?: string | null;
  final_url?: string | null;
  status: string;
  content_preview: string;
  headings: Array<{ level: number; text: string }>;
  links: Array<{ text: string; href: string }>;
  forms: Array<{ action: string; method: string; fields: string[] }>;
  meta: Record<string, string>;
  error?: string | null;
}

interface ExtractResponse {
  url: string;
  title?: string | null;
  tables: Array<{ table_index?: number; headers: string[]; rows: string[][]; total_rows?: number }>;
  links: Array<{ text: string; href: string }>;
  headings: Array<{ level: number; text: string }>;
  text_excerpt: string;
  status: string;
  error?: string | null;
}

interface ScreenshotResponse {
  url: string;
  title?: string | null;
  screenshot_url: string;
  width: number;
  height: number;
  status: string;
  timestamp: string;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

const PRESET_URLS = [
  "https://news.ycombinator.com",
  "https://en.wikipedia.org/wiki/Artificial_intelligence",
  "https://fastapi.tiangolo.com",
  "https://github.com/trending",
];

export default function BrowserStudioPage() {
  const [activeTab, setActiveTab] = useState<"inspector" | "flows" | "tasks">("inspector");
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Inspector state
  const [targetUrl, setTargetUrl] = useState("");
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectData, setInspectData] = useState<InspectResponse | null>(null);
  const [screenshotData, setScreenshotData] = useState<ScreenshotResponse | null>(null);
  const [inspectorSubTab, setInspectorSubTab] = useState<"preview" | "headings" | "tables" | "links" | "forms" | "screenshot">("preview");
  const [linkSearchQuery, setLinkSearchQuery] = useState("");

  // Flow runner state
  const [flowUrl, setFlowUrl] = useState("");
  const [flowTitle, setFlowTitle] = useState("");
  const [flowExtractType, setFlowExtractType] = useState<"all" | "tables" | "links">("all");
  const [flowTags, setFlowTags] = useState("automation, extraction");
  const [isRunningFlow, setIsRunningFlow] = useState(false);
  const [flowResult, setFlowResult] = useState<Record<string, unknown> | null>(null);
  const [flowError, setFlowError] = useState<string | null>(null);

  // Task logs state
  const [tasks, setTasks] = useState<BrowserTaskItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "completed" | "pending" | "failed">("all");
  const [selectedTask, setSelectedTask] = useState<BrowserTaskItem | null>(null);

  // Alerts & Notifications
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const showNotice = (msg: string) => {
    setNotice(msg);
    setTimeout(() => setNotice((curr) => (curr === msg ? null : curr)), 4000);
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const tok = localStorage.getItem("roxy_access_token") || localStorage.getItem("access_token");
      setAccessToken(tok);
    }
  }, []);

  // Fetch saved tasks
  const loadTasks = useCallback(async () => {
    if (!accessToken) return;
    setTasksLoading(true);
    setFetchError(null);
    try {
      const res = await fetch(`${API_BASE}/browser/tasks?limit=50`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
      } else {
        setFetchError("Unable to fetch browser task records from the server.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Connection failed while loading browser tasks.");
    } finally {
      setTasksLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (accessToken) {
      loadTasks();
    }
  }, [accessToken, loadTasks]);

  // Handle URL Inspection
  const handleInspect = async (urlOverride?: string) => {
    const url = (urlOverride || targetUrl).trim();
    if (!url) return;
    setIsInspecting(true);
    setFetchError(null);
    setInspectData(null);
    setScreenshotData(null);

    try {
      const res = await fetch(`${API_BASE}/browser/navigate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({ url, timeout_seconds: 20 }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setInspectData(data);
      showNotice("DOM inspected successfully!");

      // Also trigger screenshot asynchronously
      fetch(`${API_BASE}/browser/screenshot`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({ url, width: 1280, height: 800 }),
      })
        .then(async (sRes) => {
          if (sRes.ok) {
            const sData = await sRes.json();
            setScreenshotData(sData);
          }
        })
        .catch(() => {});
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Page inspection failed.");
    } finally {
      setIsInspecting(false);
    }
  };

  // Handle Manual Screenshot Capture
  const handleCaptureScreenshot = async () => {
    const url = (inspectData?.url || targetUrl).trim();
    if (!url) return;
    try {
      const res = await fetch(`${API_BASE}/browser/screenshot`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({ url, width: 1280, height: 800 }),
      });
      if (res.ok) {
        const sData = await res.json();
        setScreenshotData(sData);
        showNotice("Visual snapshot captured!");
      }
    } catch (err) {
      console.error("Screenshot error:", err);
    }
  };

  // Handle Flow Execution
  const handleRunFlow = async () => {
    const url = flowUrl.trim();
    if (!url) return;
    setIsRunningFlow(true);
    setFlowError(null);
    setFlowResult(null);

    const actions = [
      { type: "navigate" },
      { type: "extract", extract_type: flowExtractType },
      { type: "wait", seconds: 0.5 },
      { type: "screenshot" },
    ];

    const tagList = flowTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      const res = await fetch(`${API_BASE}/browser/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({
          url,
          title: flowTitle.trim() || undefined,
          actions,
          save_task: true,
          tags: tagList,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errJson.detail || `HTTP ${res.status}`);
      }

      const resData = await res.json();
      setFlowResult(resData);
      showNotice("Browser automation pipeline executed!");
      if (accessToken) loadTasks();
    } catch (err: unknown) {
      setFlowError(err instanceof Error ? err.message : "Pipeline execution failed.");
    } finally {
      setIsRunningFlow(false);
    }
  };

  // Handle Task Deletion with Optimistic Rollback
  const handleDeleteTask = async (taskId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const prevTasks = [...tasks];
    const prevSelected = selectedTask;
    setTasks((curr) => curr.filter((t) => t.id !== taskId));
    if (selectedTask?.id === taskId) setSelectedTask(null);

    try {
      const res = await fetch(`${API_BASE}/browser/tasks/${taskId}`, {
        method: "DELETE",
        headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      showNotice("Browser task record deleted.");
    } catch (err) {
      console.error("Delete failed, rolling back:", err);
      setTasks(prevTasks);
      setSelectedTask(prevSelected);
      setFetchError("Failed to delete task. Changes rolled back.");
    }
  };

  // Filter tasks
  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      const matchSearch =
        !searchQuery ||
        t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.url.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (t.tags && t.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase())));
      const matchStatus = statusFilter === "all" || t.status === statusFilter;
      return matchSearch && matchStatus;
    });
  }, [tasks, searchQuery, statusFilter]);

  // Filter links in inspector
  const filteredLinks = useMemo(() => {
    if (!inspectData?.links) return [];
    if (!linkSearchQuery.trim()) return inspectData.links;
    const q = linkSearchQuery.toLowerCase();
    return inspectData.links.filter(
      (l) => l.text.toLowerCase().includes(q) || l.href.toLowerCase().includes(q)
    );
  }, [inspectData?.links, linkSearchQuery]);

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 pb-16">
      {/* Top Header */}
      <div className="bg-white border-b border-slate-200 sticky top-16 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-2xl p-2 rounded-xl bg-teal-50 border border-teal-200">🌐</span>
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
                    Browser Automation Studio
                    <span className="text-xs px-2 py-0.5 rounded-full bg-teal-100 text-[#0d9488] font-semibold">
                      Headless DOM
                    </span>
                  </h1>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Autonomous web navigation, structured table extraction, DOM inspection, and visual snapshotting
                  </p>
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200 text-xs font-medium self-start sm:self-auto">
              <button
                onClick={() => setActiveTab("inspector")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "inspector"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>🔍</span>
                <span>Live Inspector</span>
              </button>
              <button
                onClick={() => setActiveTab("flows")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "flows"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>⚡</span>
                <span>Automation Flows</span>
              </button>
              <button
                onClick={() => setActiveTab("tasks")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "tasks"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>📋</span>
                <span>Task Logs</span>
                {tasks.length > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full bg-teal-100 text-[#0d9488] text-[10px]">
                    {tasks.length}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6">
        {/* Guest Auth Notice */}
        {!accessToken && (
          <div className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-base">🛡️</span>
              <span>
                <strong>Guest Mode:</strong> You can inspect web pages and run one-shot headless extractions, but saving automated tasks and cloud history requires signing in.
              </span>
            </div>
            <a
              href="/"
              className="px-3 py-1 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 transition-colors whitespace-nowrap"
            >
              Sign In
            </a>
          </div>
        )}

        {/* Global Error Banner */}
        {fetchError && (
          <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-base">⚠️</span>
              <span>{fetchError}</span>
            </div>
            <button
              onClick={() => {
                setFetchError(null);
                if (activeTab === "tasks") loadTasks();
              }}
              className="px-2.5 py-1 bg-red-100 hover:bg-red-200 text-red-800 rounded-md font-medium transition-colors"
            >
              ↻ Retry Connection
            </button>
          </div>
        )}

        {/* Notice alert */}
        {notice && (
          <div className="mb-6 p-3 rounded-xl bg-teal-50 border border-teal-200 text-[#0d9488] text-xs flex items-center gap-2">
            <span>✨</span>
            <span>{notice}</span>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 1: LIVE INSPECTOR                                                    */}
        {/* ========================================================================= */}
        {activeTab === "inspector" && (
          <div className="space-y-6">
            {/* Search Input Box */}
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
              <label className="block text-xs font-semibold text-slate-700 mb-2">
                Target Website URL
              </label>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleInspect();
                }}
                className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3"
              >
                <div className="relative flex-1">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">🌐</span>
                  <input
                    type="url"
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                    placeholder="https://example.com or any public web address..."
                    required
                    className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30 focus:border-[#0d9488]"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isInspecting || !targetUrl.trim()}
                  className="px-6 py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl text-sm font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isInspecting ? (
                    <>
                      <span className="inline-block animate-spin">↻</span>
                      <span>Inspecting DOM…</span>
                    </>
                  ) : (
                    <>
                      <span>🔍</span>
                      <span>Inspect Page</span>
                    </>
                  )}
                </button>
              </form>

              {/* Preset Targets */}
              <div className="mt-4 flex items-center gap-2 flex-wrap text-xs">
                <span className="text-slate-400 font-medium">Quick Targets:</span>
                {PRESET_URLS.map((url) => (
                  <button
                    key={url}
                    type="button"
                    onClick={() => {
                      setTargetUrl(url);
                      handleInspect(url);
                    }}
                    className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors border border-slate-200"
                  >
                    {url.replace(/^https?:\/\//, "")}
                  </button>
                ))}
              </div>
            </div>

            {/* Inspection Results */}
            {inspectData ? (
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
                {/* Result Header Bar */}
                <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                      <span>{inspectData.title || "Target Webpage"}</span>
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800">
                        {inspectData.status.toUpperCase()}
                      </span>
                    </h2>
                    <a
                      href={inspectData.final_url || inspectData.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-[#0d9488] hover:underline mt-0.5 inline-flex items-center gap-1"
                    >
                      {inspectData.final_url || inspectData.url} ↗
                    </a>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleCopy(JSON.stringify(inspectData, null, 2), "inspect-json")}
                      className="px-3 py-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5"
                    >
                      <span>{copiedId === "inspect-json" ? "✓" : "📋"}</span>
                      <span>{copiedId === "inspect-json" ? "Copied" : "Copy JSON"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleCaptureScreenshot}
                      className="px-3 py-1.5 bg-teal-50 border border-teal-200 text-[#0d9488] hover:bg-teal-100 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5"
                    >
                      <span>📸</span>
                      <span>Capture Screenshot</span>
                    </button>
                  </div>
                </div>

                {/* Sub-Tabs */}
                <div className="flex items-center border-b border-slate-200 bg-slate-50 px-6 gap-6 text-xs font-medium overflow-x-auto">
                  <button
                    onClick={() => setInspectorSubTab("preview")}
                    className={`py-3 border-b-2 transition-all flex items-center gap-1.5 ${
                      inspectorSubTab === "preview"
                        ? "border-[#0d9488] text-[#0d9488] font-bold"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    <span>📄</span>
                    <span>Summary & Content</span>
                  </button>
                  <button
                    onClick={() => setInspectorSubTab("headings")}
                    className={`py-3 border-b-2 transition-all flex items-center gap-1.5 ${
                      inspectorSubTab === "headings"
                        ? "border-[#0d9488] text-[#0d9488] font-bold"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    <span>📑</span>
                    <span>Headings ({inspectData.headings.length})</span>
                  </button>
                  <button
                    onClick={() => setInspectorSubTab("links")}
                    className={`py-3 border-b-2 transition-all flex items-center gap-1.5 ${
                      inspectorSubTab === "links"
                        ? "border-[#0d9488] text-[#0d9488] font-bold"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    <span>🔗</span>
                    <span>Links ({inspectData.links.length})</span>
                  </button>
                  <button
                    onClick={() => setInspectorSubTab("forms")}
                    className={`py-3 border-b-2 transition-all flex items-center gap-1.5 ${
                      inspectorSubTab === "forms"
                        ? "border-[#0d9488] text-[#0d9488] font-bold"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    <span>📝</span>
                    <span>Forms ({inspectData.forms.length})</span>
                  </button>
                  <button
                    onClick={() => setInspectorSubTab("screenshot")}
                    className={`py-3 border-b-2 transition-all flex items-center gap-1.5 ${
                      inspectorSubTab === "screenshot"
                        ? "border-[#0d9488] text-[#0d9488] font-bold"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    <span>📸</span>
                    <span>Visual Snapshot</span>
                  </button>
                </div>

                {/* Sub-Tab Contents */}
                <div className="p-6">
                  {inspectorSubTab === "preview" && (
                    <div className="space-y-4">
                      {inspectData.meta && Object.keys(inspectData.meta).length > 0 && (
                        <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                            Page Meta Tags
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                            {Object.entries(inspectData.meta).map(([k, v]) => (
                              <div key={k} className="flex gap-2">
                                <span className="font-semibold text-slate-600">{k}:</span>
                                <span className="text-slate-800 truncate" title={v}>
                                  {v}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div>
                        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                          Main Content Text Excerpt
                        </h4>
                        <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-mono max-h-96 overflow-y-auto">
                          {inspectData.content_preview || "No preview text available."}
                        </div>
                      </div>
                    </div>
                  )}

                  {inspectorSubTab === "headings" && (
                    <div className="space-y-2">
                      {inspectData.headings.length === 0 ? (
                        <p className="text-xs text-slate-500 py-4">No headings found on this page.</p>
                      ) : (
                        inspectData.headings.map((h, i) => (
                          <div
                            key={i}
                            className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center gap-3 text-xs"
                          >
                            <span className="px-2 py-0.5 rounded font-mono font-bold bg-teal-100 text-[#0d9488]">
                              H{h.level}
                            </span>
                            <span className="text-slate-800 font-medium">{h.text}</span>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {inspectorSubTab === "links" && (
                    <div className="space-y-4">
                      <div className="flex items-center gap-3">
                        <input
                          type="text"
                          value={linkSearchQuery}
                          onChange={(e) => setLinkSearchQuery(e.target.value)}
                          placeholder="Filter hyperlinks by anchor text or URL..."
                          className="w-full sm:w-80 px-3.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                        />
                        <span className="text-xs text-slate-400">
                          Showing {filteredLinks.length} of {inspectData.links.length}
                        </span>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-96 overflow-y-auto">
                        {filteredLinks.map((l, i) => (
                          <div
                            key={i}
                            className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs flex flex-col justify-between gap-1"
                          >
                            <span className="font-semibold text-slate-800 truncate" title={l.text}>
                              {l.text || "Anchor link"}
                            </span>
                            <a
                              href={l.href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[#0d9488] hover:underline truncate"
                              title={l.href}
                            >
                              {l.href}
                            </a>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {inspectorSubTab === "forms" && (
                    <div className="space-y-3">
                      {inspectData.forms.length === 0 ? (
                        <p className="text-xs text-slate-500 py-4">No forms detected on this page.</p>
                      ) : (
                        inspectData.forms.map((f, i) => (
                          <div key={i} className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-slate-800">Action: {f.action || "(Current URL)"}</span>
                              <span className="px-2 py-0.5 rounded bg-slate-200 font-mono font-semibold text-slate-700">
                                {f.method.toUpperCase()}
                              </span>
                            </div>
                            <div className="text-slate-600">
                              <span className="font-semibold">Fields: </span>
                              {f.fields.join(", ") || "None"}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {inspectorSubTab === "screenshot" && (
                    <div className="space-y-4">
                      {screenshotData ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-xs text-slate-500">
                            <span>Viewport: {screenshotData.width} × {screenshotData.height}px</span>
                            <span>Captured: {new Date(screenshotData.timestamp).toLocaleTimeString()}</span>
                          </div>
                          <div className="rounded-xl border border-slate-200 overflow-hidden bg-slate-900 shadow-md">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={screenshotData.screenshot_url}
                              alt="Captured snapshot preview"
                              className="w-full object-cover"
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="py-12 text-center text-xs text-slate-500 space-y-3">
                          <p>No screenshot captured for this page yet.</p>
                          <button
                            type="button"
                            onClick={handleCaptureScreenshot}
                            className="px-4 py-2 bg-[#0d9488] text-white rounded-lg font-medium hover:bg-[#0f766e] transition-colors"
                          >
                            Capture Viewport Snapshot
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center">
                <span className="text-4xl block mb-3">🌐</span>
                <h3 className="text-base font-bold text-slate-800">Ready for Live Page Inspection</h3>
                <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                  Enter any public website URL above or select a preset target to parse page metadata, headings, tables, links, and forms.
                </p>
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: AUTOMATION FLOWS                                                  */}
        {/* ========================================================================= */}
        {activeTab === "flows" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Flow Builder */}
            <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
              <div>
                <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>⚡</span>
                  <span>Autonomous Pipeline Runner</span>
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Execute multi-step headless browser actions and record telemetry
                </p>
              </div>

              <div className="space-y-4 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">Target Web Address</label>
                  <input
                    type="url"
                    value={flowUrl}
                    onChange={(e) => setFlowUrl(e.target.value)}
                    placeholder="https://example.com/pricing"
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">Flow Name / Title</label>
                  <input
                    type="text"
                    value={flowTitle}
                    onChange={(e) => setFlowTitle(e.target.value)}
                    placeholder="e.g., Weekly SaaS Pricing Monitor"
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">DOM Extraction Scope</label>
                  <select
                    value={flowExtractType}
                    onChange={(e) => setFlowExtractType(e.target.value as "all" | "tables" | "links")}
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  >
                    <option value="all">Full Extraction (Tables + Links + Headings)</option>
                    <option value="tables">Data Tables Only</option>
                    <option value="links">Hyperlinks Only</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">Tags (Comma-Separated)</label>
                  <input
                    type="text"
                    value={flowTags}
                    onChange={(e) => setFlowTags(e.target.value)}
                    placeholder="market, pricing, weekly"
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  />
                </div>

                {/* Pipeline visualizer */}
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                  <span className="font-bold text-slate-700">Scheduled Execution Pipeline:</span>
                  <div className="flex items-center gap-1.5 flex-wrap text-[11px] font-medium text-slate-600">
                    <span className="px-2 py-1 bg-white border border-slate-200 rounded-md">1. Navigate</span>
                    <span>→</span>
                    <span className="px-2 py-1 bg-white border border-slate-200 rounded-md">
                      2. Extract {flowExtractType.toUpperCase()}
                    </span>
                    <span>→</span>
                    <span className="px-2 py-1 bg-white border border-slate-200 rounded-md">3. Settle 0.5s</span>
                    <span>→</span>
                    <span className="px-2 py-1 bg-white border border-slate-200 rounded-md">4. Visual Snapshot</span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleRunFlow}
                  disabled={isRunningFlow || !flowUrl.trim()}
                  className="w-full py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isRunningFlow ? (
                    <>
                      <span className="inline-block animate-spin">↻</span>
                      <span>Running Pipeline Flow…</span>
                    </>
                  ) : (
                    <>
                      <span>▶</span>
                      <span>Execute Web Flow</span>
                    </>
                  )}
                </button>

                {flowError && (
                  <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl">
                    {flowError}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Flow Output Results */}
            <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200 p-6 shadow-sm flex flex-col">
              <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <span>📊</span>
                  <span>Execution Output</span>
                </h3>
                {flowResult && (
                  <button
                    type="button"
                    onClick={() => handleCopy(JSON.stringify(flowResult, null, 2), "flow-output")}
                    className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                  >
                    {copiedId === "flow-output" ? "✓ Copied" : "📋 Copy JSON"}
                  </button>
                )}
              </div>

              <div className="flex-1 mt-4">
                {flowResult ? (
                  <pre className="p-4 bg-slate-900 text-teal-400 font-mono text-xs rounded-xl overflow-y-auto max-h-[500px] leading-relaxed">
                    {JSON.stringify(flowResult, null, 2)}
                  </pre>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center py-16 text-slate-400 text-xs text-center">
                    <span className="text-3xl mb-2">⚡</span>
                    <p>No pipeline has been executed yet.</p>
                    <p className="text-[11px] text-slate-400 mt-1">Configure actions on the left and trigger run.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: TASK LOGS & HISTORY                                               */}
        {/* ========================================================================= */}
        {activeTab === "tasks" && (
          <div className="space-y-6">
            {/* Toolbar */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="relative w-full sm:w-80">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search tasks by title, url, tags..."
                  className="w-full pl-9 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                />
              </div>

              <div className="flex items-center gap-1.5 self-start sm:self-auto">
                {(["all", "completed", "pending", "failed"] as const).map((st) => (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                      statusFilter === st
                        ? "bg-[#0d9488] text-white shadow-sm"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {st.toUpperCase()}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={loadTasks}
                  className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors ml-1"
                  title="Refresh tasks"
                >
                  ↻
                </button>
              </div>
            </div>

            {/* Tasks List */}
            {tasksLoading ? (
              <div className="py-20 text-center text-xs text-slate-500">
                <span className="inline-block animate-spin text-xl mb-2">↻</span>
                <p>Loading browser automation tasks…</p>
              </div>
            ) : filteredTasks.length === 0 ? (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center">
                <span className="text-4xl block mb-2">📋</span>
                <h3 className="text-base font-bold text-slate-800">No Browser Tasks Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                  {searchQuery || statusFilter !== "all"
                    ? "No tasks match your active filters."
                    : "You have no saved browser automation tasks yet. Run an automation flow to persist task logs."}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredTasks.map((t) => (
                  <div
                    key={t.id}
                    onClick={() => setSelectedTask(t)}
                    className={`bg-white rounded-2xl border p-4 cursor-pointer transition-all hover:shadow-md flex flex-col justify-between ${
                      selectedTask?.id === t.id
                        ? "border-[#0d9488] ring-2 ring-[#0d9488]/20"
                        : "border-slate-200"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            t.status === "completed"
                              ? "bg-emerald-100 text-emerald-800"
                              : t.status === "failed"
                              ? "bg-red-100 text-red-800"
                              : "bg-amber-100 text-amber-800"
                          }`}
                        >
                          {t.status.toUpperCase()}
                        </span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">
                          {t.action_type}
                        </span>
                      </div>

                      <h4 className="text-xs font-bold text-slate-900 line-clamp-1 mb-1" title={t.title}>
                        {t.title}
                      </h4>
                      <p className="text-[11px] text-slate-500 line-clamp-1 font-mono mb-2" title={t.url}>
                        {t.url}
                      </p>

                      {t.tags && t.tags.length > 0 && (
                        <div className="flex items-center gap-1 flex-wrap mb-3">
                          {t.tags.map((tag) => (
                            <span
                              key={tag}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600"
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
                      <span>{t.created_at ? new Date(t.created_at).toLocaleDateString() : "Recent"}</span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(JSON.stringify(t, null, 2), t.id);
                          }}
                          className="hover:text-slate-700 transition-colors"
                          title="Copy JSON"
                        >
                          {copiedId === t.id ? "✓" : "📋"}
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteTask(t.id, e)}
                          className="hover:text-red-600 transition-colors text-slate-400"
                          title="Delete Task"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Task Detail Modal */}
            {selectedTask && (
              <div
                className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                onClick={() => setSelectedTask(null)}
              >
                <div
                  className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-xl border border-slate-200 max-h-[85vh] flex flex-col"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                    <div>
                      <h3 className="text-base font-bold text-slate-900">{selectedTask.title}</h3>
                      <p className="text-xs text-slate-500 font-mono mt-0.5">{selectedTask.url}</p>
                    </div>
                    <button
                      onClick={() => setSelectedTask(null)}
                      className="p-1 text-slate-400 hover:text-slate-700 rounded-lg text-sm"
                    >
                      ✕
                    </button>
                  </div>

                  <div className="flex-1 overflow-y-auto py-4 space-y-4 text-xs">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-slate-50 rounded-xl">
                        <span className="font-semibold text-slate-500 block mb-1">Status</span>
                        <span className="font-bold text-slate-800">{selectedTask.status.toUpperCase()}</span>
                      </div>
                      <div className="p-3 bg-slate-50 rounded-xl">
                        <span className="font-semibold text-slate-500 block mb-1">Action Type</span>
                        <span className="font-bold text-slate-800">{selectedTask.action_type}</span>
                      </div>
                    </div>

                    <div>
                      <span className="font-semibold text-slate-700 block mb-2">Actions Pipeline:</span>
                      <pre className="p-3 bg-slate-900 text-teal-400 font-mono text-[11px] rounded-xl overflow-x-auto">
                        {JSON.stringify(selectedTask.actions, null, 2)}
                      </pre>
                    </div>

                    <div>
                      <span className="font-semibold text-slate-700 block mb-2">Result Data:</span>
                      <pre className="p-3 bg-slate-900 text-teal-400 font-mono text-[11px] rounded-xl overflow-y-auto max-h-60">
                        {JSON.stringify(selectedTask.result_data, null, 2)}
                      </pre>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => handleCopy(JSON.stringify(selectedTask, null, 2), "modal-copy")}
                      className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors"
                    >
                      {copiedId === "modal-copy" ? "✓ Copied" : "📋 Copy Full JSON"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedTask(null)}
                      className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl text-xs font-semibold transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
