"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";

interface CodeSnippetItem {
  id: string;
  user_id?: string;
  title: string;
  language: string;
  code: string;
  description?: string | null;
  tags?: string[];
  is_favorite: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

interface CodeExecutionItem {
  id?: string;
  language: string;
  status: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  execution_time_ms: number;
  created_at?: string | null;
}

interface CodeStatsItem {
  total_snippets: number;
  favorite_snippets: number;
  languages_count: Record<string, number>;
  total_executions: number;
  successful_executions: number;
  success_rate_percentage: number;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

const DEFAULT_TEMPLATES: Record<string, string> = {
  python: `# Welcome to ROXY Developer Studio!
def solve(n: int) -> int:
    """Calculate the sum of squares up to n."""
    return sum(i * i for i in range(1, n + 1))

if __name__ == "__main__":
    result = solve(10)
    print(f"Result for n=10: {result}")
`,
  javascript: `// JavaScript Playground
function fibonacci(n) {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

console.log("Fibonacci sequence (first 10):", Array.from({ length: 10 }, (_, i) => fibonacci(i)));
`,
  typescript: `// TypeScript Playground
interface User {
  id: string;
  name: string;
  role: "admin" | "engineer" | "guest";
}

const user: User = { id: "u-101", name: "Alice", role: "engineer" };
console.log("Active engineer profile:", JSON.stringify(user));
`,
  bash: `#!/usr/bin/env bash
echo "Host Operating System Architecture:"
uname -a 2>/dev/null || echo "Running in sandboxed environment"
echo "Active Date & Time: $(date)"
`,
  sql: `-- SQL Sandbox Query
SELECT 
  id,
  title,
  language,
  created_at
FROM code_snippets
ORDER BY created_at DESC
LIMIT 5;
`,
  json: `{
  "developer": "ROXY Agent",
  "version": "2.4.0",
  "environment": "sandboxed-execution",
  "capabilities": ["execute", "synthesize", "explain", "debug"]
}
`,
};

export default function CodingStudioPage() {
  const [activeTab, setActiveTab] = useState<"playground" | "ai" | "snippets">("playground");
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Stats
  const [stats, setStats] = useState<CodeStatsItem>({
    total_snippets: 0,
    favorite_snippets: 0,
    languages_count: {},
    total_executions: 0,
    successful_executions: 0,
    success_rate_percentage: 100.0,
  });

  // Playground State
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState(DEFAULT_TEMPLATES.python);
  const [stdinText, setStdinText] = useState("");
  const [showStdin, setShowStdin] = useState(false);
  const [runningCode, setRunningCode] = useState(false);
  const [lastExecution, setLastExecution] = useState<CodeExecutionItem | null>(null);

  // Snippets State
  const [snippets, setSnippets] = useState<CodeSnippetItem[]>([]);
  const [loadingSnippets, setLoadingSnippets] = useState(false);
  const [snippetSearch, setSnippetSearch] = useState("");
  const [snippetLangFilter, setSnippetLangFilter] = useState("All");

  // Save Modal
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState("");
  const [saveDesc, setSaveDesc] = useState("");
  const [saveTags, setSaveTags] = useState("");
  const [savingSnippet, setSavingSnippet] = useState(false);

  // AI Assistant State
  const [aiMode, setAiMode] = useState<"generate" | "explain" | "debug">("generate");
  const [genTask, setGenTask] = useState("");
  const [genConstraints, setGenConstraints] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<{
    code: string;
    explanation: string;
    warnings?: string[];
  } | null>(null);

  const [explainInput, setExplainInput] = useState("");
  const [explainLevel, setExplainLevel] = useState("intermediate");
  const [explaining, setExplaining] = useState(false);
  const [explainResult, setExplainResult] = useState<{
    explanation: string;
    key_lines: Array<{ line: number; note: string }>;
    followups?: string[];
  } | null>(null);

  const [debugInput, setDebugInput] = useState("");
  const [debugErrorMsg, setDebugErrorMsg] = useState("");
  const [debugging, setDebugging] = useState(false);
  const [debugResult, setDebugResult] = useState<{
    hypothesis: string;
    evidence: string;
    fix: string;
    fixed_code: string;
    verification?: string;
  } | null>(null);

  // Status & Feedback
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

  const authHeaders = useMemo((): Record<string, string> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return headers;
  }, [accessToken]);

