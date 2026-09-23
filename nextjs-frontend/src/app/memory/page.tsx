"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";

export type ImportanceLevel = "low" | "normal" | "high" | "forever";

interface MemoryItem {
  id: string;
  user_id?: string;
  content: string;
  importance: ImportanceLevel;
  source: string;
  tags: string[];
  is_soft_deleted: boolean;
  soft_deleted_at?: string | null;
  soft_delete_reason?: string | null;
  cluster_id?: string | null;
  source_entry_ids?: string[];
  retrieval_count: number;
  last_retrieved_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface MemoryRetrieveItem {
  entry_id: string;
  content: string;
  importance: string;
  source: string;
  tags: string[];
  score: number;
  stored_at?: string | null;
}

interface CuratorPolicyConfig {
  summarize_after_days: number;
  cluster_min_size: number;
  soft_delete_never_retrieved_days: number;
  hard_delete_after_days: number;
  notify_on_changes: boolean;
}

interface CuratorRunReport {
  id: string;
  user_id?: string;
  entries_scanned: number;
  summarized_count: number;
  clusters_formed: any[];
  soft_deleted_count: number;
  hard_deleted_count: number;
  errors_count: number;
  duration_ms: number;
  status: string;
  diff_summary: string;
  created_at?: string | null;
}

interface MemoryStats {
  total_memories: number;
  active_memories: number;
  forever_memories: number;
  soft_deleted_memories: number;
  curator_runs_count: number;
  last_curated_at?: string | null;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function MemoryPage() {
  const [activeTab, setActiveTab] = useState<"vault" | "curator" | "retrieve" | "privacy">("vault");
  const [token, setToken] = useState<string | null>(null);

  // Core State
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [stats, setStats] = useState<MemoryStats>({
    total_memories: 0,
    active_memories: 0,
    forever_memories: 0,
    soft_deleted_memories: 0,
    curator_runs_count: 0,
    last_curated_at: null,
  });
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [importanceFilter, setImportanceFilter] = useState<string>("all");
  const [selectedTag, setSelectedTag] = useState<string>("all");
  const [includeArchived, setIncludeArchived] = useState(false);

  // Modals & Forms
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [formContent, setFormContent] = useState("");
  const [formImportance, setFormImportance] = useState<ImportanceLevel>("normal");
  const [formTags, setFormTags] = useState("");

  // Curator Tab State
  const [curatorPolicy, setCuratorPolicy] = useState<CuratorPolicyConfig>({
    summarize_after_days: 30,
    cluster_min_size: 3,
    soft_delete_never_retrieved_days: 180,
    hard_delete_after_days: 30,
    notify_on_changes: true,
  });
  const [curatorReports, setCuratorReports] = useState<CuratorRunReport[]>([]);
  const [curatorRunning, setCuratorRunning] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);

  // Semantic Retrieval Testing
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [retrievalResults, setRetrievalResults] = useState<MemoryRetrieveItem[] | null>(null);
  const [isRetrieving, setIsRetrieving] = useState(false);

