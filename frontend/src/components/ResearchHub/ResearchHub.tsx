import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Globe,
  Search,
  Sparkles,
  ExternalLink,
  BookOpen,
  CheckCircle2,
  Trash2,
  Copy,
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  Layers,
  Send,
  RefreshCw,
  Tag,
  FileText,
  Link2,
  XCircle,
} from 'lucide-react';
import { VoiceInputControl } from '../common/VoiceInputControl';
import './ResearchHub.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface SourceItem {
  index: number;
  title: string;
  url: string;
  snippet?: string;
  score?: number;
}

export interface ResearchReportItem {
  id: string;
  user_id: string;
  title: string;
  query: string;
  summary: string;
  findings: string[];
  sources: SourceItem[];
  confidence: 'high' | 'medium' | 'low' | string;
  depth: 'quick' | 'deep' | 'academic' | string;
  tags: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

interface DeepResearchResponse {
  report_id: string | null;
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

interface ResearchHubProps {
  accessToken?: string | null;
  onBack: () => void;
  onSendToChat?: (text: string) => void;
}

async function fetchJSON<T>(
  url: string,
  accessToken: string | null | undefined,
  options?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const PRESET_TOPICS = [
  'DeepSeek R1 reasoning architecture vs OpenAI o3 methods',
  'PostgreSQL vs ClickHouse for high-throughput analytics',
  'Commercial fusion energy breakthroughs and pilot plants 2026',
  'Solid-state battery commercialization timeline and benchmarks',
];

export const ResearchHub: React.FC<ResearchHubProps> = ({
  accessToken,
  onBack,
  onSendToChat,
}) => {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<'deep_research' | 'saved_reports' | 'url_fetch'>('deep_research');

  // Deep Research Launcher State
  const [query, setQuery] = useState('');
  const [depth, setDepth] = useState<'quick' | 'deep' | 'academic'>('deep');
  const [autoSave, setAutoSave] = useState(true);
  const [customTags, setCustomTags] = useState('');
  const [isResearching, setIsResearching] = useState(false);
  const [researchStage, setResearchStage] = useState<string>('');
  const [activeReport, setActiveReport] = useState<ResearchReportItem | DeepResearchResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toastNotice, setToastNotice] = useState<string | null>(null);

  // Saved Reports State
  const [savedReports, setSavedReports] = useState<ResearchReportItem[]>([]);
  const [isLoadingReports, setIsLoadingReports] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // URL Fetcher State
  const [fetchUrl, setFetchUrl] = useState('');
  const [isFetchingUrl, setIsFetchingUrl] = useState(false);
  const [urlFetchResult, setUrlFetchResult] = useState<WebFetchResponse | null>(null);

  // Load Saved Reports
  const loadReports = useCallback(async () => {
    setIsLoadingReports(true);
    setFetchError(null);
    try {
      const data = await fetchJSON<{ reports: ResearchReportItem[]; total: number }>(
        `${API_BASE}/research`,
        accessToken,
      );
      setSavedReports(data.reports || []);
    } catch {
      setFetchError('Unable to retrieve research reports. Check connection or backend status.');
    } finally {
      setIsLoadingReports(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  // Flash Toast Notice
  const showToast = (msg: string) => {
    setToastNotice(msg);
    setTimeout(() => setToastNotice(null), 3000);
  };

  const [interimQuery, setInterimQuery] = useState('');
  const abortControllerRef = React.useRef<AbortController | null>(null);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Cancel active research
  const handleCancelResearch = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsResearching(false);
    setResearchStage('');
    setErrorMsg('Research cancelled by user.');
  };

  // Launch Deep Research Pipeline
  const handleLaunchResearch = async (searchQuery?: string) => {
    const targetQuery = searchQuery || query;
    if (!targetQuery.trim() || isResearching) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    setIsResearching(true);
    setErrorMsg(null);
    setActiveReport(null);

    // Concise progress states per Phase 15:
    // "Searching sources..." -> "Analyzing sources..." -> "Preparing answer..."
    setResearchStage('Searching sources...');
    const t1 = setTimeout(() => setResearchStage('Analyzing sources...'), 2000);
    const t2 = setTimeout(() => setResearchStage('Preparing answer...'), 5000);

    try {
      const tagsList = customTags
        .split(',')
        .map((t) => t.trim().toLowerCase().replace(/^#/, ''))
        .filter(Boolean);

      const resp = await fetchJSON<DeepResearchResponse>(
        `${API_BASE}/research/deep-research`,
        accessToken,
        {
          method: 'POST',
          signal: abortCtrl.signal,
          body: JSON.stringify({
            query: targetQuery,
            depth,
            save_report: autoSave,
            tags: tagsList.length ? tagsList : undefined,
          }),
        },
      );

      setActiveReport(resp);
      showToast('Research investigation synthesized successfully!');
      if (autoSave) {
        void loadReports();
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        setErrorMsg('Research cancelled.');
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Research failed: ${msg}`);
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setIsResearching(false);
      setResearchStage('');
      abortControllerRef.current = null;
    }
  };

  // Save current active unsaved report
  const handleSaveActiveReport = async () => {
    if (!activeReport) return;
    try {
      const res = await fetchJSON<{ report: ResearchReportItem }>(
        `${API_BASE}/research`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({
            title: activeReport.title,
            query: activeReport.query,
            summary: activeReport.summary,
            findings: activeReport.findings,
            sources: activeReport.sources,
            confidence: activeReport.confidence,
            depth: activeReport.depth,
            tags: ['investigation', 'saved'],
          }),
        },
      );
      showToast('Report saved to your library!');
      void loadReports();
      setActiveReport(res.report);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Failed to save report: ${msg}`);
    }
  };

  // Delete saved report
  const handleDeleteReport = async (reportId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const prev = [...savedReports];
    setSavedReports((curr) => curr.filter((r) => r.id !== reportId));
    if (activeReport && 'id' in activeReport && activeReport.id === reportId) {
      setActiveReport(null);
    }
    try {
      await fetchJSON<{ status: string }>(
        `${API_BASE}/research/${reportId}`,
        accessToken,
        { method: 'DELETE' },
      );
      showToast('Report deleted.');
    } catch (err: unknown) {
      setSavedReports(prev);
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Failed to delete report: ${msg}. Changes rolled back.`);
    }
  };

  // Copy report summary as markdown
  const handleCopyReport = (report: ResearchReportItem | DeepResearchResponse) => {
    const md = [
      `# ${report.title}`,
      `**Research Query:** ${report.query}`,
      `**Confidence:** ${report.confidence.toUpperCase()} | **Depth:** ${report.depth.toUpperCase()}`,
      '',
      '## Executive Summary',
      report.summary,
      '',
      '## Key Findings',
      ...report.findings.map((f, i) => `${i + 1}. ${f}`),
      '',
      '## Verified Sources',
      ...report.sources.map((s) => `[${s.index}] [${s.title}](${s.url})`),
      '',
      '_Synthesized autonomously by ROXY Deep Research Engine._',
    ].join('\n');

    void navigator.clipboard.writeText(md);
    showToast('Report markdown copied to clipboard!');
  };

  // Send report to chat coordinator
  const handleSendToChatCoordinator = (report: ResearchReportItem | DeepResearchResponse) => {
    if (!onSendToChat) return;
    const text = `I am reviewing the research report on "${report.title}". Key summary: ${report.summary}. Can you help me analyze its strategic implications?`;
    onSendToChat(text);
  };

  // Fetch URL content directly
  const handleFetchUrl = async () => {
    if (!fetchUrl.trim() || isFetchingUrl) return;
    setIsFetchingUrl(true);
    setUrlFetchResult(null);
    setErrorMsg(null);
    try {
      const res = await fetchJSON<WebFetchResponse>(
        `${API_BASE}/research/fetch-url`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({ url: fetchUrl.trim(), max_chars: 6000 }),
        },
      );
      setUrlFetchResult(res);
      showToast('Webpage extracted successfully!');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Failed to fetch URL: ${msg}`);
    } finally {
      setIsFetchingUrl(false);
    }
  };

  // Derived tags for filter pills
  const allTags = useMemo(() => {
    const set = new Set<string>();
    savedReports.forEach((r) => {
      (r.tags || []).forEach((t) => set.add(t));
    });
    return Array.from(set);
  }, [savedReports]);

  // Filtered saved reports
  const filteredReports = useMemo(() => {
    return savedReports.filter((r) => {
      const matchesSearch =
        !searchFilter.trim() ||
        r.title.toLowerCase().includes(searchFilter.toLowerCase()) ||
        r.query.toLowerCase().includes(searchFilter.toLowerCase()) ||
        r.summary.toLowerCase().includes(searchFilter.toLowerCase());
      const matchesTag = !selectedTag || (r.tags || []).includes(selectedTag);
      return matchesSearch && matchesTag;
    });
  }, [savedReports, searchFilter, selectedTag]);

  return (
    <div className="research-hub">
      {/* Toast alert */}
      {toastNotice && (
        <div className="research-hub__toast" role="status">
          <CheckCircle2 size={16} />
          <span>{toastNotice}</span>
        </div>
      )}

      {/* Header bar */}
      <header className="research-hub__header">
        <div className="research-hub__header-left">
          <button
            type="button"
            className="research-hub__back-btn"
            onClick={onBack}
            title="Back to Workspace"
          >
            <ArrowLeft size={16} />
            <span>Workspace</span>
          </button>
          <div className="research-hub__title-wrap">
            <div className="research-hub__badge">
              <Globe size={14} className="research-hub__badge-icon" />
              <span>Deep Research Engine</span>
            </div>
            <h1 className="research-hub__title">Autonomous Research Hub</h1>
            <p className="research-hub__subtitle">
              Multi-engine live search, query decomposition, cross-source synthesis, and verified citations.
            </p>
          </div>
        </div>

        {/* Quick metrics */}
        <div className="research-hub__metrics">
          <div className="research-hub__metric-pill">
            <BookOpen size={14} />
            <span>
              <strong>{savedReports.length}</strong> Reports Saved
            </span>
          </div>
          <div className="research-hub__metric-pill">
            <CheckCircle2 size={14} />
            <span>
              <strong>High Fidelity</strong> Grounding
            </span>
          </div>
        </div>
      </header>

      {/* Tabs navigation */}
      <div className="research-hub__tabs-bar">
        <button
          type="button"
          className={`research-hub__tab ${activeTab === 'deep_research' ? 'research-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('deep_research')}
        >
          <Sparkles size={16} />
          <span>Deep Research</span>
        </button>
        <button
          type="button"
          className={`research-hub__tab ${activeTab === 'saved_reports' ? 'research-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('saved_reports')}
        >
          <BookOpen size={16} />
          <span>Saved Reports ({savedReports.length})</span>
        </button>
        <button
          type="button"
          className={`research-hub__tab ${activeTab === 'url_fetch' ? 'research-hub__tab--active' : ''}`}
          onClick={() => setActiveTab('url_fetch')}
        >
          <Link2 size={16} />
          <span>Live URL Extractor</span>
        </button>
      </div>

      {/* Error Banner */}
      {errorMsg && (
        <div className="research-hub__error-banner" role="alert">
          <AlertCircle size={18} />
          <span>{errorMsg}</span>
          <button
            type="button"
            className="research-hub__retry-btn"
            onClick={() => void handleLaunchResearch()}
          >
            ↻ Retry Investigation
          </button>
          <button
            type="button"
            className="research-hub__error-dismiss"
            onClick={() => setErrorMsg(null)}
          >
            &times;
          </button>
        </div>
      )}

      {/* Connection Error Banner */}
      {fetchError && (
        <div className="research-hub__error-banner" role="alert">
          <AlertCircle size={18} />
          <span>{fetchError}</span>
          <button
            type="button"
            className="research-hub__retry-btn"
            onClick={() => void loadReports()}
          >
            ↻ Retry Connection
          </button>
        </div>
      )}

      {/* Guest Mode Notice Banner */}
      {!accessToken && (
        <div className="research-hub__auth-banner">
          <span>🔒</span>
          <span>Guest Mode: Sign in to persist deep investigations, save research dossiers, and sync sources across devices.</span>
        </div>
      )}

      {/* MAIN TAB 1: Deep Research Launcher & Active Report */}
      {activeTab === 'deep_research' && (
        <div className="research-hub__main-layout">
          {/* Launcher Panel */}
          <div className="research-hub__launcher-card">
            <div className="research-hub__launcher-header">
              <div className="research-hub__launcher-title">
                <Sparkles size={18} className="research-hub__launcher-icon" />
                <span>Launch Autonomous Investigation</span>
              </div>
              <span className="research-hub__launcher-desc">
                Roxy decomposes complex topics into targeted multi-engine queries, analyzes live results, and synthesizes an authoritative report.
              </span>
            </div>

            {/* Query Input */}
            <div className="research-hub__input-wrap">
              <div className="research-hub__input-inner">
                <Search size={18} className="research-hub__input-icon" />
                <input
                  type="text"
                  className="research-hub__query-input"
                  placeholder={
                    interimQuery
                      ? `Listening: "${interimQuery}"`
                      : "Enter any topic or question (e.g. Next-gen solid-state battery benchmarks 2026)..."
                  }
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleLaunchResearch();
                  }}
                  disabled={isResearching}
                />
                {query && !isResearching && (
                  <button
                    type="button"
                    className="research-hub__clear-btn"
                    onClick={() => setQuery('')}
                  >
                    &times;
                  </button>
                )}
                <VoiceInputControl
                  toolId="research"
                  size="sm"
                  onTranscript={(finalText) => {
                    setQuery(finalText);
                    setInterimQuery('');
                  }}
                  onInterim={(interim) => {
                    setInterimQuery(interim);
                  }}
                  readAloudText={activeReport ? `${activeReport.title}. ${activeReport.summary}` : undefined}
                  showReadAloud={Boolean(activeReport)}
                  disabled={isResearching}
                />
              </div>
              {interimQuery && (
                <div style={{ padding: '6px 12px', fontSize: '12px', color: '#38bdf8', fontStyle: 'italic' }}>
                  🎙️ {interimQuery}
                </div>
              )}
            </div>

            {/* Depth selector + Options */}
            <div className="research-hub__controls-row">
              <div className="research-hub__depth-selector">
                <span className="research-hub__control-label">Investigation Depth:</span>
                <div className="research-hub__depth-pills">
                  {(
                    [
                      { id: 'quick', label: '⚡ Quick Briefing', desc: '2 sub-queries' },
                      { id: 'deep', label: '🔬 Deep Investigation', desc: '3 sub-queries' },
                      { id: 'academic', label: '📚 Academic Survey', desc: '4 sub-queries' },
                    ] as const
                  ).map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      className={`research-hub__depth-pill ${depth === d.id ? 'research-hub__depth-pill--active' : ''}`}
                      onClick={() => setDepth(d.id)}
                      disabled={isResearching}
                      title={d.desc}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="research-hub__auto-save-toggle">
                <label className="research-hub__checkbox-label">
                  <input
                    type="checkbox"
                    checked={autoSave}
                    onChange={(e) => setAutoSave(e.target.checked)}
                    disabled={isResearching}
                  />
                  <span>Auto-save to Library</span>
                </label>
              </div>
            </div>

            {/* Tags Input */}
            <div className="research-hub__tags-row">
              <Tag size={14} className="research-hub__tags-icon" />
              <input
                type="text"
                className="research-hub__tags-input"
                placeholder="Optional tags separated by comma (e.g. ai, hardware, market-analysis)"
                value={customTags}
                onChange={(e) => setCustomTags(e.target.value)}
                disabled={isResearching}
              />
            </div>

            {/* Action Bar */}
            <div className="research-hub__action-bar">
              <div className="research-hub__presets">
                <span className="research-hub__presets-label">Popular Topics:</span>
                <div className="research-hub__presets-list">
                  {PRESET_TOPICS.map((topic, i) => (
                    <button
                      key={i}
                      type="button"
                      className="research-hub__preset-chip"
                      onClick={() => {
                        setQuery(topic);
                        void handleLaunchResearch(topic);
                      }}
                      disabled={isResearching}
                    >
                      {topic}
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {isResearching && (
                  <button
                    type="button"
                    className="research-hub__preset-chip"
                    style={{ borderColor: '#ef4444', color: '#f87171' }}
                    onClick={handleCancelResearch}
                  >
                    <XCircle size={14} style={{ marginRight: '4px' }} />
                    Cancel
                  </button>
                )}
                <button
                  type="button"
                  className={`research-hub__launch-btn ${isResearching ? 'research-hub__launch-btn--loading' : ''}`}
                  onClick={() => void handleLaunchResearch()}
                  disabled={!query.trim() || isResearching}
                >
                  {isResearching ? (
                    <>
                      <RefreshCw size={16} className="research-hub__spin-icon" />
                      <span>{researchStage || 'Synthesizing...'}</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={16} />
                      <span>Run Deep Research</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Pipeline Stage Visualizer */}
            {isResearching && (
              <div className="research-hub__pipeline-tracker">
                <div className="research-hub__pipeline-header">
                  <span className="research-hub__pipeline-title">Autonomous Execution Pipeline</span>
                  <span className="research-hub__pipeline-status">{researchStage}</span>
                </div>
                <div className="research-hub__pipeline-progress-bar">
                  <div className="research-hub__pipeline-progress-fill" />
                </div>
                <div className="research-hub__pipeline-steps">
                  <span className="research-hub__pipeline-step research-hub__pipeline-step--active">
                    1. Decompose
                  </span>
                  <span className="research-hub__pipeline-arrow">→</span>
                  <span className="research-hub__pipeline-step research-hub__pipeline-step--active">
                    2. Live Multi-Search
                  </span>
                  <span className="research-hub__pipeline-arrow">→</span>
                  <span className="research-hub__pipeline-step research-hub__pipeline-step--active">
                    3. Extract Sources
                  </span>
                  <span className="research-hub__pipeline-arrow">→</span>
                  <span className="research-hub__pipeline-step research-hub__pipeline-step--active">
                    4. Synthesize Citations
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Active Report Viewer */}
          {activeReport && (
            <section className="research-hub__report-card">
              <div className="research-hub__report-topbar">
                <div className="research-hub__report-meta">
                  <div className="research-hub__report-badges">
                    <span
                      className={`research-hub__confidence-pill research-hub__confidence-pill--${activeReport.confidence.toLowerCase()}`}
                    >
                      Confidence: {activeReport.confidence.toUpperCase()}
                    </span>
                    <span className="research-hub__depth-badge">
                      {activeReport.depth.toUpperCase()}
                    </span>
                    {activeReport.sources && (
                      <span className="research-hub__sources-badge">
                        {activeReport.sources.length} Sources Verified
                      </span>
                    )}
                  </div>
                  <h2 className="research-hub__report-title">{activeReport.title}</h2>
                  <p className="research-hub__report-query">
                    <strong>Investigation Scope:</strong> {activeReport.query}
                  </p>
                </div>

                <div className="research-hub__report-actions">
                  <button
                    type="button"
                    className="research-hub__action-btn"
                    onClick={() => handleCopyReport(activeReport)}
                    title="Copy Markdown"
                  >
                    <Copy size={15} />
                    <span>Copy</span>
                  </button>

                  {onSendToChat && (
                    <button
                      type="button"
                      className="research-hub__action-btn"
                      onClick={() => handleSendToChatCoordinator(activeReport)}
                      title="Analyze with AI Agent"
                    >
                      <Send size={15} />
                      <span>Chat</span>
                    </button>
                  )}

                  {!('id' in activeReport) && (
                    <button
                      type="button"
                      className="research-hub__action-btn research-hub__action-btn--primary"
                      onClick={() => void handleSaveActiveReport()}
                      title="Save to Library"
                    >
                      <BookOpen size={15} />
                      <span>Save Report</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Sub-queries Decomposed */}
              {'sub_queries' in activeReport && activeReport.sub_queries && activeReport.sub_queries.length > 0 && (
                <div className="research-hub__subqueries-panel">
                  <div className="research-hub__section-label">
                    <Layers size={14} />
                    <span>Targeted Sub-Queries Decomposed</span>
                  </div>
                  <div className="research-hub__subqueries-list">
                    {activeReport.sub_queries.map((sq, i) => (
                      <span key={i} className="research-hub__subquery-pill">
                        {sq}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Executive Summary */}
              <div className="research-hub__section">
                <h3 className="research-hub__section-heading">Executive Summary</h3>
                <div className="research-hub__summary-box">
                  <p className="research-hub__summary-text">{activeReport.summary}</p>
                </div>
              </div>

              {/* Key Findings */}
              {activeReport.findings && activeReport.findings.length > 0 && (
                <div className="research-hub__section">
                  <h3 className="research-hub__section-heading">Key Synthesized Findings</h3>
                  <ul className="research-hub__findings-list">
                    {activeReport.findings.map((f, i) => (
                      <li key={i} className="research-hub__finding-item">
                        <span className="research-hub__finding-number">{i + 1}</span>
                        <span className="research-hub__finding-text">{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Verified Sources Registry */}
              {activeReport.sources && activeReport.sources.length > 0 && (
                <div className="research-hub__section">
                  <h3 className="research-hub__section-heading">
                    Verified Primary Sources ({activeReport.sources.length})
                  </h3>
                  <div className="research-hub__sources-grid">
                    {activeReport.sources.map((s) => {
                      let domain = '';
                      try {
                        domain = new URL(s.url).hostname.replace('www.', '');
                      } catch {
                        domain = s.url;
                      }
                      return (
                        <a
                          key={s.index}
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="research-hub__source-card"
                          title={s.url}
                        >
                          <div className="research-hub__source-top">
                            <span className="research-hub__source-badge">[{s.index}]</span>
                            <span className="research-hub__source-domain">{domain}</span>
                            <ExternalLink size={13} className="research-hub__source-ext-icon" />
                          </div>
                          <h4 className="research-hub__source-title">{s.title || domain}</h4>
                          {s.snippet && (
                            <p className="research-hub__source-snippet">{s.snippet}</p>
                          )}
                        </a>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>
          )}
        </div>
      )}

      {/* MAIN TAB 2: Saved Reports Archive */}
      {activeTab === 'saved_reports' && (
        <div className="research-hub__archive-layout">
          {/* Search & Filter Header */}
          <div className="research-hub__archive-controls">
            <div className="research-hub__search-box">
              <Search size={16} className="research-hub__search-box-icon" />
              <input
                type="text"
                placeholder="Filter saved reports by title, query, or summary..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="research-hub__search-box-input"
              />
              {searchFilter && (
                <button
                  type="button"
                  className="research-hub__clear-btn"
                  onClick={() => setSearchFilter('')}
                >
                  &times;
                </button>
              )}
            </div>

            {/* Tag filters */}
            {allTags.length > 0 && (
              <div className="research-hub__tag-filters">
                <button
                  type="button"
                  className={`research-hub__tag-pill ${selectedTag === null ? 'research-hub__tag-pill--active' : ''}`}
                  onClick={() => setSelectedTag(null)}
                >
                  All Tags
                </button>
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className={`research-hub__tag-pill ${selectedTag === tag ? 'research-hub__tag-pill--active' : ''}`}
                    onClick={() => setSelectedTag(tag === selectedTag ? null : tag)}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Clean Slate Empty State */}
          {!isLoadingReports && filteredReports.length === 0 && (
            <div className="research-hub__empty-state">
              <div className="research-hub__empty-icon-box">
                <BookOpen size={36} strokeWidth={1.5} />
              </div>
              <h3 className="research-hub__empty-title">
                {searchFilter || selectedTag
                  ? 'No matching research reports found'
                  : 'No saved research reports yet'}
              </h3>
              <p className="research-hub__empty-desc">
                {searchFilter || selectedTag
                  ? 'Try adjusting your search criteria or tag filters.'
                  : 'Launch an autonomous investigation in the Deep Research tab to generate and archive your first verified intelligence report.'}
              </p>
              {!searchFilter && !selectedTag && (
                <button
                  type="button"
                  className="research-hub__empty-btn"
                  onClick={() => setActiveTab('deep_research')}
                >
                  <Sparkles size={16} />
                  <span>Start a Deep Investigation</span>
                </button>
              )}
            </div>
          )}

          {/* Reports Grid */}
          <div className="research-hub__reports-grid">
            {filteredReports.map((report) => (
              <div
                key={report.id}
                className="research-hub__report-tile"
                onClick={() => {
                  setActiveReport(report);
                  setActiveTab('deep_research');
                }}
              >
                <div className="research-hub__tile-header">
                  <span
                    className={`research-hub__confidence-pill research-hub__confidence-pill--${(report.confidence || 'medium').toLowerCase()}`}
                  >
                    {report.confidence.toUpperCase()}
                  </span>
                  <div className="research-hub__tile-actions">
                    <button
                      type="button"
                      className="research-hub__icon-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopyReport(report);
                      }}
                      title="Copy Markdown"
                    >
                      <Copy size={13} />
                    </button>
                    <button
                      type="button"
                      className="research-hub__icon-btn research-hub__icon-btn--danger"
                      onClick={(e) => handleDeleteReport(report.id, e)}
                      title="Delete Report"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                <h3 className="research-hub__tile-title">{report.title}</h3>
                <p className="research-hub__tile-query">
                  <strong>Query:</strong> {report.query}
                </p>
                <p className="research-hub__tile-summary">{report.summary}</p>

                {report.tags && report.tags.length > 0 && (
                  <div className="research-hub__tile-tags">
                    {report.tags.map((t, i) => (
                      <span key={i} className="research-hub__tile-tag">
                        #{t}
                      </span>
                    ))}
                  </div>
                )}

                <div className="research-hub__tile-footer">
                  <span className="research-hub__tile-sources">
                    <Globe size={12} />
                    {(report.sources || []).length} Sources
                  </span>
                  <span className="research-hub__tile-view-link">
                    Open Report <ChevronRight size={14} />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* MAIN TAB 3: Live URL Extractor */}
      {activeTab === 'url_fetch' && (
        <div className="research-hub__fetch-layout">
          <div className="research-hub__launcher-card">
            <div className="research-hub__launcher-header">
              <div className="research-hub__launcher-title">
                <FileText size={18} className="research-hub__launcher-icon" />
                <span>Primary Source Webpage Extractor</span>
              </div>
              <span className="research-hub__launcher-desc">
                Extract readable text, strip HTML clutter, calculate density, and preview primary source materials directly.
              </span>
            </div>

            <div className="research-hub__input-wrap">
              <div className="research-hub__input-inner">
                <Link2 size={18} className="research-hub__input-icon" />
                <input
                  type="url"
                  className="research-hub__query-input"
                  placeholder="https://example.com/article-or-report..."
                  value={fetchUrl}
                  onChange={(e) => setFetchUrl(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleFetchUrl();
                  }}
                  disabled={isFetchingUrl}
                />
              </div>
            </div>

            <div className="research-hub__action-bar">
              <div />
              <button
                type="button"
                className={`research-hub__launch-btn ${isFetchingUrl ? 'research-hub__launch-btn--loading' : ''}`}
                onClick={() => void handleFetchUrl()}
                disabled={!fetchUrl.trim() || isFetchingUrl}
              >
                {isFetchingUrl ? (
                  <>
                    <RefreshCw size={16} className="research-hub__spin-icon" />
                    <span>Extracting...</span>
                  </>
                ) : (
                  <>
                    <Globe size={16} />
                    <span>Extract Web Content</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* URL Fetch Results */}
          {urlFetchResult && (
            <div className="research-hub__report-card">
              <div className="research-hub__report-topbar">
                <div className="research-hub__report-meta">
                  <div className="research-hub__report-badges">
                    <span className="research-hub__sources-badge">
                      {urlFetchResult.word_count} Words Extracted
                    </span>
                  </div>
                  <h2 className="research-hub__report-title">{urlFetchResult.title}</h2>
                  <a
                    href={urlFetchResult.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="research-hub__source-domain"
                  >
                    {urlFetchResult.url} <ExternalLink size={12} />
                  </a>
                </div>

                <div className="research-hub__report-actions">
                  <button
                    type="button"
                    className="research-hub__action-btn"
                    onClick={() => {
                      void navigator.clipboard.writeText(urlFetchResult.content);
                      showToast('Article content copied to clipboard!');
                    }}
                  >
                    <Copy size={15} />
                    <span>Copy Text</span>
                  </button>
                  <button
                    type="button"
                    className="research-hub__action-btn research-hub__action-btn--primary"
                    onClick={() => {
                      setQuery(`Summarize and verify key claims from ${urlFetchResult.url}: ${urlFetchResult.title}`);
                      setActiveTab('deep_research');
                    }}
                  >
                    <Sparkles size={15} />
                    <span>Investigate This Page</span>
                  </button>
                </div>
              </div>

              <div className="research-hub__section">
                <h3 className="research-hub__section-heading">Extracted Clean Content</h3>
                <div className="research-hub__content-preview">
                  <pre className="research-hub__content-pre">{urlFetchResult.content}</pre>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