  // Load Data
  const loadSnippetsAndStats = useCallback(async () => {
    if (!accessToken) return;
    setLoadingSnippets(true);
    setFetchError(null);
    try {
      const [snipRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/coding/snippets`, { headers: authHeaders }),
        fetch(`${API_BASE}/coding/stats`, { headers: authHeaders }),
      ]);
      if (snipRes.ok) {
        const data = await snipRes.json();
        setSnippets(data.snippets || []);
      } else {
        setFetchError("Unable to fetch code snippets from the server.");
      }
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Connection failed while loading snippets.");
    } finally {
      setLoadingSnippets(false);
    }
  }, [accessToken, authHeaders]);

  useEffect(() => {
    if (accessToken) {
      loadSnippetsAndStats();
    }
  }, [accessToken, loadSnippetsAndStats]);

  // Execute Code
  const handleRunCode = async () => {
    if (!code.trim() || runningCode) return;
    setRunningCode(true);
    try {
      const res = await fetch(`${API_BASE}/coding/execute`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          language,
          code,
          stdin: showStdin && stdinText.trim() ? stdinText : null,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setLastExecution(data);
        showNotice("Execution completed!");
        if (accessToken) loadSnippetsAndStats();
      } else {
        const errJson = await res.json().catch(() => ({ detail: res.statusText }));
        setLastExecution({
          language,
          status: "error",
          stdout: "",
          stderr: errJson.detail || `HTTP ${res.status}`,
          exit_code: 1,
          execution_time_ms: 0,
        });
      }
    } catch (err) {
      setLastExecution({
        language,
        status: "error",
        stdout: "",
        stderr: `Execution request failed: ${err}`,
        exit_code: 1,
        execution_time_ms: 0,
      });
    } finally {
      setRunningCode(false);
    }
  };

  // Save Snippet
  const handleSaveSnippet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!saveTitle.trim()) return;
    setSavingSnippet(true);
    try {
      const tagList = saveTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const res = await fetch(`${API_BASE}/coding/snippets`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          title: saveTitle.trim(),
          language,
          code,
          description: saveDesc.trim() || null,
          tags: tagList,
        }),
      });

      if (res.ok) {
        setSaveModalOpen(false);
        setSaveTitle("");
        setSaveDesc("");
        setSaveTags("");
        showNotice("Snippet saved to library!");
        await loadSnippetsAndStats();
      } else {
        throw new Error("Failed to save snippet.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Failed to save snippet.");
    } finally {
      setSavingSnippet(false);
    }
  };

  // Toggle Favorite
  const handleToggleFavorite = async (snippet: CodeSnippetItem, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await fetch(`${API_BASE}/coding/snippets/${snippet.id}`, {
        method: "PATCH",
        headers: authHeaders,
        body: JSON.stringify({ is_favorite: !snippet.is_favorite }),
      });
      await loadSnippetsAndStats();
    } catch {
      // Offline fallback
    }
  };

  // Delete Snippet with Optimistic Rollback
  const handleDeleteSnippet = async (snippetId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const prevSnippets = [...snippets];
    const prevStats = { ...stats };
    setSnippets((curr) => curr.filter((s) => s.id !== snippetId));
    setStats((curr) => ({
      ...curr,
      total_snippets: Math.max(0, curr.total_snippets - 1),
    }));

    try {
      const res = await fetch(`${API_BASE}/coding/snippets/${snippetId}`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showNotice("Code snippet deleted.");
      await loadSnippetsAndStats();
    } catch (err) {
      console.error("Delete snippet failed, rolling back:", err);
      setSnippets(prevSnippets);
      setStats(prevStats);
      setFetchError("Failed to delete snippet. Changes rolled back.");
    }
  };

  // AI Generate Code
  const handleGenerateCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!genTask.trim() || generating) return;
    setGenerating(true);
    setGeneratedResult(null);
    try {
      const res = await fetch(`${API_BASE}/coding/generate`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          task: genTask.trim(),
          language,
          constraints: genConstraints
            ? genConstraints.split(",").map((c) => c.trim()).filter(Boolean)
            : null,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setGeneratedResult(data);
        showNotice("Code synthesized!");
      } else {
        throw new Error("Generation failed.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Code synthesis failed.");
    } finally {
      setGenerating(false);
    }
  };

  // AI Explain Code
  const handleExplainCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!explainInput.trim() || explaining) return;
    setExplaining(true);
    setExplainResult(null);
    try {
      const res = await fetch(`${API_BASE}/coding/explain`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          code: explainInput.trim(),
          language,
          level: explainLevel,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setExplainResult(data);
        showNotice("Code explained!");
      } else {
        throw new Error("Explanation failed.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Code explanation failed.");
    } finally {
      setExplaining(false);
    }
  };

  // AI Debug Code
  const handleDebugCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!debugInput.trim() || debugging) return;
    setDebugging(true);
    setDebugResult(null);
    try {
      const res = await fetch(`${API_BASE}/coding/debug`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          code: debugInput.trim(),
          language,
          error_message: debugErrorMsg.trim() || null,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setDebugResult(data);
        showNotice("Bug analyzed and fix proposed!");
      } else {
        throw new Error("Debugging failed.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Debugging failed.");
    } finally {
      setDebugging(false);
    }
  };

  // Language filter list
  const languageOptions = useMemo(() => {
    const set = new Set<string>();
    snippets.forEach((s) => {
      if (s.language) set.add(s.language);
    });
    return ["All", ...Array.from(set)];
  }, [snippets]);

  // Filtered snippets
  const filteredSnippets = useMemo(() => {
    return snippets.filter((s) => {
      const matchSearch =
        !snippetSearch ||
        s.title.toLowerCase().includes(snippetSearch.toLowerCase()) ||
        (s.description && s.description.toLowerCase().includes(snippetSearch.toLowerCase())) ||
        (s.tags && s.tags.some((t) => t.toLowerCase().includes(snippetSearch.toLowerCase())));
      const matchLang =
        snippetLangFilter === "All" || s.language.toLowerCase() === snippetLangFilter.toLowerCase();
      return matchSearch && matchLang;
    });
  }, [snippets, snippetSearch, snippetLangFilter]);

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 pb-16">
      {/* Top Header */}
      <div className="bg-white border-b border-slate-200 sticky top-16 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-2xl p-2 rounded-xl bg-teal-50 border border-teal-200">💻</span>
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
                    Coding & Execution Studio
                    <span className="text-xs px-2 py-0.5 rounded-full bg-teal-100 text-[#0d9488] font-semibold">
                      Sandboxed Runtime
                    </span>
                  </h1>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Autonomous developer copilot, multi-language execution playground, and snippet repository
                  </p>
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200 text-xs font-medium self-start sm:self-auto">
              <button
                onClick={() => setActiveTab("playground")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "playground"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>⚡</span>
                <span>Playground</span>
              </button>
              <button
                onClick={() => setActiveTab("ai")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "ai"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>🤖</span>
                <span>AI Copilot</span>
              </button>
              <button
                onClick={() => setActiveTab("snippets")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "snippets"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>📁</span>
                <span>Snippets</span>
                {snippets.length > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full bg-teal-100 text-[#0d9488] text-[10px]">
                    {snippets.length}
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Stats Bar */}
          <div className="mt-5 pt-4 border-t border-slate-100 flex items-center gap-4 flex-wrap text-xs">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
              <span className="text-slate-400">📄</span>
              <span className="text-slate-600 font-medium">Snippets:</span>
              <strong className="text-slate-900 font-bold">{stats.total_snippets}</strong>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-800">
              <span>⭐</span>
              <span className="font-medium">Favorites:</span>
              <strong className="font-bold">{stats.favorite_snippets}</strong>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
              <span className="text-slate-400">▶</span>
              <span className="text-slate-600 font-medium">Total Runs:</span>
              <strong className="text-slate-900 font-bold">{stats.total_executions}</strong>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800">
              <span>✓</span>
              <span className="font-medium">Success Rate:</span>
              <strong className="font-bold">{stats.success_rate_percentage}%</strong>
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
                <strong>Guest Mode:</strong> You can write and execute code in the sandbox locally, but saving snippets and cloud execution history require signing in.
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
                loadSnippetsAndStats();
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
        {/* TAB 1: PLAYGROUND & RUNNER                                               */}
        {/* ========================================================================= */}
        {activeTab === "playground" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Editor Side */}
            <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4 flex flex-col">
              <div className="flex items-center justify-between gap-3 pb-3 border-b border-slate-100 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-700">Language:</span>
                  <select
                    value={language}
                    onChange={(e) => {
                      const l = e.target.value;
                      setLanguage(l);
                      if (DEFAULT_TEMPLATES[l]) setCode(DEFAULT_TEMPLATES[l]);
                    }}
                    className="px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-800 focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                  >
                    <option value="python">Python 3.14</option>
                    <option value="javascript">JavaScript (Node.js)</option>
                    <option value="typescript">TypeScript</option>
                    <option value="bash">Bash / Shell</option>
                    <option value="sql">SQL Query</option>
                    <option value="json">JSON Document</option>
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowStdin(!showStdin)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors border ${
                      showStdin
                        ? "bg-teal-50 border-teal-200 text-[#0d9488]"
                        : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    Stdin {showStdin ? "▲" : "▼"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setSaveModalOpen(true)}
                    className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1"
                  >
                    <span>💾</span>
                    <span>Save Snippet</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleRunCode}
                    disabled={runningCode || !code.trim()}
                    className="px-4 py-1 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-lg text-xs font-semibold transition-all shadow-sm flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {runningCode ? (
                      <>
                        <span className="inline-block animate-spin">↻</span>
                        <span>Running…</span>
                      </>
                    ) : (
                      <>
                        <span>▶</span>
                        <span>Execute</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Stdin Drawer */}
              {showStdin && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
                  <label className="block text-[11px] font-semibold text-slate-600">
                    Standard Input (stdin):
                  </label>
                  <textarea
                    rows={2}
                    value={stdinText}
                    onChange={(e) => setStdinText(e.target.value)}
                    placeholder="Provide input lines for input() or readline()..."
                    className="w-full px-3 py-1.5 bg-white border border-slate-200 rounded-lg font-mono text-xs focus:outline-none"
                  />
                </div>
              )}

              {/* Code Editor */}
              <div className="flex-1 min-h-[360px] flex flex-col">
                <textarea
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Type your code here..."
                  className="w-full flex-1 p-4 bg-slate-900 text-emerald-400 font-mono text-xs rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/40 resize-y leading-relaxed"
                />
              </div>
            </div>

            {/* Terminal Output Side */}
            <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-900">Execution Output</span>
                  {lastExecution && (
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        lastExecution.status === "success"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {lastExecution.status.toUpperCase()} (Exit {lastExecution.exit_code})
                    </span>
                  )}
                </div>
                {lastExecution && (
                  <div className="flex items-center gap-2 text-[11px] text-slate-400">
                    <span>{lastExecution.execution_time_ms}ms</span>
                    <button
                      type="button"
                      onClick={() =>
                        handleCopy(
                          lastExecution.stdout || lastExecution.stderr,
                          "term-copy"
                        )
                      }
                      className="hover:text-slate-700 transition-colors"
                      title="Copy Output"
                    >
                      {copiedId === "term-copy" ? "✓" : "📋"}
                    </button>
                  </div>
                )}
              </div>

              <div className="flex-1 mt-4">
                {lastExecution ? (
                  <pre
                    className={`p-4 rounded-xl font-mono text-xs overflow-y-auto max-h-[460px] leading-relaxed ${
                      lastExecution.stderr && !lastExecution.stdout
                        ? "bg-red-950/90 text-red-300"
                        : "bg-slate-900 text-emerald-300"
                    }`}
                  >
                    {lastExecution.stdout || lastExecution.stderr || "(Execution completed with no output)"}
                  </pre>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center py-20 text-slate-400 text-xs text-center">
                    <span className="text-3xl mb-2">⚡</span>
                    <p>Click &quot;Execute&quot; to run your code.</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Output and errors will be captured in this terminal.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: AI DEVELOPER COPILOT                                              */}
        {/* ========================================================================= */}
        {activeTab === "ai" && (
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
            {/* Mode Switcher */}
            <div className="flex items-center gap-2 pb-4 border-b border-slate-100">
              {(["generate", "explain", "debug"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setAiMode(m)}
                  className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                    aiMode === m
                      ? "bg-[#0d9488] text-white shadow-sm"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {m === "generate" && "⚡ Code Synthesis"}
                  {m === "explain" && "📖 Code Explanation"}
                  {m === "debug" && "🐛 Bug Diagnostic & Fix"}
                </button>
              ))}
            </div>

            {/* Sub-mode 1: Generate */}
            {aiMode === "generate" && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 text-xs">
                <form onSubmit={handleGenerateCode} className="lg:col-span-5 space-y-4">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">Task Description</label>
                    <textarea
                      rows={3}
                      value={genTask}
                      onChange={(e) => setGenTask(e.target.value)}
                      placeholder="e.g. Write a FastApi middleware for request rate limiting using sliding windows..."
                      required
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    />
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">
                      Constraints (Comma-Separated)
                    </label>
                    <input
                      type="text"
                      value={genConstraints}
                      onChange={(e) => setGenConstraints(e.target.value)}
                      placeholder="async, type hints, zero dependencies"
                      className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={generating || !genTask.trim()}
                    className="w-full py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {generating ? "Synthesizing…" : "Synthesize Code"}
                  </button>
                </form>

                <div className="lg:col-span-7 bg-slate-50 rounded-xl border border-slate-200 p-4 flex flex-col justify-between">
                  {generatedResult ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800">Synthesized Solution</span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setCode(generatedResult.code);
                              setActiveTab("playground");
                            }}
                            className="px-2.5 py-1 bg-white border border-slate-200 text-[#0d9488] rounded-md font-semibold hover:bg-teal-50"
                          >
                            Load in Playground
                          </button>
                          <button
                            type="button"
                            onClick={() => handleCopy(generatedResult.code, "gen-copy")}
                            className="px-2.5 py-1 bg-white border border-slate-200 text-slate-700 rounded-md hover:bg-slate-100"
                          >
                            {copiedId === "gen-copy" ? "✓" : "📋"}
                          </button>
                        </div>
                      </div>
                      <pre className="p-3 bg-slate-900 text-emerald-300 font-mono text-xs rounded-xl overflow-x-auto max-h-72">
                        {generatedResult.code}
                      </pre>
                      <p className="text-slate-600 leading-relaxed">{generatedResult.explanation}</p>
                    </div>
                  ) : (
                    <div className="h-full flex items-center justify-center py-16 text-slate-400 text-center">
                      Describe your coding problem and click Synthesize Code.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Sub-mode 2: Explain */}
            {aiMode === "explain" && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 text-xs">
                <form onSubmit={handleExplainCode} className="lg:col-span-5 space-y-4">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">Code to Explain</label>
                    <textarea
                      rows={6}
                      value={explainInput}
                      onChange={(e) => setExplainInput(e.target.value)}
                      placeholder="Paste code snippet to analyze..."
                      required
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    />
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">Target Audience</label>
                    <select
                      value={explainLevel}
                      onChange={(e) => setExplainLevel(e.target.value)}
                      className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                    >
                      <option value="beginner">Beginner (Foundations & Metaphors)</option>
                      <option value="intermediate">Intermediate (Standard Architecture)</option>
                      <option value="advanced">Advanced (Deep Performance & Memory)</option>
                    </select>
                  </div>
                  <button
                    type="submit"
                    disabled={explaining || !explainInput.trim()}
                    className="w-full py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {explaining ? "Explaining…" : "Explain Code"}
                  </button>
                </form>

                <div className="lg:col-span-7 bg-slate-50 rounded-xl border border-slate-200 p-4">
                  {explainResult ? (
                    <div className="space-y-4">
                      <div>
                        <h4 className="font-bold text-slate-900 mb-1">Architecture Summary</h4>
                        <p className="text-slate-700 leading-relaxed">{explainResult.explanation}</p>
                      </div>

                      {explainResult.key_lines && explainResult.key_lines.length > 0 && (
                        <div>
                          <h4 className="font-bold text-slate-900 mb-1.5">Key Line Breakdown</h4>
                          <div className="space-y-1.5">
                            {explainResult.key_lines.map((kl, i) => (
                              <div key={i} className="p-2 bg-white rounded-lg border border-slate-200 flex gap-2">
                                <span className="font-mono font-bold text-[#0d9488]">L{kl.line}:</span>
                                <span className="text-slate-700">{kl.note}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="h-full flex items-center justify-center py-16 text-slate-400 text-center">
                      Paste a code snippet to analyze its components and architectural patterns.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Sub-mode 3: Debug */}
            {aiMode === "debug" && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 text-xs">
                <form onSubmit={handleDebugCode} className="lg:col-span-5 space-y-4">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">Failing Code</label>
                    <textarea
                      rows={5}
                      value={debugInput}
                      onChange={(e) => setDebugInput(e.target.value)}
                      placeholder="Paste buggy code here..."
                      required
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    />
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">
                      Error Message / Traceback (Optional)
                    </label>
                    <textarea
                      rows={2}
                      value={debugErrorMsg}
                      onChange={(e) => setDebugErrorMsg(e.target.value)}
                      placeholder="e.g. IndexError: list index out of range"
                      className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={debugging || !debugInput.trim()}
                    className="w-full py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {debugging ? "Diagnosing…" : "Diagnose & Fix"}
                  </button>
                </form>

                <div className="lg:col-span-7 bg-slate-50 rounded-xl border border-slate-200 p-4">
                  {debugResult ? (
                    <div className="space-y-3">
                      <div>
                        <span className="font-bold text-slate-800">Hypothesis: </span>
                        <span className="text-slate-700">{debugResult.hypothesis}</span>
                      </div>
                      <div>
                        <span className="font-bold text-slate-800">Root Cause Evidence: </span>
                        <span className="text-slate-700">{debugResult.evidence}</span>
                      </div>
                      <div>
                        <span className="font-bold text-slate-800">Correction: </span>
                        <span className="text-slate-700">{debugResult.fix}</span>
                      </div>

                      <div className="pt-2">
                        <div className="flex items-center justify-between pb-1">
                          <span className="font-bold text-slate-900">Corrected Code</span>
                          <button
                            type="button"
                            onClick={() => {
                              setCode(debugResult.fixed_code);
                              setActiveTab("playground");
                            }}
                            className="px-2.5 py-1 bg-white border border-slate-200 text-[#0d9488] rounded-md font-semibold hover:bg-teal-50"
                          >
                            Load in Playground
                          </button>
                        </div>
                        <pre className="p-3 bg-slate-900 text-emerald-300 font-mono text-xs rounded-xl overflow-x-auto max-h-56">
                          {debugResult.fixed_code}
                        </pre>
                      </div>
                    </div>
                  ) : (
                    <div className="h-full flex items-center justify-center py-16 text-slate-400 text-center">
                      Paste broken code and optional traceback to receive root-cause analysis and automated fixes.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: SNIPPETS LIBRARY                                                  */}
        {/* ========================================================================= */}
        {activeTab === "snippets" && (
          <div className="space-y-6">
            {/* Toolbar */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
              <div className="relative flex-1 sm:max-w-md">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
                <input
                  type="text"
                  value={snippetSearch}
                  onChange={(e) => setSnippetSearch(e.target.value)}
                  placeholder="Search snippets by title, description, or tags..."
                  className="w-full pl-10 pr-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setSaveModalOpen(true)}
                  className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl text-xs font-semibold transition-all shadow-sm flex items-center gap-1.5"
                >
                  <span>＋</span>
                  <span>Save Snippet</span>
                </button>
                <button
                  type="button"
                  onClick={loadSnippetsAndStats}
                  className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl text-xs transition-colors"
                  title="Refresh snippets"
                >
                  ↻
                </button>
              </div>
            </div>

            {/* Language filter pills */}
            {languageOptions.length > 1 && (
              <div className="flex items-center gap-1.5 flex-wrap text-xs">
                <span className="text-slate-400 font-medium mr-1">Language:</span>
                {languageOptions.map((lang) => (
                  <button
                    key={lang}
                    onClick={() => setSnippetLangFilter(lang)}
                    className={`px-3 py-1 rounded-lg transition-colors ${
                      snippetLangFilter === lang
                        ? "bg-[#0d9488] text-white font-semibold shadow-sm"
                        : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {lang.toUpperCase()}
                  </button>
                ))}
              </div>
            )}