  // Privacy Tab State
  const [purgeInput, setPurgeInput] = useState("");
  const [isPurging, setIsPurging] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Notification Toast
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }, []);

  // Auth initialization
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("access_token");
      if (stored) setToken(stored);
    }
  }, []);

  const authHeaders = useMemo(() => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }, [token]);

  // 1. Fetch Memories
  const fetchMemories = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const url = `${API_BASE}/memory/entries?include_soft_deleted=${includeArchived}&limit=100`;
      const res = await fetch(url, { headers: authHeaders });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      const items: MemoryItem[] = Array.isArray(data) ? data : data.entries || [];
      setMemories(items);
    } catch (err: any) {
      const msg = err.message || "Failed to load semantic memories";
      setFetchError(msg);
      showToast("error", msg);
    } finally {
      setLoading(false);
    }
  }, [includeArchived, authHeaders, showToast]);

  // 2. Fetch Stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/memory/stats`, { headers: authHeaders });
      if (res.ok) {
        const data: MemoryStats = await res.json();
        setStats(data);
      }
    } catch {
      // Non-blocking telemetry
    }
  }, [authHeaders]);

  // 3. Fetch Curator Policy & Reports
  const fetchCuratorData = useCallback(async () => {
    try {
      const [policyRes, reportsRes] = await Promise.all([
        fetch(`${API_BASE}/memory/curator/policy`, { headers: authHeaders }),
        fetch(`${API_BASE}/memory/curator/reports?limit=15`, { headers: authHeaders }),
      ]);
      if (policyRes.ok) {
        const pData: CuratorPolicyConfig = await policyRes.json();
        setCuratorPolicy(pData);
      }
      if (reportsRes.ok) {
        const rData: CuratorRunReport[] = await reportsRes.json();
        setCuratorReports(rData);
      }
    } catch {
      // Non-blocking curator load
    }
  }, [authHeaders]);

  useEffect(() => {
    fetchMemories();
    fetchStats();
    if (activeTab === "curator") {
      fetchCuratorData();
    }
  }, [fetchMemories, fetchStats, fetchCuratorData, activeTab]);

  // Extract all unique tags
  const allTags = useMemo(() => {
    const tagSet = new Set<string>();
    memories.forEach((m) => m.tags.forEach((t) => tagSet.add(t)));
    return Array.from(tagSet).sort();
  }, [memories]);

  // Filtered Memories
  const filteredMemories = useMemo(() => {
    return memories.filter((m) => {
      if (importanceFilter !== "all" && m.importance !== importanceFilter) {
        return false;
      }
      if (selectedTag !== "all" && !m.tags.includes(selectedTag)) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesContent = m.content.toLowerCase().includes(q);
        const matchesTags = m.tags.some((t) => t.toLowerCase().includes(q));
        if (!matchesContent && !matchesTags) return false;
      }
      return true;
    });
  }, [memories, importanceFilter, selectedTag, searchQuery]);

  // Create or Update Memory
  const handleSaveMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formContent.trim()) {
      showToast("error", "Memory content cannot be empty.");
      return;
    }

    const tags = formTags
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);

    try {
      if (editingMemoryId) {
        const res = await fetch(`${API_BASE}/memory/entries/${editingMemoryId}`, {
          method: "PATCH",
          headers: authHeaders,
          body: JSON.stringify({
            content: formContent.trim(),
            importance: formImportance,
            tags,
          }),
        });
        if (!res.ok) throw new Error("Failed to update memory");
        showToast("success", "Memory updated successfully.");
      } else {
        const res = await fetch(`${API_BASE}/memory/entries`, {
          method: "POST",
          headers: authHeaders,
          body: JSON.stringify({
            content: formContent.trim(),
            importance: formImportance,
            tags,
            source: "user:explicit",
          }),
        });
        if (!res.ok) throw new Error("Failed to create memory");
        showToast("success", "Memory stored in vault.");
      }

      setIsAddModalOpen(false);
      setEditingMemoryId(null);
      setFormContent("");
      setFormTags("");
      setFormImportance("normal");
      fetchMemories();
      fetchStats();
    } catch (err: any) {
      showToast("error", err.message || "Action failed.");
    }
  };

  // Toggle Forever Importance (Optimistic with rollback)
  const handleToggleForever = async (mem: MemoryItem) => {
    const nextImportance: ImportanceLevel = mem.importance === "forever" ? "normal" : "forever";
    const previous = [...memories];
    setMemories((prev) =>
      prev.map((m) => (m.id === mem.id ? { ...m, importance: nextImportance } : m))
    );
    try {
      const res = await fetch(`${API_BASE}/memory/entries/${mem.id}`, {
        method: "PATCH",
        headers: authHeaders,
        body: JSON.stringify({ importance: nextImportance }),
      });
      if (!res.ok) throw new Error("Failed to toggle pin");
      showToast(
        "success",
        nextImportance === "forever" ? "Pinned as Forever Memory." : "Unpinned from Forever."
      );
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast("error", err.message || "Failed to update pin.");
    }
  };

  // Soft Delete / Archive (Optimistic with rollback)
  const handleSoftDelete = async (id: string) => {
    const previous = [...memories];
    if (!includeArchived) {
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } else {
      setMemories((prev) =>
        prev.map((m) => (m.id === id ? { ...m, is_soft_deleted: true } : m))
      );
    }
    try {
      const res = await fetch(`${API_BASE}/memory/entries/${id}`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Failed to archive memory");
      showToast("success", "Memory moved to soft-delete archive.");
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast("error", err.message || "Failed to archive memory.");
    }
  };

  // Restore Memory (Optimistic with rollback)
  const handleRestore = async (id: string) => {
    const previous = [...memories];
    setMemories((prev) =>
      prev.map((m) => (m.id === id ? { ...m, is_soft_deleted: false } : m))
    );
    try {
      const res = await fetch(`${API_BASE}/memory/entries/${id}/restore`, {
        method: "POST",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Failed to restore memory");
      showToast("success", "Memory restored to active vault.");
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast("error", err.message || "Failed to restore memory.");
    }
  };

  // Permanent Delete (Optimistic with rollback)
  const handlePermanentDelete = async (id: string) => {
    const previous = [...memories];
    setMemories((prev) => prev.filter((m) => m.id !== id));
    try {
      const res = await fetch(`${API_BASE}/memory/entries/${id}?permanent=true`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Failed to delete memory permanently");
      showToast("success", "Memory permanently purged.");
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast("error", err.message || "Failed to delete memory.");
    }
  };

  // Copy Content Helper
  const handleCopy = (id: string, text: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  // Run Semantic Retrieval Test
  const handleRunRetrieval = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!retrievalQuery.trim()) return;

    setIsRetrieving(true);
    try {
      const res = await fetch(`${API_BASE}/memory/retrieve`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          query: retrievalQuery.trim(),
          top_k: topK,
          min_score: 0.05,
        }),
      });
      if (!res.ok) throw new Error("Retrieval query failed");
      const data = await res.json();
      setRetrievalResults(data.entries || []);
    } catch (err: any) {
      showToast("error", err.message || "Retrieval search failed");
    } finally {
      setIsRetrieving(false);
    }
  };

  // Trigger Autonomous Curator Pass
  const handleRunCurator = async () => {
    setCuratorRunning(true);
    try {
      const res = await fetch(`${API_BASE}/memory/curator/run`, {
        method: "POST",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Curator run failed");
      const report: CuratorRunReport = await res.json();
      setCuratorReports((prev) => [report, ...prev]);
      showToast("success", `Curator pass completed: ${report.entries_scanned} scanned.`);
      fetchMemories();
      fetchStats();
    } catch (err: any) {
      showToast("error", err.message || "Curator execution failed");
    } finally {
      setCuratorRunning(false);
    }
  };

  // Save Curator Policy
  const handleSavePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingPolicy(true);
    try {
      const res = await fetch(`${API_BASE}/memory/curator/policy`, {
        method: "PUT",
        headers: authHeaders,
        body: JSON.stringify(curatorPolicy),
      });
      if (!res.ok) throw new Error("Failed to update policy");
      const updated: CuratorPolicyConfig = await res.json();
      setCuratorPolicy(updated);
      showToast("success", "Curator policy configuration updated.");
    } catch (err: any) {
      showToast("error", err.message || "Policy update failed");
    } finally {
      setSavingPolicy(false);
    }
  };

  // Export User Memory Vault
  const handleExportData = async () => {
    setExporting(true);
    try {
      const res = await fetch(`${API_BASE}/memory/export`, { headers: authHeaders });
      if (!res.ok) throw new Error("Export failed");
      const bundle = await res.json();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `roxy_memory_vault_export_${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      showToast("success", "Memory vault export downloaded successfully.");
    } catch (err: any) {
      showToast("error", err.message || "Failed to export data");
    } finally {
      setExporting(false);
    }
  };

  // Purge All Memories (GDPR Erasure)
  const handlePurgeAll = async () => {
    if (purgeInput.trim() !== "PURGE ALL MEMORIES") {
      showToast("error", 'Please type "PURGE ALL MEMORIES" exactly to confirm.');
      return;
    }
    setIsPurging(true);
    try {
      const res = await fetch(`${API_BASE}/memory/purge-all`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Purge request failed");
      const data = await res.json();
      const count = data.purged_count ?? data.deleted_count ?? 0;
      showToast("success", `Permanently erased ${count} memories.`);
      setPurgeInput("");
      fetchMemories();
      fetchStats();
    } catch (err: any) {
      showToast("error", err.message || "Purge execution failed");
    } finally {
      setIsPurging(false);
    }
  };

  const getImportanceColor = (imp: string) => {
    switch (imp) {
      case "forever":
        return "bg-purple-900/40 text-purple-300 border-purple-700/60";
      case "high":
        return "bg-amber-900/40 text-amber-300 border-amber-700/60";
      case "low":
        return "bg-slate-800 text-slate-400 border-slate-700";
      default:
        return "bg-teal-900/40 text-teal-300 border-teal-700/60";
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
              ? "bg-teal-950/90 text-teal-200 border-teal-700/80"
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
              <span className="text-2xl">🧠</span>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                Semantic Memory & Curator Studio
                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-800">
                  Cross-Session AI
                </span>
              </h1>
            </div>
            <p className="text-xs text-[#95a8a8] mt-1">
              Autonomous semantic facts vault, cross-turn context grounding, self-healing memory clustering, and GDPR erasure.
            </p>
          </div>

          {/* Telemetry Counter Chips */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Active:</span>
              <span className="text-sm font-semibold text-teal-400">{stats.active_memories}</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Forever:</span>
              <span className="text-sm font-semibold text-purple-400">{stats.forever_memories}</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Archived:</span>
              <span className="text-sm font-semibold text-slate-400">{stats.soft_deleted_memories}</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#1a2525] border border-[#273636] flex items-center gap-2">
              <span className="text-xs text-[#95a8a8]">Curator Runs:</span>
              <span className="text-sm font-semibold text-indigo-400">{stats.curator_runs_count}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {/* Guest Authentication Banner */}
        {!token && (
          <div className="mb-6 p-3.5 rounded-xl bg-purple-950/40 border border-purple-800/60 text-purple-200 text-xs flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-base">ℹ️</span>
              <span>
                <strong>Guest Mode:</strong> You are viewing semantic memories in read-only local storage. Sign in with a verified account to persist long-term memories and trigger autonomous curator passes.
              </span>
            </div>
          </div>
        )}

        {/* Connection Error Banner */}
        {fetchError && (
          <div className="mb-6 p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-200 text-xs flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-base">⚠️</span>
              <span>{fetchError}</span>
            </div>
            <button
              type="button"
              onClick={() => {
                fetchMemories();
                fetchStats();
                if (activeTab === "curator") fetchCuratorData();
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
            onClick={() => setActiveTab("vault")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "vault"
                ? "bg-purple-950/60 text-purple-300 border border-purple-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>📁</span>
            <span>Semantic Vault</span>
            <span className="text-xs px-1.5 py-0.2 bg-[#273636] rounded-full text-slate-300">
              {memories.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("curator")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "curator"
                ? "bg-purple-950/60 text-purple-300 border border-purple-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>⚡</span>
            <span>Autonomous Curator</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("retrieve")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "retrieve"
                ? "bg-purple-950/60 text-purple-300 border border-purple-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>🔍</span>
            <span>Retrieval Inspector</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("privacy")}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === "privacy"
                ? "bg-purple-950/60 text-purple-300 border border-purple-700/60 shadow-sm"
                : "text-[#95a8a8] hover:text-white hover:bg-[#1a2525]"
            }`}
          >
            <span>🛡️</span>
            <span>Privacy & GDPR</span>
          </button>
        </div>

        {/* ========================================================================= */}
        {/* TAB 1: SEMANTIC VAULT */}
        {/* ========================================================================= */}
        {activeTab === "vault" && (
          <div className="space-y-6">
            {/* Filter and Action Header */}
            <div className="p-4 rounded-xl bg-[#141d1d] border border-[#273636] flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-3 flex-wrap flex-1">
                {/* Search Input */}
                <div className="relative min-w-[240px] flex-1 max-w-md">
                  <span className="absolute left-3 top-2.5 text-slate-500 text-sm">🔍</span>
                  <input
                    type="text"
                    placeholder="Search memories, facts, or tags..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
                  />
                </div>

                {/* Importance Filter Chips */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {["all", "forever", "high", "normal", "low"].map((imp) => (
                    <button
                      key={imp}
                      type="button"
                      onClick={() => setImportanceFilter(imp)}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium capitalize transition-all ${
                        importanceFilter === imp
                          ? "bg-purple-900/60 text-purple-200 border border-purple-600"
                          : "bg-[#1a2525] text-slate-400 hover:text-white border border-[#273636]"
                      }`}
                    >
                      {imp}
                    </button>
                  ))}
                </div>

                {/* Archived Toggle */}
                <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer select-none ml-auto md:ml-0">
                  <input
                    type="checkbox"
                    checked={includeArchived}
                    onChange={(e) => setIncludeArchived(e.target.checked)}
                    className="rounded bg-[#0e1515] border-[#273636] text-purple-600 focus:ring-0"
                  />
                  <span>Show Archived</span>
                </label>
              </div>

              {/* Add Memory Button */}
              <button
                type="button"
                onClick={() => {
                  setEditingMemoryId(null);
                  setFormContent("");
                  setFormTags("");
                  setFormImportance("normal");
                  setIsAddModalOpen(true);
                }}
                className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-lg text-xs font-medium flex items-center justify-center gap-2 transition-colors shadow-sm whitespace-nowrap"
              >
                <span>➕</span>
                <span>Store Memory</span>
              </button>
            </div>

            {/* Tag Filter Chips Bar */}
            {allTags.length > 0 && (
              <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
                <span className="text-slate-500 whitespace-nowrap">Filter Tag:</span>
                <button
                  type="button"
                  onClick={() => setSelectedTag("all")}
                  className={`px-2 py-0.5 rounded-full border transition-all ${
                    selectedTag === "all"
                      ? "bg-teal-950 text-teal-300 border-teal-700"
                      : "bg-[#141d1d] text-slate-400 border-[#273636] hover:text-white"
                  }`}
                >
                  All
                </button>
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => setSelectedTag(tag)}
                    className={`px-2 py-0.5 rounded-full border transition-all ${
                      selectedTag === tag
                        ? "bg-teal-950 text-teal-300 border-teal-700"
                        : "bg-[#141d1d] text-slate-400 border-[#273636] hover:text-white"
                    }`}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            )}

            {/* Memories Grid or Clean Zero State */}
            {loading ? (
              <div className="py-20 text-center text-slate-500 text-sm">
                <span className="inline-block animate-spin mr-2">↻</span> Loading semantic memories...
              </div>
            ) : filteredMemories.length === 0 ? (
              <div className="py-20 text-center rounded-2xl border border-dashed border-[#273636] bg-[#141d1d]/40 p-8">
                <span className="text-4xl block mb-3">🧠</span>
                <h3 className="text-base font-semibold text-white mb-1">
                  {searchQuery || importanceFilter !== "all" || selectedTag !== "all"
                    ? "No matching memories found"
                    : "No memories stored in vault"}
                </h3>
                <p className="text-xs text-[#95a8a8] max-w-sm mx-auto mb-5">
                  {searchQuery || importanceFilter !== "all" || selectedTag !== "all"
                    ? "Try adjusting your search terms or clearing your active filters."
                    : "Store user preferences, facts, project guidelines, and key knowledge to ground ROXY's multi-agent responses."}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setEditingMemoryId(null);
                    setFormContent("");
                    setFormTags("");
                    setFormImportance("normal");
                    setIsAddModalOpen(true);
                  }}
                  className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-lg text-xs font-medium inline-flex items-center gap-2 transition-colors"
                >
                  <span>➕</span>
                  <span>Store First Memory</span>
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredMemories.map((mem) => (
                  <div
                    key={mem.id}
                    className={`p-4 rounded-xl border transition-all flex flex-col justify-between ${
                      mem.is_soft_deleted
                        ? "bg-[#121919]/60 border-slate-800 opacity-60"
                        : "bg-[#141d1d] border-[#273636] hover:border-purple-800/80 shadow-sm"
                    }`}
                  >
                    <div>
                      {/* Top Badges */}
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border uppercase tracking-wider ${getImportanceColor(
                            mem.importance
                          )}`}
                        >
                          {mem.importance}
                        </span>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            title={mem.importance === "forever" ? "Unpin forever" : "Pin forever"}
                            onClick={() => handleToggleForever(mem)}
                            className={`p-1 rounded text-xs transition-colors ${
                              mem.importance === "forever"
                                ? "text-purple-400 hover:text-purple-300"
                                : "text-slate-500 hover:text-purple-400"
                            }`}
                          >
                            📌
                          </button>
                          <button
                            type="button"
                            title="Copy memory content"
                            onClick={() => handleCopy(mem.id, mem.content)}
                            className="p-1 rounded text-slate-500 hover:text-white text-xs transition-colors"
                          >
                            {copiedId === mem.id ? "✓" : "📋"}
                          </button>
                        </div>
                      </div>

                      {/* Content */}
                      <p className="text-xs text-slate-200 leading-relaxed font-sans mb-3 break-words whitespace-pre-wrap">
                        {mem.content}
                      </p>

                      {/* Tags */}
                      {mem.tags && mem.tags.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap mb-3">
                          {mem.tags.map((t) => (
                            <span
                              key={t}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-[#1a2525] text-teal-400 border border-[#273636]"
                            >
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Bottom Metadata & Controls */}
                    <div className="border-t border-[#273636] pt-3 mt-2 flex items-center justify-between text-[11px] text-[#95a8a8]">
                      <div className="flex items-center gap-2">
                        <span title="Retrieval count">🔄 {mem.retrieval_count}</span>
                        {mem.is_soft_deleted && (
                          <span className="text-amber-500 text-[10px] font-medium">Archived</span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        {mem.is_soft_deleted ? (
                          <>
                            <button
                              type="button"
                              onClick={() => handleRestore(mem.id)}
                              className="px-2 py-0.5 bg-teal-950 hover:bg-teal-900 text-teal-300 border border-teal-800 rounded text-[10px] transition-colors"
                            >
                              Restore
                            </button>
                            <button
                              type="button"
                              onClick={() => handlePermanentDelete(mem.id)}
                              className="px-2 py-0.5 bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 rounded text-[10px] transition-colors"
                            >
                              Purge
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingMemoryId(mem.id);
                                setFormContent(mem.content);
                                setFormTags(mem.tags.join(", "));
                                setFormImportance(mem.importance);
                                setIsAddModalOpen(true);
                              }}
                              className="p-1 hover:text-white transition-colors"
                              title="Edit memory"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSoftDelete(mem.id)}
                              className="p-1 hover:text-amber-400 transition-colors"
                              title="Archive memory"
                            >
                              📦
                            </button>
                            <button
                              type="button"
                              onClick={() => handlePermanentDelete(mem.id)}
                              className="p-1 hover:text-rose-400 transition-colors"
                              title="Delete permanently"
                            >
                              🗑️
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: AUTONOMOUS CURATOR */}
        {/* ========================================================================= */}
        {activeTab === "curator" && (
          <div className="space-y-8">
            {/* Curator Hero / Trigger */}
            <div className="p-6 rounded-2xl bg-gradient-to-r from-purple-950/40 via-indigo-950/20 to-[#141d1d] border border-purple-800/40 flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <span>⚡</span> Autonomous Memory Curator
                </h2>
                <p className="text-xs text-[#95a8a8] mt-1 max-w-xl leading-relaxed">
                  The curator scans semantic entries, clusters related thoughts into unified concepts, summarizes aging scratchpads, and soft-deletes obsolete, unretrieved memories according to configured policy thresholds.
                </p>
              </div>

              <button
                type="button"
                disabled={curatorRunning}
                onClick={handleRunCurator}
                className="px-5 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg transition-all flex items-center justify-center gap-2 whitespace-nowrap disabled:opacity-50"
              >
                {curatorRunning ? (
                  <>
                    <span className="inline-block animate-spin">↻</span>
                    <span>Curating Vault...</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>Trigger Curator Pass</span>
                  </>
                )}
              </button>
            </div>

            {/* Split: Policy Configuration & Past Execution Reports */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Policy Configuration Card */}
              <div className="p-5 rounded-xl bg-[#141d1d] border border-[#273636] flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
                    <span>⚙️</span> Curator Policy Thresholds
                  </h3>

                  <form onSubmit={handleSavePolicy} className="space-y-4">
                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <label className="text-slate-300">Summarize After (Days):</label>
                        <span className="text-purple-400 font-semibold">{curatorPolicy.summarize_after_days}d</span>
                      </div>
                      <input
                        type="range"
                        min="7"
                        max="90"
                        value={curatorPolicy.summarize_after_days}
                        onChange={(e) =>
                          setCuratorPolicy({ ...curatorPolicy, summarize_after_days: Number(e.target.value) })
                        }
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <label className="text-slate-300">Cluster Minimum Size:</label>
                        <span className="text-purple-400 font-semibold">{curatorPolicy.cluster_min_size} memories</span>
                      </div>
                      <input
                        type="range"
                        min="2"
                        max="10"
                        value={curatorPolicy.cluster_min_size}
                        onChange={(e) =>
                          setCuratorPolicy({ ...curatorPolicy, cluster_min_size: Number(e.target.value) })
                        }
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <label className="text-slate-300">Soft-Delete Unretrieved After:</label>
                        <span className="text-purple-400 font-semibold">
                          {curatorPolicy.soft_delete_never_retrieved_days}d
                        </span>
                      </div>
                      <input
                        type="range"
                        min="30"
                        max="365"
                        value={curatorPolicy.soft_delete_never_retrieved_days}
                        onChange={(e) =>
                          setCuratorPolicy({
                            ...curatorPolicy,
                            soft_delete_never_retrieved_days: Number(e.target.value),
                          })
                        }
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div>
                      <div className="flex justify-between text-xs mb-1">
                        <label className="text-slate-300">Hard-Delete Archived After:</label>
                        <span className="text-purple-400 font-semibold">{curatorPolicy.hard_delete_after_days}d</span>
                      </div>
                      <input
                        type="range"
                        min="7"
                        max="180"
                        value={curatorPolicy.hard_delete_after_days}
                        onChange={(e) =>
                          setCuratorPolicy({ ...curatorPolicy, hard_delete_after_days: Number(e.target.value) })
                        }
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div className="flex items-center gap-2 pt-2">
                      <input
                        type="checkbox"
                        id="notifyChanges"
                        checked={curatorPolicy.notify_on_changes}
                        onChange={(e) =>
                          setCuratorPolicy({ ...curatorPolicy, notify_on_changes: e.target.checked })
                        }
                        className="rounded bg-[#0e1515] border-[#273636] text-purple-600 focus:ring-0"
                      />
                      <label htmlFor="notifyChanges" className="text-xs text-slate-300 cursor-pointer">
                        Notify in chat summary when curator performs automated pruning
                      </label>
                    </div>

                    <div className="pt-3">
                      <button
                        type="submit"
                        disabled={savingPolicy}
                        className="px-4 py-2 bg-purple-700 hover:bg-purple-600 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        {savingPolicy ? "Saving Policy..." : "Save Policy Config"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>

              {/* Execution Reports & Diff History */}
              <div className="p-5 rounded-xl bg-[#141d1d] border border-[#273636] flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
                    <span>📜</span> Curator Run History & Diff Logs
                  </h3>

                  {curatorReports.length === 0 ? (
                    <div className="py-12 text-center text-xs text-slate-500">
                      No past curator execution records. Trigger a pass above to generate an audit diff.
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
                      {curatorReports.map((r) => (
                        <div
                          key={r.id}
                          className="p-3.5 rounded-lg bg-[#0e1515] border border-[#273636] text-xs space-y-2"
                        >
                          <div className="flex items-center justify-between text-[11px] text-slate-400">
                            <span className="font-mono text-purple-300">
                              {r.created_at ? new Date(r.created_at).toLocaleString() : "Recent Run"}
                            </span>
                            <span className="px-2 py-0.5 rounded bg-teal-950 text-teal-300 border border-teal-800 text-[10px]">
                              {r.status}
                            </span>
                          </div>

                          <div className="flex items-center gap-3 text-[11px] text-slate-300">
                            <span>Scanned: {r.entries_scanned}</span>
                            <span>Summarized: {r.summarized_count}</span>
                            <span>Archived: {r.soft_deleted_count}</span>
                            <span>Duration: {r.duration_ms}ms</span>
                          </div>

                          {r.diff_summary && (
                            <div className="p-2 rounded bg-black/40 font-mono text-[11px] text-teal-300 border border-[#273636] break-words">
                              {r.diff_summary}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: RETRIEVAL INSPECTOR */}
        {/* ========================================================================= */}
        {activeTab === "retrieve" && (
          <div className="space-y-6">
            <div className="p-5 rounded-xl bg-[#141d1d] border border-[#273636]">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2 mb-2">
                <span>🔍</span> Real-Time Semantic Retrieval Test
              </h2>
              <p className="text-xs text-[#95a8a8] mb-4">
                Test how the backend hybrid retrieval engine evaluates relevance scores and retrieves memories for coordinator chat grounding.
              </p>

              <form onSubmit={handleRunRetrieval} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  placeholder="Enter a test prompt (e.g. 'what are my language preferences?')..."
                  value={retrievalQuery}
                  onChange={(e) => setRetrievalQuery(e.target.value)}
                  className="flex-1 px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                />
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Top K:</span>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                    className="w-16 px-2 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white"
                  />
                  <button
                    type="submit"
                    disabled={isRetrieving || !retrievalQuery.trim()}
                    className="px-4 py-2 bg-purple-700 hover:bg-purple-600 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50 whitespace-nowrap"
                  >
                    {isRetrieving ? "Scoring..." : "Run Query"}
                  </button>
                </div>
              </form>
            </div>

            {/* Retrieval Results Display */}
            {retrievalResults !== null && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold text-[#95a8a8] uppercase tracking-wider">
                  Candidate Matches ({retrievalResults.length})
                </h3>

                {retrievalResults.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-500 rounded-xl border border-dashed border-[#273636] bg-[#141d1d]/40">
                    No memories scored above the candidate relevance threshold for this query.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {retrievalResults.map((item, idx) => (
                      <div
                        key={item.entry_id || idx}
                        className="p-4 rounded-xl bg-[#141d1d] border border-[#273636] flex flex-col md:flex-row md:items-center justify-between gap-4"
                      >
                        <div className="flex-1 space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                              Rank #{idx + 1}
                            </span>
                            <span
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border uppercase ${getImportanceColor(
                                item.importance
                              )}`}
                            >
                              {item.importance}
                            </span>
                            {item.tags?.map((t) => (
                              <span
                                key={t}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-[#1a2525] text-teal-400 border border-[#273636]"
                              >
                                #{t}
                              </span>
                            ))}
                          </div>
                          <p className="text-xs text-slate-200 font-sans">{item.content}</p>
                        </div>

                        {/* Relevance Score Pill */}
                        <div className="flex items-center gap-3">
                          <div className="text-right">
                            <div className="text-xs font-mono font-bold text-teal-400">
                              {(item.score * 100).toFixed(1)}% match
                            </div>
                            <div className="text-[10px] text-slate-500 font-mono">
                              score: {item.score.toFixed(4)}
                            </div>
                          </div>
                          <div className="w-16 bg-[#0e1515] h-2 rounded-full overflow-hidden border border-[#273636]">
                            <div
                              className="bg-teal-500 h-full rounded-full"
                              style={{ width: `${Math.min(100, Math.max(10, item.score * 100))}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: PRIVACY & GDPR */}
        {/* ========================================================================= */}
        {activeTab === "privacy" && (
          <div className="space-y-6 max-w-4xl">
            {/* Export Card */}
            <div className="p-5 rounded-xl bg-[#141d1d] border border-[#273636] space-y-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>📦</span> GDPR Portable Data Export
              </h2>
              <p className="text-xs text-[#95a8a8] leading-relaxed">
                Download your complete semantic memory vault, including all active entries, tags, creation timestamps, importance ratings, and curator audit history in a standardized portable JSON package.
              </p>
              <button
                type="button"
                disabled={exporting}
                onClick={handleExportData}
                className="px-4 py-2 bg-teal-800 hover:bg-teal-700 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50 inline-flex items-center gap-2"
              >
                {exporting ? "Generating Package..." : "📥 Download Vault JSON Bundle"}
              </button>
            </div>

            {/* Erasure / Right to be Forgotten Card */}
            <div className="p-5 rounded-xl bg-rose-950/20 border border-rose-900/40 space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-rose-400 flex items-center gap-2">
                  <span>⚠️</span> Permanent Vault Erasure ("Right to be Forgotten")
                </h2>
                <p className="text-xs text-[#95a8a8] mt-1 leading-relaxed">
                  Permanently purge all long-term memories and curator reports from the database and vector indices. This action is irreversible and immediately wipes all personalized AI grounding context.
                </p>
              </div>

              <div className="space-y-3 pt-2">
                <p className="text-xs text-rose-300 font-medium">
                  To confirm, type <span className="font-mono bg-black/40 px-1 py-0.5 rounded">PURGE ALL MEMORIES</span> below:
                </p>
                <div className="flex flex-col sm:flex-row gap-3">
                  <input
                    type="text"
                    value={purgeInput}
                    onChange={(e) => setPurgeInput(e.target.value)}
                    placeholder="Type PURGE ALL MEMORIES..."
                    className="flex-1 max-w-md px-3 py-2 bg-[#0e1515] border border-rose-800/80 rounded-lg text-xs text-white placeholder-slate-600 focus:outline-none focus:border-rose-500 font-mono"
                  />
                  <button
                    type="button"
                    disabled={isPurging || purgeInput.trim() !== "PURGE ALL MEMORIES"}
                    onClick={handlePurgeAll}
                    className="px-4 py-2 bg-rose-700 hover:bg-rose-600 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                  >
                    {isPurging ? "Purging..." : "Permanently Erase All Data"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ========================================================================= */}
      {/* ADD / EDIT MEMORY MODAL */}
      {/* ========================================================================= */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#141d1d] border border-[#273636] rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#273636] pb-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span>{editingMemoryId ? "✏️ Edit Memory" : "➕ Store New Memory"}</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveMemory} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Memory Content:
                </label>
                <textarea
                  rows={4}
                  required
                  placeholder="e.g., User prefers responses in dark-mode friendly markdown tables..."
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Importance Level:
                  </label>
                  <select
                    value={formImportance}
                    onChange={(e) => setFormImportance(e.target.value as ImportanceLevel)}
                    className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="normal">Normal (Standard Context)</option>
                    <option value="high">High (Priority Retrieval)</option>
                    <option value="forever">Forever (Never Curated/Pruned)</option>
                    <option value="low">Low (Scratchpad/Temporary)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Tags (Comma-separated):
                  </label>
                  <input
                    type="text"
                    placeholder="preferences, ui, work"
                    value={formTags}
                    onChange={(e) => setFormTags(e.target.value)}
                    className="w-full px-3 py-2 bg-[#0e1515] border border-[#273636] rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <div className="border-t border-[#273636] pt-3 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 bg-[#1a2525] hover:bg-[#273636] text-slate-300 rounded-lg text-xs font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-lg text-xs font-medium transition-colors shadow-sm"
                >
                  {editingMemoryId ? "Update Memory" : "Save Memory"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
