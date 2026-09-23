"use client";

import React, { useState, useEffect, useCallback } from "react";

interface SourceItem {
  index: number;
  title: string;
  url: string;
  snippet?: string;
  score?: number;
}

interface ResearchReportItem {
  id: string;
  user_id?: string;
  title: string;
  query: string;
  summary: string;
  findings: string[];
  sources: SourceItem[];
  confidence: "high" | "medium" | "low" | string;
  depth: "quick" | "deep" | "academic" | string;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

interface DeepResearchResponse {
  report_id?: string | null;
  title: string;
  query: string;
  summary: string;
  sub_queries: string[];
  findings: string[];
  sources: SourceItem[];
  citations: string[];
  confidence: string;
  depth: string;
}

interface WebFetchResponse {
  url: string;
  title: string;
  content: string;
  word_count: number;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

const PRESET_TOPICS = [
  "DeepSeek R1 reasoning architecture vs OpenAI o3 methods",
  "PostgreSQL vs ClickHouse for high-throughput analytics",
  "Commercial fusion energy breakthroughs and pilot plants 2026",
  "Solid-state battery commercialization timeline and benchmarks",
];

export default function ResearchPage() {
  const [activeTab, setActiveTab] = useState<"deep_research" | "saved_reports" | "url_fetch">("deep_research");
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Deep research launcher state
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<"quick" | "deep" | "academic">("deep");
  const [autoSave, setAutoSave] = useState(true);
  const [customTags, setCustomTags] = useState("");
  const [isResearching, setIsResearching] = useState(false);
  const [researchStage, setResearchStage] = useState("");
  const [activeReport, setActiveReport] = useState<ResearchReportItem | DeepResearchResponse | null>(null);

  // Saved reports library state
  const [savedReports, setSavedReports] = useState<ResearchReportItem[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  // URL fetcher state
  const [fetchUrl, setFetchUrl] = useState("");
  const [isFetchingUrl, setIsFetchingUrl] = useState(false);
  const [urlFetchResult, setUrlFetchResult] = useState<WebFetchResponse | null>(null);

  // Status feedback
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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

  const loadReports = useCallback(async () => {
    if (!accessToken) return;
    setLoadingReports(true);
    setErrorBanner(null);
    try {
      const res = await fetch(`${API_BASE}/research`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSavedReports(data.reports || []);
      } else {
        setErrorBanner("Could not sync research reports from the server.");
      }
    } catch {
      setErrorBanner("Unable to connect to the research service. Check backend connection.");
    } finally {
      setLoadingReports(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (accessToken && activeTab === "saved_reports") {
      void loadReports();
    }
  }, [accessToken, activeTab, loadReports]);

  // Launch Deep Research
  const handleLaunchResearch = async (searchQuery?: string) => {
    const targetQuery = searchQuery || query;
    if (!targetQuery.trim() || isResearching) return;

    setIsResearching(true);
    setErrorBanner(null);
    setActiveReport(null);

    setResearchStage("Decomposing query into sub-queries...");
    const t1 = setTimeout(() => setResearchStage("Searching multi-engine live web sources..."), 1500);
    const t2 = setTimeout(() => setResearchStage("Extracting primary source excerpts & evidence..."), 3500);
    const t3 = setTimeout(() => setResearchStage("Synthesizing cross-source claims & citations..."), 6000);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const tagsList = customTags
        .split(",")
        .map((t) => t.trim().toLowerCase().replace(/^#/, ""))
        .filter(Boolean);

      const res = await fetch(`${API_BASE}/research/deep-research`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          query: targetQuery.trim(),
          depth,
          save_report: autoSave,
          tags: tagsList.length ? tagsList : undefined,
        }),
      });

      if (!res.ok) throw new Error("Deep research synthesis failed.");
      const data: DeepResearchResponse = await res.json();
      setActiveReport(data);
      showNotice("Research investigation synthesized successfully!");
      if (autoSave && accessToken) {
        void loadReports();
      }
    } catch (err) {
      showNotice((err as Error).message || "Investigation failed.");
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      setIsResearching(false);
      setResearchStage("");
    }
  };

  // URL Text Extractor
  const handleFetchUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fetchUrl.trim() || isFetchingUrl) return;

    setIsFetchingUrl(true);
    setUrlFetchResult(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(`${API_BASE}/research/fetch-url`, {
        method: "POST",
        headers,
        body: JSON.stringify({ url: fetchUrl.trim() }),
      });

      if (!res.ok) throw new Error("Failed to extract content from URL.");
      const data: WebFetchResponse = await res.json();
      setUrlFetchResult(data);
      showNotice(`Extracted ${data.word_count} words from source.`);
    } catch (err) {
      showNotice((err as Error).message || "URL extraction failed.");
    } finally {
      setIsFetchingUrl(false);
    }
  };