            {/* Snippets Grid */}
            {loadingSnippets ? (
              <div className="py-20 text-center text-xs text-slate-500">
                <span className="inline-block animate-spin text-xl mb-2">↻</span>
                <p>Loading snippets library…</p>
              </div>
            ) : filteredSnippets.length === 0 ? (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center">
                <span className="text-4xl block mb-2">📄</span>
                <h3 className="text-base font-bold text-slate-800">No Code Snippets Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-4">
                  {snippetSearch || snippetLangFilter !== "All"
                    ? "No snippets match your active search filters."
                    : "Save snippets from the playground or synthesize code with the AI Copilot."}
                </p>
                <button
                  onClick={() => setActiveTab("playground")}
                  className="px-4 py-2 bg-[#0d9488] text-white rounded-xl text-xs font-semibold hover:bg-[#0f766e] transition-colors"
                >
                  Open Playground
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {filteredSnippets.map((snip) => (
                  <div
                    key={snip.id}
                    className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-teal-50 text-[#0d9488] border border-teal-200">
                          {snip.language.toUpperCase()}
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={(e) => handleToggleFavorite(snip, e)}
                            className={`text-xs transition-colors ${
                              snip.is_favorite ? "text-amber-500" : "text-slate-300 hover:text-amber-400"
                            }`}
                            title="Favorite"
                          >
                            ★
                          </button>
                          <button
                            type="button"
                            onClick={(e) => handleDeleteSnippet(snip.id, e)}
                            className="text-slate-300 hover:text-red-600 transition-colors text-xs"
                            title="Delete Snippet"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>

                      <h3 className="text-sm font-bold text-slate-900 mb-1 line-clamp-1">{snip.title}</h3>
                      {snip.description && (
                        <p className="text-xs text-slate-500 mb-3 line-clamp-2">{snip.description}</p>
                      )}

                      {snip.tags && snip.tags.length > 0 && (
                        <div className="flex items-center gap-1 flex-wrap mb-3">
                          {snip.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600">
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setCode(snip.code);
                          setLanguage(snip.language);
                          setActiveTab("playground");
                        }}
                        className="flex-1 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold transition-colors text-center"
                      >
                        Load in Playground
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopy(snip.code, snip.id)}
                        className="p-1.5 text-slate-400 hover:text-slate-700 transition-colors"
                        title="Copy Code"
                      >
                        {copiedId === snip.id ? "✓" : "📋"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Save Modal */}
      {saveModalOpen && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setSaveModalOpen(false)}
        >
          <div
            className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-bold text-slate-900 mb-4">Save Snippet to Library</h3>
            <form onSubmit={handleSaveSnippet} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Snippet Title</label>
                <input
                  type="text"
                  value={saveTitle}
                  onChange={(e) => setSaveTitle(e.target.value)}
                  placeholder="e.g. Binary Search Tree Insertion"
                  required
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  rows={2}
                  value={saveDesc}
                  onChange={(e) => setSaveDesc(e.target.value)}
                  placeholder="Optional context about the utility..."
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Tags (Comma-Separated)</label>
                <input
                  type="text"
                  value={saveTags}
                  onChange={(e) => setSaveTags(e.target.value)}
                  placeholder="algorithm, trees, search"
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setSaveModalOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingSnippet || !saveTitle.trim()}
                  className="px-5 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold shadow-sm"
                >
                  {savingSnippet ? "Saving…" : "Save Snippet"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
