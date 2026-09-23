import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Brain,
  ArrowLeft,
  Search,
  Plus,
  Pin,
  Trash2,
  Sparkles,
  RefreshCw,
  Download,
  ShieldAlert,
  Check,
  Copy,
  Send,
  Archive,
  RotateCcw,
  Sliders,
  Database,
  X,
} from 'lucide-react';
import './MemoryStudio.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export type ImportanceLevel = 'low' | 'normal' | 'high' | 'forever';

export interface MemoryItem {
  id: string;
  user_id: string;
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

export interface MemoryRetrieveItem {
  entry_id: string;
  content: string;
  importance: string;
  source: string;
  tags: string[];
  score: number;
  stored_at?: string | null;
}

export interface CuratorPolicyConfig {
  summarize_after_days: number;
  cluster_min_size: number;
  soft_delete_never_retrieved_days: number;
  hard_delete_after_days: number;
  notify_on_changes: boolean;
}

export interface CuratorRunReport {
  id: string;
  user_id: string;
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

export interface MemoryStats {
  total_memories: number;
  active_memories: number;
  forever_memories: number;
  soft_deleted_memories: number;
  curator_runs_count: number;
  last_curated_at?: string | null;
}

interface MemoryStudioProps {
  onBack?: () => void;
  accessToken?: string | null;
  onSendToChat?: (text: string) => void;
}

export const MemoryStudio: React.FC<MemoryStudioProps> = ({
  onBack,
  accessToken,
  onSendToChat,
}) => {
  const [activeTab, setActiveTab] = useState<'vault' | 'curator' | 'privacy'>('vault');

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
  const [searchQuery, setSearchQuery] = useState('');
  const [importanceFilter, setImportanceFilter] = useState<string>('all');
  const [includeArchived, setIncludeArchived] = useState(false);

  // Semantic Retrieval Testing
  const [showRetrievalTest, setShowRetrievalTest] = useState(false);
  const [retrievalQuery, setRetrievalQuery] = useState('');
  const [retrievalResults, setRetrievalResults] = useState<MemoryRetrieveItem[] | null>(null);
  const [isRetrieving, setIsRetrieving] = useState(false);

  // Modal State (Add / Edit)
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [formContent, setFormContent] = useState('');
  const [formImportance, setFormImportance] = useState<ImportanceLevel>('normal');
  const [formTags, setFormTags] = useState('');

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

  // Privacy Tab State
  const [purgeInput, setPurgeInput] = useState('');
  const [isPurging, setIsPurging] = useState(false);

  // Notifications
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const showToast = useCallback((type: 'success' | 'error', message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const authHeaders = useMemo(() => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }
    return headers;
  }, [accessToken]);

  // 1. Fetch Memories
  const fetchMemories = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const url = `${API_BASE}/memory/entries?include_soft_deleted=${includeArchived}&limit=100`;
      const res = await fetch(url, { headers: authHeaders });
      if (!res.ok) throw new Error(`Failed to fetch memories: ${res.statusText}`);
      const data = await res.json();
      const items: MemoryItem[] = Array.isArray(data) ? data : (data.entries || []);
      setMemories(items);
    } catch (err: any) {
      const msg = err.message || 'Error loading memories';
      setFetchError(msg);
      showToast('error', msg);
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
        fetch(`${API_BASE}/memory/curator/reports?limit=10`, { headers: authHeaders }),
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
    if (activeTab === 'curator') {
      fetchCuratorData();
    }
  }, [fetchMemories, fetchStats, fetchCuratorData, activeTab]);