  // Delete saved report with optimistic rollback
  const handleDeleteReport = async (reportId: string) => {
    if (!accessToken) return;
    const prev = [...savedReports];
    setSavedReports((curr) => curr.filter((r) => r.id !== reportId));
    if (activeReport && "id" in activeReport && activeReport.id === reportId) {
      setActiveReport(null);
    }

    try {
      const res = await fetch(`${API_BASE}/research/${reportId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error("Server error deleting report");
      showNotice("🗑️ Report removed from library.");
    } catch {
      setSavedReports(prev);
      showNotice("Failed to delete report. Changes rolled back.");
    }
  };

  const handleCopyReport = (report: ResearchReportItem | DeepResearchResponse) => {
    const md = [
      `# ${report.title}`,
      `**Query:** ${report.query}`,
      `**Confidence:** ${report.confidence.toUpperCase()} | **Depth:** ${report.depth.toUpperCase()}`,
      "",
      "## Executive Summary",
      report.summary,
      "",
      "## Key Findings",
      ...(report.findings || []).map((f) => `- ${f}`),
      "",
      "## Citations & Sources",
      ...(report.sources || []).map((s) => `[${s.index}] ${s.title}: ${s.url}`),
    ].join("\n");

    if (typeof navigator !== "undefined") {
      navigator.clipboard.writeText(md);
      showNotice("📋 Markdown report copied to clipboard.");
    }
  };

  const filteredReports = savedReports.filter((r) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      r.title.toLowerCase().includes(q) ||
      r.query.toLowerCase().includes(q) ||
      r.summary.toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-[#f8faf9]">
      {/* Top Header */}
      <header className="px-6 py-4 bg-white border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 text-lg font-bold">
            🔬
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Autonomous Deep Research Hub</h1>
            <p className="text-xs text-slate-500">
              {isResearching
                ? "Synthesizing deep investigation..."
                : `${savedReports.length} reports in library · Live multi-engine search`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {activeReport && (
            <button
              onClick={() => handleCopyReport(activeReport)}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-sm transition-all"
            >
              📋 Copy Markdown
            </button>
          )}
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
              onClick={() => void loadReports()}
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
            <span>You are in guest preview mode. Sign in to save research dossiers, track investigation history, and sync sources across devices.</span>
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-200 pb-3">
          <button
            onClick={() => setActiveTab("deep_research")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "deep_research"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            ✨ Deep Research
          </button>
          <button
            onClick={() => {
              setActiveTab("saved_reports");
              void loadReports();
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "saved_reports"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <span>📚 Saved Reports</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200/80 text-slate-700">
              {savedReports.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab("url_fetch")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "url_fetch"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            🔗 Live URL Extractor
          </button>
        </div>

        {/* TAB 1: DEEP RESEARCH */}
        {activeTab === "deep_research" && (
          <div className="space-y-5 max-w-4xl">
            {/* Launcher Card */}
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
              <h2 className="text-sm font-bold text-slate-900">Launch Autonomous Investigation</h2>

              {/* Preset Chips */}
              <div className="flex flex-wrap gap-2">
                {PRESET_TOPICS.map((topic, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setQuery(topic);
                      void handleLaunchResearch(topic);
                    }}
                    className="text-[11px] px-2.5 py-1 bg-slate-50 hover:bg-teal-50 hover:border-teal-200 hover:text-teal-800 text-slate-600 border border-slate-200 rounded-lg transition-all text-left"
                  >
                    💡 {topic}
                  </button>
                ))}
              </div>

              {/* Query Input */}
              <div className="space-y-1">
                <input
                  type="text"
                  placeholder="Enter research query, company, technical comparison, or market question..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void handleLaunchResearch();
                    }
                  }}
                  className="w-full text-xs px-3.5 py-2.5 border border-slate-200 rounded-xl focus:outline-none focus:border-[#0d9488]"
                />
              </div>

              {/* Controls Grid */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <div className="flex items-center gap-3">
                  {/* Depth selector */}
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-slate-500 font-semibold">Depth:</span>
                    <select
                      value={depth}
                      onChange={(e) => setDepth(e.target.value as any)}
                      className="text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:border-[#0d9488]"
                    >
                      <option value="quick">Quick Brief</option>
                      <option value="deep">Comprehensive Deep</option>
                      <option value="academic">Academic Rigor</option>
                    </select>
                  </div>

                  {/* Auto save checkbox */}
                  <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoSave}
                      onChange={(e) => setAutoSave(e.target.checked)}
                      className="rounded border-slate-300 text-[#0d9488] focus:ring-0"
                    />
                    <span>Auto-save to library</span>
                  </label>
                </div>

                <button
                  type="button"
                  onClick={() => void handleLaunchResearch()}
                  disabled={isResearching || !query.trim()}
                  className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-sm transition-all flex items-center gap-2"
                >
                  {isResearching ? (
                    <>
                      <span className="w-2 h-2 rounded-full bg-white animate-ping" />
                      <span>Investigating...</span>
                    </>
                  ) : (
                    <span>🚀 Launch Deep Research</span>
                  )}
                </button>
              </div>

              {/* Research Stage Progress */}
              {isResearching && (
                <div className="p-3 bg-teal-50 border border-teal-200 rounded-xl text-xs text-teal-800 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#0d9488] animate-pulse" />
                  <span className="font-semibold">{researchStage || "Analyzing query..."}</span>
                </div>
              )}
            </div>

            {/* Active Report Output */}
            {activeReport && (
              <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
                <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-4">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">{activeReport.title}</h2>
                    <p className="text-xs text-slate-500 mt-0.5">Query: &ldquo;{activeReport.query}&rdquo;</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-teal-100 text-teal-800">
                      {activeReport.confidence} Confidence
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700">
                      {activeReport.depth} Depth
                    </span>
                  </div>
                </div>

                {/* Executive Summary */}
                <div className="space-y-1.5">
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Executive Summary</h3>
                  <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 leading-relaxed">
                    {activeReport.summary}
                  </div>
                </div>

                {/* Key Findings */}
                {activeReport.findings && activeReport.findings.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Key Findings</h3>
                    <ul className="space-y-1.5">
                      {activeReport.findings.map((f, i) => (
                        <li key={i} className="text-xs text-slate-700 flex items-start gap-2">
                          <span className="text-[#0d9488] font-bold">✓</span>
                          <span className="leading-relaxed">{f}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Verified Citations & Sources */}
                {activeReport.sources && activeReport.sources.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                      Verified Citations &amp; Sources ({activeReport.sources.length})
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {activeReport.sources.map((s) => (
                        <a
                          key={s.index}
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-slate-50 hover:border-teal-300 transition-all flex flex-col justify-between"
                        >
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="text-[10px] font-bold px-1.5 py-0.2 bg-teal-100 text-teal-800 rounded">
                                [{s.index}]
                              </span>
                              <span className="text-xs font-bold text-slate-800 truncate">{s.title}</span>
                            </div>
                            {s.snippet && (
                              <p className="text-[11px] text-slate-500 line-clamp-2 mt-1 leading-relaxed">
                                {s.snippet}
                              </p>
                            )}
                          </div>
                          <span className="text-[10px] text-teal-700 truncate mt-2 font-mono">
                            {s.url} ↗
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: SAVED REPORTS */}
        {activeTab === "saved_reports" && (
          <div className="max-w-4xl space-y-4">
            <div className="flex items-center gap-2">
              <input
                type="search"
                placeholder="Search saved research dossiers by title, query, or findings..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="flex-1 text-xs px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl focus:outline-none focus:border-[#0d9488] shadow-sm"
              />
              <button
                onClick={() => void loadReports()}
                className="px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-sm"
              >
                🔄 Refresh
              </button>
            </div>

            {loadingReports ? (
              <p className="text-xs text-slate-500">Loading saved reports...</p>
            ) : filteredReports.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
                <div className="text-4xl mb-2">📚</div>
                <h3 className="text-sm font-bold text-slate-800">
                  {searchFilter ? "No matching reports found" : "No Saved Research Reports"}
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  {searchFilter
                    ? `No dossiers matched "${searchFilter}". Try a different keyword.`
                    : "Your investigation library is empty. Launch a Deep Research investigation to save dossiers here."}
                </p>
                {!searchFilter && (
                  <button
                    onClick={() => setActiveTab("deep_research")}
                    className="mt-3.5 px-4 py-2 bg-[#0d9488] text-white rounded-lg text-xs font-semibold hover:bg-[#0f766e]"
                  >
                    ✨ Launch Deep Research
                  </button>
                )}
              </div>
            ) : (
              <div className="grid gap-3.5">
                {filteredReports.map((r) => (
                  <div
                    key={r.id}
                    className="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h4 className="text-sm font-bold text-slate-900">{r.title}</h4>
                        <p className="text-xs text-slate-500 mt-0.5">Query: {r.query}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-teal-100 text-teal-800">
                            {r.confidence}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700">
                            {r.depth}
                          </span>
                          <span className="text-[11px] text-slate-400">
                            {r.findings?.length || 0} findings · {r.sources?.length || 0} citations
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => handleCopyReport(r)}
                          className="px-2.5 py-1 rounded border border-slate-200 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          📋 Copy
                        </button>
                        <button
                          onClick={() => void handleDeleteReport(r.id)}
                          className="px-2.5 py-1 rounded border border-slate-200 text-[11px] font-semibold text-rose-600 hover:bg-rose-50"
                        >
                          Delete
                        </button>
                      </div>
                    </div>

                    <p className="text-xs text-slate-600 line-clamp-3 leading-relaxed bg-slate-50 p-3 rounded-xl border border-slate-100">
                      {r.summary}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: LIVE URL EXTRACTOR */}
        {activeTab === "url_fetch" && (
          <div className="max-w-3xl space-y-4">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900">Live Web Page Content Extractor</h3>
              <p className="text-xs text-slate-500">
                Extract readable text, headings, and clean word counts directly from any public web page.
              </p>

              <form onSubmit={handleFetchUrl} className="flex gap-2">
                <input
                  type="url"
                  required
                  placeholder="https://example.com/article"
                  value={fetchUrl}
                  onChange={(e) => setFetchUrl(e.target.value)}
                  className="flex-1 text-xs px-3.5 py-2.5 border border-slate-200 rounded-xl focus:outline-none focus:border-[#0d9488]"
                />
                <button
                  type="submit"
                  disabled={isFetchingUrl || !fetchUrl.trim()}
                  className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
                >
                  {isFetchingUrl ? "Extracting..." : "Extract Text"}
                </button>
              </form>
            </div>

            {urlFetchResult && (
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h4 className="text-xs font-bold text-slate-900 truncate max-w-md">{urlFetchResult.title}</h4>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-teal-100 text-teal-800">
                    {urlFetchResult.word_count} words
                  </span>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl text-xs text-slate-700 max-h-80 overflow-y-auto leading-relaxed whitespace-pre-wrap font-mono">
                  {urlFetchResult.content}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