  // Create or Update Memory
  const handleSaveMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formContent.trim()) {
      showToast('error', 'Memory content cannot be empty.');
      return;
    }

    const tags = formTags
      .split(',')
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);

    try {
      if (editingMemoryId) {
        // PATCH
        const res = await fetch(`${API_BASE}/memory/entries/${editingMemoryId}`, {
          method: 'PATCH',
          headers: authHeaders,
          body: JSON.stringify({
            content: formContent.trim(),
            importance: formImportance,
            tags,
          }),
        });
        if (!res.ok) throw new Error('Failed to update memory');
        showToast('success', 'Memory updated successfully.');
      } else {
        // POST
        const res = await fetch(`${API_BASE}/memory/entries`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            content: formContent.trim(),
            importance: formImportance,
            tags,
            source: 'user:explicit',
          }),
        });
        if (!res.ok) throw new Error('Failed to create memory');
        showToast('success', 'Memory stored in vault.');
      }

      setIsModalOpen(false);
      setEditingMemoryId(null);
      setFormContent('');
      setFormTags('');
      setFormImportance('normal');
      fetchMemories();
      fetchStats();
    } catch (err: any) {
      showToast('error', err.message || 'Action failed.');
    }
  };

  // Toggle Forever Importance (Optimistic with rollback)
  const handleToggleForever = async (mem: MemoryItem) => {
    const nextImportance: ImportanceLevel = mem.importance === 'forever' ? 'normal' : 'forever';
    const previous = [...memories];
    setMemories((prev) =>
      prev.map((m) => (m.id === mem.id ? { ...m, importance: nextImportance } : m))
    );
    try {
      const res = await fetch(`${API_BASE}/memory/entries/${mem.id}`, {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({ importance: nextImportance }),
      });
      if (!res.ok) throw new Error('Failed to toggle pin');
      showToast(
        'success',
        nextImportance === 'forever' ? 'Pinned as Forever Memory.' : 'Unpinned from Forever.'
      );
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast('error', err.message || 'Failed to update memory pin.');
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
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error('Failed to archive memory');
      showToast('success', 'Memory moved to soft-delete archive.');
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast('error', err.message || 'Failed to archive memory.');
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
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error('Failed to restore memory');
      showToast('success', 'Memory restored to active vault.');
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast('error', err.message || 'Failed to restore memory.');
    }
  };

  // Permanent Delete (Optimistic with rollback)
  const handlePermanentDelete = async (id: string) => {
    const previous = [...memories];
    setMemories((prev) => prev.filter((m) => m.id !== id));
    try {
      const res = await fetch(`${API_BASE}/memory/entries/${id}?permanent=true`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error('Failed to delete memory permanently');
      showToast('success', 'Memory permanently purged.');
      fetchStats();
    } catch (err: any) {
      setMemories(previous);
      showToast('error', err.message || 'Failed to delete memory.');
    }
  };

  // Semantic Retrieval Search
  const handleRunRetrieval = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!retrievalQuery.trim()) return;

    setIsRetrieving(true);
    try {
      const res = await fetch(`${API_BASE}/memory/retrieve`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          query: retrievalQuery.trim(),
          top_k: 8,
          min_score: 0.1,
        }),
      });
      if (!res.ok) throw new Error('Retrieval query failed');
      const data = await res.json();
      setRetrievalResults(data.entries || []);
    } catch (err: any) {
      showToast('error', err.message);
    } finally {
      setIsRetrieving(false);
    }
  };

  // Run Autonomous Curator On-Demand
  const handleRunCurator = async () => {
    setCuratorRunning(true);
    try {
      const res = await fetch(`${API_BASE}/memory/curator/run`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error('Curator pass failed');
      const report: CuratorRunReport = await res.json();
      showToast('success', `Curator completed: ${report.diff_summary}`);
      fetchCuratorData();
      fetchMemories();
      fetchStats();
    } catch (err: any) {
      showToast('error', err.message || 'Curator pass error');
    } finally {
      setCuratorRunning(false);
    }
  };

  // Save Curator Policy
  const handleSavePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/memory/curator/policy`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify(curatorPolicy),
      });
      if (!res.ok) throw new Error('Failed to update curator policy');
      showToast('success', 'Curator policy thresholds updated.');
    } catch (err: any) {
      showToast('error', err.message);
    }
  };

  // Export Data Archive
  const handleExportData = async () => {
    try {
      const res = await fetch(`${API_BASE}/memory/export`, { headers: authHeaders });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `roxy_memory_vault_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      showToast('success', 'Memory vault archive downloaded.');
    } catch (err: any) {
      showToast('error', err.message);
    }
  };

  // Purge All Memories (GDPR Erasure)
  const handlePurgeAll = async () => {
    if (purgeInput.trim() !== 'PURGE ALL MEMORIES') {
      showToast('error', 'Please type "PURGE ALL MEMORIES" exactly to confirm.');
      return;
    }
    setIsPurging(true);
    try {
      const res = await fetch(`${API_BASE}/memory/purge-all`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error('Purge failed');
      const data = await res.json();
      const purged = data.purged_count ?? data.deleted_count ?? 0;
      showToast('success', `Purged ${purged} memories permanently.`);
      setPurgeInput('');
      fetchMemories();
      fetchStats();
    } catch (err: any) {
      showToast('error', err.message);
    } finally {
      setIsPurging(false);
    }
  };

  // Copy Content Helper
  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Filtered Memories
  const filteredMemories = useMemo(() => {
    return memories.filter((m) => {
      if (importanceFilter !== 'all' && m.importance !== importanceFilter) {
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
  }, [memories, importanceFilter, searchQuery]);

  return (
    <div className="memory-studio">
      {/* Header */}
      <header className="memory-studio__header">
        <div className="memory-studio__header-left">
          {onBack && (
            <button
              type="button"
              className="memory-studio__back-btn"
              onClick={onBack}
              aria-label="Back to chat"
            >
              <ArrowLeft size={16} />
              <span>Back to Chat</span>
            </button>
          )}
          <h1 className="memory-studio__title">
            <Brain size={26} color="#a855f7" />
            <span>Semantic Memory & Curator Studio</span>
          </h1>
          <p className="memory-studio__desc">
            Autonomous cross-session knowledge recall, semantic facts vault, self-healing memory clustering,
            and GDPR privacy controls.
          </p>
        </div>

        {/* Stats Telemetry */}
        <div className="memory-studio__stats-bar">
          <div className="memory-studio__stat-chip">
            <span className="memory-studio__stat-val active">{stats.active_memories}</span>
            <span className="memory-studio__stat-lbl">Active</span>
          </div>
          <div className="memory-studio__stat-chip">
            <span className="memory-studio__stat-val forever">{stats.forever_memories}</span>
            <span className="memory-studio__stat-lbl">Forever</span>
          </div>
          <div className="memory-studio__stat-chip">
            <span className="memory-studio__stat-val archived">{stats.soft_deleted_memories}</span>
            <span className="memory-studio__stat-lbl">Archived</span>
          </div>
          <div className="memory-studio__stat-chip">
            <span className="memory-studio__stat-val curator">{stats.curator_runs_count}</span>
            <span className="memory-studio__stat-lbl">Curator Runs</span>
          </div>
        </div>
      </header>

      {!accessToken && (
        <div className="memory-studio__auth-banner" role="status">
          <span>ℹ️ You are viewing Memory Studio in guest mode. Sign in to synchronize your semantic memory vault across sessions and enable autonomous curator passes.</span>
        </div>
      )}

      {fetchError && (
        <div className="memory-studio__error-banner" role="alert">
          <span>⚠️ {fetchError}</span>
          <button
            type="button"
            className="memory-studio__retry-btn"
            onClick={() => {
              fetchMemories();
              fetchStats();
              if (activeTab === 'curator') fetchCuratorData();
            }}
          >
            ↻ Retry Connection
          </button>
        </div>
      )}

      {/* Tabs */}
      <nav className="memory-studio__tabs" aria-label="Memory Studio Sections">
        <button
          type="button"
          className={`memory-studio__tab-btn ${activeTab === 'vault' ? 'memory-studio__tab-btn--active' : ''}`}
          onClick={() => setActiveTab('vault')}
        >
          <Database size={16} />
          <span>Semantic Memory Vault</span>
        </button>
        <button
          type="button"
          className={`memory-studio__tab-btn ${activeTab === 'curator' ? 'memory-studio__tab-btn--active' : ''}`}
          onClick={() => setActiveTab('curator')}
        >
          <Sparkles size={16} />
          <span>Curator Agent & Audit</span>
        </button>
        <button
          type="button"
          className={`memory-studio__tab-btn ${activeTab === 'privacy' ? 'memory-studio__tab-btn--active' : ''}`}
          onClick={() => setActiveTab('privacy')}
        >
          <ShieldAlert size={16} />
          <span>Privacy & GDPR Export</span>
        </button>
      </nav>

      {/* Alert / Toast */}
      {toast && (
        <div className={`memory-studio__toast memory-studio__toast--${toast.type}`} role="status">
          <span>{toast.message}</span>
          <button
            type="button"
            className="memory-studio__icon-btn"
            onClick={() => setToast(null)}
            aria-label="Dismiss alert"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* TAB 1: MEMORY VAULT */}
      {activeTab === 'vault' && (
        <main>
          {/* Controls Bar */}
          <div className="memory-studio__vault-controls">
            <div className="memory-studio__search-bar">
              <Search size={16} color="#9ca3af" />
              <input
                type="text"
                placeholder="Search memories or tags..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="memory-studio__icon-btn"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <div className="memory-studio__filters">
              <select
                className="memory-studio__select"
                value={importanceFilter}
                onChange={(e) => setImportanceFilter(e.target.value)}
                aria-label="Filter by importance"
              >
                <option value="all">All Importance</option>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="forever">Forever Only</option>
              </select>

              <label className="memory-studio__toggle-lbl">
                <input
                  type="checkbox"
                  checked={includeArchived}
                  onChange={(e) => setIncludeArchived(e.target.checked)}
                />
                <span>Include Archived</span>
              </label>

              <button
                type="button"
                className="memory-studio__btn-secondary"
                onClick={() => setShowRetrievalTest((v) => !v)}
              >
                <Sparkles size={14} />
                <span>{showRetrievalTest ? 'Close Test' : 'Test Retrieval'}</span>
              </button>

              <button
                type="button"
                className="memory-studio__btn-primary"
                onClick={() => {
                  setEditingMemoryId(null);
                  setFormContent('');
                  setFormTags('');
                  setFormImportance('normal');
                  setIsModalOpen(true);
                }}
              >
                <Plus size={16} />
                <span>Add Memory</span>
              </button>
            </div>
          </div>

          {/* Test Retrieval Panel */}
          {showRetrievalTest && (
            <section className="memory-studio__retrieval-box" aria-label="Semantic Retrieval Test">
              <div className="memory-studio__retrieval-header">
                <span className="memory-studio__retrieval-title">
                  <Sparkles size={16} />
                  <span>Semantic Relevance & Scoring Inspector</span>
                </span>
                <button
                  type="button"
                  className="memory-studio__icon-btn"
                  onClick={() => setShowRetrievalTest(false)}
                  aria-label="Close"
                >
                  <X size={14} />
                </button>
              </div>
              <form onSubmit={handleRunRetrieval} className="memory-studio__retrieval-form">
                <input
                  type="text"
                  className="memory-studio__retrieval-input"
                  placeholder="Enter a prompt, question, or keyword to test memory recall..."
                  value={retrievalQuery}
                  onChange={(e) => setRetrievalQuery(e.target.value)}
                />
                <button
                  type="submit"
                  className="memory-studio__btn-primary"
                  disabled={isRetrieving || !retrievalQuery.trim()}
                >
                  {isRetrieving ? 'Searching...' : 'Score Recall'}
                </button>
              </form>

              {retrievalResults && (
                <div className="memory-studio__retrieval-results">
                  {retrievalResults.length === 0 ? (
                    <p style={{ color: '#9ca3af', fontSize: '0.88rem', margin: '0.5rem 0 0 0' }}>
                      No relevant memories matched this query threshold.
                    </p>
                  ) : (
                    retrievalResults.map((item) => (
                      <div key={item.entry_id} className="memory-studio__retrieval-item">
                        <div style={{ flex: 1 }}>
                          <span style={{ fontSize: '0.9rem', color: '#f3f4f6' }}>{item.content}</span>
                          <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.3rem' }}>
                            {item.tags.map((t) => (
                              <span key={t} className="memory-studio__tag-pill">
                                #{t}
                              </span>
                            ))}
                          </div>
                        </div>
                        <span className="memory-studio__retrieval-score">
                          Score: {(item.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </section>
          )}

          {/* Memories Grid or Zero-State */}
          {loading ? (
            <div className="memory-studio__empty">
              <RefreshCw className="memory-studio__empty-icon" style={{ animation: 'spin 1.5s linear infinite' }} />
              <p className="memory-studio__empty-title">Loading semantic memories...</p>
            </div>
          ) : filteredMemories.length === 0 ? (
            <div className="memory-studio__empty">
              <Brain className="memory-studio__empty-icon" />
              <h3 className="memory-studio__empty-title">
                {searchQuery ? 'No matching memories found' : 'Your Memory Vault is empty'}
              </h3>
              <p className="memory-studio__empty-desc">
                {searchQuery
                  ? 'Try searching with different keywords or clearing your filters.'
                  : 'Explicitly store your preferences, guidelines, or facts—or chat with ROXY and ask her to remember things for you!'}
              </p>
              {!searchQuery && (
                <button
                  type="button"
                  className="memory-studio__btn-primary"
                  onClick={() => {
                    setEditingMemoryId(null);
                    setFormContent('');
                    setFormTags('');
                    setFormImportance('normal');
                    setIsModalOpen(true);
                  }}
                >
                  <Plus size={16} />
                  <span>Store First Memory</span>
                </button>
              )}
            </div>
          ) : (
            <div className="memory-studio__grid">
              {filteredMemories.map((mem) => (
                <article
                  key={mem.id}
                  className={`memory-studio__card ${mem.is_soft_deleted ? 'memory-studio__card--archived' : ''}`}
                >
                  <div>
                    <div className="memory-studio__card-top">
                      <div className="memory-studio__badges">
                        <span className={`memory-studio__badge memory-studio__badge--${mem.importance}`}>
                          {mem.importance}
                        </span>
                        <span className="memory-studio__badge memory-studio__badge--source">
                          {mem.source}
                        </span>
                        {mem.is_soft_deleted && (
                          <span className="memory-studio__badge memory-studio__badge--archived">
                            Archived
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        className="memory-studio__icon-btn"
                        onClick={() => handleToggleForever(mem)}
                        title={mem.importance === 'forever' ? 'Unpin forever' : 'Pin forever (exempt from pruning)'}
                        aria-label="Toggle pin forever"
                      >
                        <Pin
                          size={15}
                          color={mem.importance === 'forever' ? '#c084fc' : '#9ca3af'}
                          fill={mem.importance === 'forever' ? '#c084fc' : 'none'}
                        />
                      </button>
                    </div>

                    <p className="memory-studio__content">{mem.content}</p>

                    {mem.tags.length > 0 && (
                      <div className="memory-studio__tags">
                        {mem.tags.map((t) => (
                          <span key={t} className="memory-studio__tag-pill">
                            #{t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="memory-studio__meta-row">
                      <span>Recalls: {mem.retrieval_count}x</span>
                      <div className="memory-studio__card-actions">
                        <button
                          type="button"
                          className="memory-studio__icon-btn"
                          onClick={() => handleCopy(mem.id, mem.content)}
                          title="Copy memory content"
                          aria-label="Copy"
                        >
                          {copiedId === mem.id ? <Check size={14} color="#34d399" /> : <Copy size={14} />}
                        </button>

                        {onSendToChat && (
                          <button
                            type="button"
                            className="memory-studio__icon-btn"
                            onClick={() => onSendToChat(`Regarding my stored memory: "${mem.content}"`)}
                            title="Send context to Chat"
                            aria-label="Send to chat"
                          >
                            <Send size={14} />
                          </button>
                        )}

                        {!mem.is_soft_deleted ? (
                          <>
                            <button
                              type="button"
                              className="memory-studio__icon-btn"
                              onClick={() => {
                                setEditingMemoryId(mem.id);
                                setFormContent(mem.content);
                                setFormImportance(mem.importance);
                                setFormTags(mem.tags.join(', '));
                                setIsModalOpen(true);
                              }}
                              title="Edit memory"
                              aria-label="Edit"
                            >
                              <Sliders size={14} />
                            </button>
                            <button
                              type="button"
                              className="memory-studio__icon-btn memory-studio__icon-btn--danger"
                              onClick={() => handleSoftDelete(mem.id)}
                              title="Archive memory (soft delete)"
                              aria-label="Archive"
                            >
                              <Archive size={14} />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="memory-studio__icon-btn"
                              onClick={() => handleRestore(mem.id)}
                              title="Restore to active vault"
                              aria-label="Restore"
                            >
                              <RotateCcw size={14} color="#34d399" />
                            </button>
                            <button
                              type="button"
                              className="memory-studio__icon-btn memory-studio__icon-btn--danger"
                              onClick={() => handlePermanentDelete(mem.id)}
                              title="Permanently delete"
                              aria-label="Delete permanently"
                            >
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </main>
      )}

      {/* TAB 2: CURATOR AUDIT & POLICY */}
      {activeTab === 'curator' && (
        <section className="memory-studio__curator-wrap">
          {/* Curator Agent Hero */}
          <div className="memory-studio__curator-hero">
            <div className="memory-studio__curator-hero-info">
              <h2 className="memory-studio__curator-hero-title">
                <Sparkles size={20} />
                <span>Autonomous Memory Curator Agent</span>
              </h2>
              <p className="memory-studio__curator-hero-desc">
                The Curator agent runs in the background to cluster semantic similarities, summarize older memories,
                and safely prune outdated entries after their retention grace period. Memories marked as{' '}
                <strong style={{ color: '#c084fc' }}>Forever</strong> are completely immune to automated pruning.
              </p>
            </div>
            <button
              type="button"
              className="memory-studio__btn-primary"
              onClick={handleRunCurator}
              disabled={curatorRunning}
            >
              <RefreshCw
                size={16}
                style={curatorRunning ? { animation: 'spin 1.5s linear infinite' } : undefined}
              />
              <span>{curatorRunning ? 'Curating Memory Vault...' : 'Run Curator Pass Now'}</span>
            </button>
          </div>

          <div className="memory-studio__curator-grid">
            {/* Policy Settings Form */}
            <div className="memory-studio__section-card">
              <h3 className="memory-studio__section-title">
                <Sliders size={18} color="#818cf8" />
                <span>Curator Policy & Thresholds</span>
              </h3>
              <form onSubmit={handleSavePolicy} className="memory-studio__policy-form">
                <div className="memory-studio__field">
                  <label htmlFor="summarize-days">Summarize Older Entries (Days)</label>
                  <input
                    id="summarize-days"
                    type="number"
                    min="1"
                    max="365"
                    value={curatorPolicy.summarize_after_days}
                    onChange={(e) =>
                      setCuratorPolicy({ ...curatorPolicy, summarize_after_days: Number(e.target.value) })
                    }
                  />
                </div>

                <div className="memory-studio__field">
                  <label htmlFor="cluster-size">Cluster Minimum Items Threshold</label>
                  <input
                    id="cluster-size"
                    type="number"
                    min="2"
                    max="20"
                    value={curatorPolicy.cluster_min_size}
                    onChange={(e) =>
                      setCuratorPolicy({ ...curatorPolicy, cluster_min_size: Number(e.target.value) })
                    }
                  />
                </div>

                <div className="memory-studio__field">
                  <label htmlFor="soft-delete-days">Archive Never-Retrieved Entries (Days)</label>
                  <input
                    id="soft-delete-days"
                    type="number"
                    min="7"
                    max="730"
                    value={curatorPolicy.soft_delete_never_retrieved_days}
                    onChange={(e) =>
                      setCuratorPolicy({
                        ...curatorPolicy,
                        soft_delete_never_retrieved_days: Number(e.target.value),
                      })
                    }
                  />
                </div>

                <div className="memory-studio__field">
                  <label htmlFor="hard-delete-days">Permanent Purge Grace Period (Days)</label>
                  <input
                    id="hard-delete-days"
                    type="number"
                    min="1"
                    max="365"
                    value={curatorPolicy.hard_delete_after_days}
                    onChange={(e) =>
                      setCuratorPolicy({
                        ...curatorPolicy,
                        hard_delete_after_days: Number(e.target.value),
                      })
                    }
                  />
                </div>

                <button type="submit" className="memory-studio__btn-secondary" style={{ width: 'fit-content' }}>
                  <span>Save Policy Thresholds</span>
                </button>
              </form>
            </div>

            {/* Run Reports History */}
            <div className="memory-studio__section-card">
              <h3 className="memory-studio__section-title">
                <RefreshCw size={18} color="#34d399" />
                <span>Curator Execution Reports</span>
              </h3>
              {curatorReports.length === 0 ? (
                <p style={{ color: '#9ca3af', fontSize: '0.88rem' }}>
                  No curator runs recorded yet. Trigger a pass above to start audit tracking.
                </p>
              ) : (
                <div className="memory-studio__reports-list">
                  {curatorReports.map((report) => (
                    <div key={report.id} className="memory-studio__report-item">
                      <div className="memory-studio__report-top">
                        <span style={{ fontWeight: 600, color: '#e5e7eb' }}>
                          Pass: {report.status.toUpperCase()}
                        </span>
                        <span>{report.duration_ms}ms</span>
                      </div>
                      <div className="memory-studio__report-metrics">
                        <span>Scanned: {report.entries_scanned}</span>
                        <span>Summarized: {report.summarized_count}</span>
                        <span>Archived: {report.soft_deleted_count}</span>
                        <span>Purged: {report.hard_deleted_count}</span>
                      </div>
                      {report.diff_summary && (
                        <div className="memory-studio__report-diff">{report.diff_summary}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* TAB 3: PRIVACY & DATA EXPORT */}
      {activeTab === 'privacy' && (
        <section className="memory-studio__privacy-wrap">
          {/* GDPR Portability */}
          <div className="memory-studio__privacy-card">
            <h3 className="memory-studio__section-title">
              <Download size={18} color="#38bdf8" />
              <span>Data Portability & Export (GDPR Article 20)</span>
            </h3>
            <p style={{ color: '#9ca3af', fontSize: '0.9rem', margin: 0, lineHeight: 1.5 }}>
              Export all stored semantic memories, active preferences, soft-deleted archive records, and curator
              audit logs in an open, portable JSON format.
            </p>
            <button
              type="button"
              className="memory-studio__btn-secondary"
              onClick={handleExportData}
              style={{ width: 'fit-content' }}
            >
              <Download size={15} />
              <span>Download Memory Vault Archive (.json)</span>
            </button>
          </div>

          {/* Right to Erasure / Purge All */}
          <div className="memory-studio__privacy-card memory-studio__privacy-card--danger">
            <h3 className="memory-studio__danger-title">
              <ShieldAlert size={20} />
              <span>Permanent Erasure & Vault Purge (GDPR Article 17)</span>
            </h3>
            <p style={{ color: '#fca5a5', fontSize: '0.9rem', margin: 0, lineHeight: 1.5 }}>
              Permanently and irreversibly wipe all active memories, pinned forever memories, and curator run reports
              associated with your account.
            </p>
            <div className="memory-studio__purge-box">
              <label htmlFor="purge-confirm" style={{ fontSize: '0.85rem', color: '#e5e7eb' }}>
                Type <strong style={{ color: '#ef4444' }}>PURGE ALL MEMORIES</strong> below to confirm:
              </label>
              <input
                id="purge-confirm"
                type="text"
                className="memory-studio__purge-confirm-input"
                placeholder="PURGE ALL MEMORIES"
                value={purgeInput}
                onChange={(e) => setPurgeInput(e.target.value)}
              />
              <button
                type="button"
                className="memory-studio__btn-danger"
                disabled={purgeInput.trim() !== 'PURGE ALL MEMORIES' || isPurging}
                onClick={handlePurgeAll}
              >
                {isPurging ? 'Erasing Vault...' : 'Irreversibly Purge All Memories'}
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Modal: Add or Edit Memory */}
      {isModalOpen && (
        <div className="memory-studio__modal-overlay">
          <div className="memory-studio__modal">
            <div className="memory-studio__modal-header">
              <h3 className="memory-studio__modal-title">
                {editingMemoryId ? 'Edit Semantic Memory' : 'Store New Memory'}
              </h3>
              <button
                type="button"
                className="memory-studio__modal-close"
                onClick={() => setIsModalOpen(false)}
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleSaveMemory} className="memory-studio__policy-form">
              <div className="memory-studio__field">
                <label htmlFor="memory-content">Memory Content / Fact *</label>
                <textarea
                  id="memory-content"
                  rows={4}
                  placeholder="e.g., I prefer concise Python code with strict typing and no third-party libraries..."
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  required
                />
              </div>

              <div className="memory-studio__field">
                <label htmlFor="memory-importance">Importance Level</label>
                <select
                  id="memory-importance"
                  className="memory-studio__select"
                  value={formImportance}
                  onChange={(e) => setFormImportance(e.target.value as ImportanceLevel)}
                >
                  <option value="low">Low (Standard pruning candidate)</option>
                  <option value="normal">Normal (Default cross-session recall)</option>
                  <option value="high">High (Priority retrieval weight)</option>
                  <option value="forever">Forever (Immune to automated curator pruning)</option>
                </select>
              </div>

              <div className="memory-studio__field">
                <label htmlFor="memory-tags">Tags (Comma-separated)</label>
                <input
                  id="memory-tags"
                  type="text"
                  placeholder="python, preferences, coding, work"
                  value={formTags}
                  onChange={(e) => setFormTags(e.target.value)}
                />
              </div>

              <div className="memory-studio__modal-footer">
                <button
                  type="button"
                  className="memory-studio__btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="memory-studio__btn-primary">
                  {editingMemoryId ? 'Save Changes' : 'Store Memory'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
