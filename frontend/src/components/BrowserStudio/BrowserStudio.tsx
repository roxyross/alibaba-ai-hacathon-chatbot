import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Compass,
  Globe,
  Search,
  Sparkles,
  ExternalLink,
  CheckCircle2,
  Trash2,
  Copy,
  ArrowLeft,
  AlertCircle,
  Play,
  RefreshCw,
  Tag,
  FileText,
  Clock,
  Code,
  Layers,
  ChevronRight,
  ShieldAlert,
  Send,
  Camera,
  Check,
} from 'lucide-react';
import './BrowserStudio.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface BrowserTaskItem {
  id: string;
  user_id: string;
  title: string;
  url: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | string;
  action_type: 'navigate' | 'extract' | 'fill_form' | 'screenshot' | 'multi_step' | string;
  actions: Array<{ type: string; [key: string]: unknown }>;
  result_data: {
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
  tags: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface InspectResponse {
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

export interface ExtractResponse {
  url: string;
  title?: string | null;
  tables: Array<{ table_index?: number; headers: string[]; rows: string[][]; total_rows?: number }>;
  links: Array<{ text: string; href: string }>;
  headings: Array<{ level: number; text: string }>;
  text_excerpt: string;
  status: string;
  error?: string | null;
}

export interface ScreenshotResponse {
  url: string;
  title?: string | null;
  screenshot_url: string;
  width: number;
  height: number;
  status: string;
  timestamp: string;
}

interface BrowserStudioProps {
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

const PRESET_URLS = [
  'https://news.ycombinator.com',
  'https://en.wikipedia.org/wiki/Artificial_intelligence',
  'https://fastapi.tiangolo.com',
  'https://github.com/trending',
];

export const BrowserStudio: React.FC<BrowserStudioProps> = ({
  accessToken,
  onBack,
  onSendToChat,
}) => {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<'inspector' | 'flows' | 'tasks'>('inspector');

  // Inspector tab state
  const [targetUrl, setTargetUrl] = useState('');
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectData, setInspectData] = useState<InspectResponse | null>(null);
  const [screenshotData, setScreenshotData] = useState<ScreenshotResponse | null>(null);
  const [inspectorSubTab, setInspectorSubTab] = useState<'preview' | 'headings' | 'tables' | 'links' | 'forms' | 'raw'>('preview');
  const [inspectError, setInspectError] = useState<string | null>(null);

  // Flow runner tab state
  const [flowUrl, setFlowUrl] = useState('');
  const [flowTitle, setFlowTitle] = useState('');
  const [flowExtractType, setFlowExtractType] = useState<'all' | 'tables' | 'links'>('all');
  const [flowTags, setFlowTags] = useState('automation, extraction');
  const [isRunningFlow, setIsRunningFlow] = useState(false);
  const [flowResult, setFlowResult] = useState<Record<string, unknown> | null>(null);
  const [flowError, setFlowError] = useState<string | null>(null);

  // Tasks library tab state
  const [tasks, setTasks] = useState<BrowserTaskItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'pending' | 'failed'>('all');
  const [selectedTask, setSelectedTask] = useState<BrowserTaskItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Copy helper
  const handleCopy = useCallback((text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  // Fetch tasks
  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    try {
      const data = await fetchJSON<{ tasks: BrowserTaskItem[]; total: number }>(
        `${API_BASE}/browser/tasks?limit=50`,
        accessToken,
      );
      setTasks(data.tasks ?? []);
    } catch {
      setTasks([]);
    } finally {
      setTasksLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // Inspect page action
  const handleInspect = async (urlToInspect?: string) => {
    const url = (urlToInspect || targetUrl).trim();
    if (!url) return;
    setInspectError(null);
    setIsInspecting(true);
    setInspectData(null);
    setScreenshotData(null);

    try {
      const data = await fetchJSON<InspectResponse>(
        `${API_BASE}/browser/navigate`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({ url, timeout_seconds: 20 }),
        },
      );
      setInspectData(data);

      // Trigger screenshot capture asynchronously
      fetchJSON<ScreenshotResponse>(
        `${API_BASE}/browser/screenshot`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({ url, width: 1280, height: 800 }),
        },
      )
        .then((shot) => setScreenshotData(shot))
        .catch(() => {});
    } catch (err: unknown) {
      setInspectError(err instanceof Error ? err.message : 'Inspection failed');
    } finally {
      setIsInspecting(false);
    }
  };

  // Run multi-step flow action
  const handleRunFlow = async () => {
    const url = flowUrl.trim();
    if (!url) return;
    setFlowError(null);
    setIsRunningFlow(true);
    setFlowResult(null);

    const actions = [
      { type: 'navigate' },
      { type: 'extract', extract_type: flowExtractType },
      { type: 'wait', seconds: 0.5 },
      { type: 'screenshot' },
    ];

    const tagList = flowTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      const res = await fetchJSON<Record<string, unknown>>(
        `${API_BASE}/browser/execute`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({
            url,
            title: flowTitle.trim() || undefined,
            actions,
            save_task: true,
            tags: tagList,
          }),
        },
      );
      setFlowResult(res);
      loadTasks(); // refresh saved tasks
    } catch (err: unknown) {
      setFlowError(err instanceof Error ? err.message : 'Flow execution failed');
    } finally {
      setIsRunningFlow(false);
    }
  };

  // Delete task action
  const handleDeleteTask = async (taskId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!window.confirm('Delete this browser task record?')) return;
    try {
      await fetchJSON(`${API_BASE}/browser/tasks/${taskId}`, accessToken, {
        method: 'DELETE',
      });
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
      if (selectedTask?.id === taskId) setSelectedTask(null);
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  // Filtered tasks
  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      const matchSearch =
        !searchQuery ||
        t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.url.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchStatus = statusFilter === 'all' || t.status === statusFilter;
      return matchSearch && matchStatus;
    });
  }, [tasks, searchQuery, statusFilter]);

  return (
    <div className="browser-studio" role="region" aria-label="Web Automation Studio">
      {/* 1. Header Toolbar */}
      <header className="browser-studio__header">
        <div className="browser-studio__header-left">
          <button
            type="button"
            className="browser-studio__back-btn"
            onClick={onBack}
            title="Back to Chat"
          >
            <ArrowLeft size={16} />
            <span>Chat</span>
          </button>
          <div className="browser-studio__title-group">
            <div className="browser-studio__icon-box">
              <Compass size={20} className="browser-studio__icon" />
            </div>
            <div>
              <h1 className="browser-studio__title">Browser Studio</h1>
              <p className="browser-studio__subtitle">
                Autonomous Headless Navigation, DOM Inspection & Web Automation
              </p>
            </div>
          </div>
        </div>

        <nav className="browser-studio__tabs" aria-label="Studio Navigation">
          <button
            type="button"
            className={`browser-studio__tab ${activeTab === 'inspector' ? 'browser-studio__tab--active' : ''}`}
            onClick={() => setActiveTab('inspector')}
          >
            <Globe size={15} />
            <span>Live Inspector</span>
          </button>
          <button
            type="button"
            className={`browser-studio__tab ${activeTab === 'flows' ? 'browser-studio__tab--active' : ''}`}
            onClick={() => setActiveTab('flows')}
          >
            <Play size={15} />
            <span>Automation Flows</span>
          </button>
          <button
            type="button"
            className={`browser-studio__tab ${activeTab === 'tasks' ? 'browser-studio__tab--active' : ''}`}
            onClick={() => setActiveTab('tasks')}
          >
            <Clock size={15} />
            <span>Task Logs</span>
            {tasks.length > 0 && <span className="browser-studio__badge">{tasks.length}</span>}
          </button>
        </nav>
      </header>

      {/* 2. Main Studio Content */}
      <main className="browser-studio__content">
        {/* TAB 1: LIVE INSPECTOR */}
        {activeTab === 'inspector' && (
          <div className="browser-studio__panel">
            <div className="browser-studio__search-bar-wrap">
              <form
                className="browser-studio__search-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleInspect();
                }}
              >
                <Globe size={18} className="browser-studio__input-icon" />
                <input
                  type="url"
                  className="browser-studio__url-input"
                  placeholder="Enter any target website URL (e.g., https://example.com)..."
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  required
                />
                <button
                  type="submit"
                  className="browser-studio__inspect-btn"
                  disabled={isInspecting || !targetUrl.trim()}
                >
                  {isInspecting ? (
                    <>
                      <RefreshCw size={15} className="browser-studio__spin" />
                      <span>Inspecting DOM…</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={15} />
                      <span>Inspect Page</span>
                    </>
                  )}
                </button>
              </form>

              <div className="browser-studio__chips-row">
                <span className="browser-studio__chips-label">Popular Targets:</span>
                {PRESET_URLS.map((u) => (
                  <button
                    key={u}
                    type="button"
                    className="browser-studio__chip"
                    onClick={() => {
                      setTargetUrl(u);
                      handleInspect(u);
                    }}
                  >
                    {u.replace('https://', '')}
                  </button>
                ))}
              </div>
            </div>

            {inspectError && (
              <div className="browser-studio__alert browser-studio__alert--error">
                <AlertCircle size={18} />
                <span>{inspectError}</span>
              </div>
            )}

            {inspectData ? (
              <div className="browser-studio__inspection-card">
                <div className="browser-studio__inspection-header">
                  <div className="browser-studio__inspection-meta">
                    <span className="browser-studio__status-chip browser-studio__status-chip--success">
                      <CheckCircle2 size={13} />
                      <span>HTTP 200 OK</span>
                    </span>
                    <h2 className="browser-studio__page-title">{inspectData.title || 'Page Details'}</h2>
                    <a
                      href={inspectData.final_url || inspectData.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="browser-studio__external-link"
                    >
                      <span>{inspectData.final_url || inspectData.url}</span>
                      <ExternalLink size={12} />
                    </a>
                  </div>

                  <div className="browser-studio__meta-pills">
                    <div className="browser-studio__stat-pill">
                      <span className="browser-studio__stat-val">{inspectData.headings.length}</span>
                      <span className="browser-studio__stat-label">Headings</span>
                    </div>
                    <div className="browser-studio__stat-pill">
                      <span className="browser-studio__stat-val">{inspectData.links.length}</span>
                      <span className="browser-studio__stat-label">Links</span>
                    </div>
                    <div className="browser-studio__stat-pill">
                      <span className="browser-studio__stat-val">{inspectData.forms.length}</span>
                      <span className="browser-studio__stat-label">Forms</span>
                    </div>
                  </div>
                </div>

                {/* Sub-tabs inside Inspector */}
                <div className="browser-studio__subtabs">
                  <button
                    type="button"
                    className={`browser-studio__subtab ${inspectorSubTab === 'preview' ? 'browser-studio__subtab--active' : ''}`}
                    onClick={() => setInspectorSubTab('preview')}
                  >
                    <Camera size={14} />
                    <span>Visual Snapshot</span>
                  </button>
                  <button
                    type="button"
                    className={`browser-studio__subtab ${inspectorSubTab === 'headings' ? 'browser-studio__subtab--active' : ''}`}
                    onClick={() => setInspectorSubTab('headings')}
                  >
                    <FileText size={14} />
                    <span>Headings ({inspectData.headings.length})</span>
                  </button>
                  <button
                    type="button"
                    className={`browser-studio__subtab ${inspectorSubTab === 'links' ? 'browser-studio__subtab--active' : ''}`}
                    onClick={() => setInspectorSubTab('links')}
                  >
                    <Globe size={14} />
                    <span>Hyperlinks ({inspectData.links.length})</span>
                  </button>
                  <button
                    type="button"
                    className={`browser-studio__subtab ${inspectorSubTab === 'forms' ? 'browser-studio__subtab--active' : ''}`}
                    onClick={() => setInspectorSubTab('forms')}
                  >
                    <Layers size={14} />
                    <span>Forms ({inspectData.forms.length})</span>
                  </button>
                  <button
                    type="button"
                    className={`browser-studio__subtab ${inspectorSubTab === 'raw' ? 'browser-studio__subtab--active' : ''}`}
                    onClick={() => setInspectorSubTab('raw')}
                  >
                    <Code size={14} />
                    <span>Clean Excerpt</span>
                  </button>
                </div>

                <div className="browser-studio__subtab-content">
                  {inspectorSubTab === 'preview' && (
                    <div className="browser-studio__snapshot-pane">
                      {screenshotData?.screenshot_url ? (
                        <div className="browser-studio__screenshot-frame">
                          <img
                            src={screenshotData.screenshot_url}
                            alt={`Rendered preview of ${inspectData.url}`}
                            className="browser-studio__screenshot-img"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = 'none';
                            }}
                          />
                          <p className="browser-studio__screenshot-caption">
                            Live visual preview captured at {screenshotData.width}x{screenshotData.height} resolution
                          </p>
                        </div>
                      ) : (
                        <div className="browser-studio__placeholder-snapshot">
                          <Camera size={32} className="browser-studio__placeholder-icon" />
                          <p>Capturing high-resolution visual snapshot…</p>
                        </div>
                      )}
                    </div>
                  )}

                  {inspectorSubTab === 'headings' && (
                    <div className="browser-studio__items-list">
                      {inspectData.headings.length === 0 ? (
                        <p className="browser-studio__empty-subtext">No H1-H3 headings found in DOM.</p>
                      ) : (
                        inspectData.headings.map((h, i) => (
                          <div key={i} className="browser-studio__item-row">
                            <span className="browser-studio__h-level">H{h.level}</span>
                            <span className="browser-studio__item-text">{h.text}</span>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {inspectorSubTab === 'links' && (
                    <div className="browser-studio__items-list">
                      {inspectData.links.length === 0 ? (
                        <p className="browser-studio__empty-subtext">No external links found.</p>
                      ) : (
                        inspectData.links.map((lnk, i) => (
                          <div key={i} className="browser-studio__item-row">
                            <span className="browser-studio__link-title">{lnk.text}</span>
                            <a
                              href={lnk.href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="browser-studio__link-url"
                            >
                              {lnk.href}
                            </a>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {inspectorSubTab === 'forms' && (
                    <div className="browser-studio__items-list">
                      {inspectData.forms.length === 0 ? (
                        <p className="browser-studio__empty-subtext">No input forms detected on this page.</p>
                      ) : (
                        inspectData.forms.map((f, i) => (
                          <div key={i} className="browser-studio__form-card">
                            <div className="browser-studio__form-badge-row">
                              <span className="browser-studio__method-tag">{f.method}</span>
                              <span className="browser-studio__action-url">{f.action}</span>
                            </div>
                            {f.fields.length > 0 && (
                              <div className="browser-studio__fields-tags">
                                <span className="browser-studio__fields-label">Inputs:</span>
                                {f.fields.map((fld) => (
                                  <span key={fld} className="browser-studio__fld-tag">
                                    {fld}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {inspectorSubTab === 'raw' && (
                    <div className="browser-studio__raw-pane">
                      <pre className="browser-studio__raw-pre">
                        {inspectData.content_preview || 'No text extracted.'}
                      </pre>
                    </div>
                  )}
                </div>

                {onSendToChat && (
                  <div className="browser-studio__card-footer">
                    <button
                      type="button"
                      className="browser-studio__send-chat-btn"
                      onClick={() => {
                        const prompt = `Please analyze this webpage: "${inspectData.title}" (${inspectData.url}). Content preview: ${inspectData.content_preview.slice(0, 300)}...`;
                        onSendToChat(prompt);
                      }}
                    >
                      <Send size={14} />
                      <span>Send Extraction to Chat</span>
                    </button>
                  </div>
                )}
              </div>
            ) : !isInspecting ? (
              <div className="browser-studio__zero-state">
                <Compass size={40} className="browser-studio__zero-icon" />
                <h3>No Webpage Inspected Yet</h3>
                <p>Enter a URL above to inspect page headers, discover links, and extract tables.</p>
              </div>
            ) : null}
          </div>
        )}

        {/* TAB 2: AUTOMATION FLOWS */}
        {activeTab === 'flows' && (
          <div className="browser-studio__panel">
            <div className="browser-studio__flow-builder-card">
              <h2 className="browser-studio__card-heading">
                <Play size={18} />
                <span>Autonomous Multi-Step Flow Runner</span>
              </h2>
              <p className="browser-studio__card-sub">
                Sequence multiple headless actions (Navigate &rarr; Extract &rarr; Wait &rarr; Snapshot) in a single run.
              </p>

              <div className="browser-studio__form-grid">
                <div className="browser-studio__form-field">
                  <label className="browser-studio__label">Target Website URL *</label>
                  <input
                    type="url"
                    className="browser-studio__input"
                    placeholder="https://example.com/data"
                    value={flowUrl}
                    onChange={(e) => setFlowUrl(e.target.value)}
                    required
                  />
                </div>

                <div className="browser-studio__form-field">
                  <label className="browser-studio__label">Workflow Title</label>
                  <input
                    type="text"
                    className="browser-studio__input"
                    placeholder="e.g. Scrape Pricing & Headings"
                    value={flowTitle}
                    onChange={(e) => setFlowTitle(e.target.value)}
                  />
                </div>

                <div className="browser-studio__form-field">
                  <label className="browser-studio__label">Extraction Scope</label>
                  <select
                    className="browser-studio__select"
                    value={flowExtractType}
                    onChange={(e) => setFlowExtractType(e.target.value as 'all' | 'tables' | 'links')}
                  >
                    <option value="all">Full Extraction (Tables + Links + Headings)</option>
                    <option value="tables">Data Tables Only</option>
                    <option value="links">Hyperlinks Only</option>
                  </select>
                </div>

                <div className="browser-studio__form-field">
                  <label className="browser-studio__label">Tags (comma separated)</label>
                  <input
                    type="text"
                    className="browser-studio__input"
                    placeholder="e.g. market, competitor, weekly"
                    value={flowTags}
                    onChange={(e) => setFlowTags(e.target.value)}
                  />
                </div>
              </div>

              <div className="browser-studio__flow-steps-preview">
                <span className="browser-studio__flow-steps-title">Scheduled Action Pipeline:</span>
                <div className="browser-studio__flow-steps-row">
                  <span className="browser-studio__step-pill">1. Navigate to URL</span>
                  <ChevronRight size={14} className="browser-studio__step-arrow" />
                  <span className="browser-studio__step-pill">2. Extract {flowExtractType.toUpperCase()}</span>
                  <ChevronRight size={14} className="browser-studio__step-arrow" />
                  <span className="browser-studio__step-pill">3. Wait 0.5s</span>
                  <ChevronRight size={14} className="browser-studio__step-arrow" />
                  <span className="browser-studio__step-pill">4. Capture Visual Snapshot</span>
                </div>
              </div>

              <button
                type="button"
                className="browser-studio__run-flow-btn"
                disabled={isRunningFlow || !flowUrl.trim()}
                onClick={handleRunFlow}
              >
                {isRunningFlow ? (
                  <>
                    <RefreshCw size={16} className="browser-studio__spin" />
                    <span>Executing Pipeline…</span>
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    <span>Execute Web Flow</span>
                  </>
                )}
              </button>

              {flowError && (
                <div className="browser-studio__alert browser-studio__alert--error">
                  <AlertCircle size={18} />
                  <span>{flowError}</span>
                </div>
              )}

              {flowResult && (
                <div className="browser-studio__flow-result-pane">
                  <div className="browser-studio__flow-result-header">
                    <span className="browser-studio__status-chip browser-studio__status-chip--success">
                      <CheckCircle2 size={13} />
                      <span>Pipeline {String(flowResult.status).toUpperCase()}</span>
                    </span>
                    <button
                      type="button"
                      className="browser-studio__copy-btn"
                      onClick={() => handleCopy(JSON.stringify(flowResult, null, 2), 'flow-res')}
                    >
                      {copiedId === 'flow-res' ? <Check size={13} /> : <Copy size={13} />}
                      <span>{copiedId === 'flow-res' ? 'Copied' : 'Copy Result'}</span>
                    </button>
                  </div>
                  <pre className="browser-studio__flow-json">
                    {JSON.stringify(flowResult, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: TASK LOGS */}
        {activeTab === 'tasks' && (
          <div className="browser-studio__panel">
            <div className="browser-studio__tasks-toolbar">
              <div className="browser-studio__search-box">
                <Search size={15} />
                <input
                  type="text"
                  placeholder="Search saved tasks by title, url, tags..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="browser-studio__search-input"
                />
              </div>

              <div className="browser-studio__filter-pills">
                {(['all', 'completed', 'pending', 'failed'] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`browser-studio__filter-pill ${statusFilter === s ? 'browser-studio__filter-pill--active' : ''}`}
                    onClick={() => setStatusFilter(s)}
                  >
                    {s.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            {tasksLoading ? (
              <div className="browser-studio__loading-box">
                <RefreshCw size={24} className="browser-studio__spin" />
                <span>Loading browser automation tasks…</span>
              </div>
            ) : filteredTasks.length === 0 ? (
              <div className="browser-studio__zero-state">
                <Clock size={40} className="browser-studio__zero-icon" />
                <h3>No Browser Tasks Found</h3>
                <p>
                  {searchQuery || statusFilter !== 'all'
                    ? 'No tasks matched your search filters.'
                    : 'You have no saved browser automation tasks. Run an automation flow or inspect a webpage to save tasks.'}
                </p>
              </div>
            ) : (
              <div className="browser-studio__tasks-grid">
                {filteredTasks.map((t) => (
                  <div
                    key={t.id}
                    className={`browser-studio__task-card ${selectedTask?.id === t.id ? 'browser-studio__task-card--selected' : ''}`}
                    onClick={() => setSelectedTask(t)}
                  >
                    <div className="browser-studio__task-card-top">
                      <span className={`browser-studio__status-chip browser-studio__status-chip--${t.status}`}>
                        {t.status === 'completed' ? <CheckCircle2 size={12} /> : <Clock size={12} />}
                        <span>{t.status.toUpperCase()}</span>
                      </span>
                      <span className="browser-studio__action-badge">{t.action_type}</span>
                    </div>

                    <h3 className="browser-studio__task-title">{t.title}</h3>
                    <p className="browser-studio__task-url">{t.url}</p>

                    {t.tags.length > 0 && (
                      <div className="browser-studio__tags-row">
                        {t.tags.map((tag) => (
                          <span key={tag} className="browser-studio__tag-chip">
                            <Tag size={10} />
                            <span>{tag}</span>
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="browser-studio__task-footer">
                      <span className="browser-studio__date-text">
                        {t.created_at ? new Date(t.created_at).toLocaleDateString() : 'Recent'}
                      </span>
                      <div className="browser-studio__card-actions">
                        <button
                          type="button"
                          className="browser-studio__icon-action-btn"
                          title="Copy JSON"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(JSON.stringify(t, null, 2), t.id);
                          }}
                        >
                          {copiedId === t.id ? <Check size={13} /> : <Copy size={13} />}
                        </button>
                        <button
                          type="button"
                          className="browser-studio__icon-action-btn browser-studio__icon-action-btn--delete"
                          title="Delete Task"
                          onClick={(e) => handleDeleteTask(t.id, e)}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Selected Task Inspection Modal */}
            {selectedTask && (
              <div className="browser-studio__modal-backdrop" onClick={() => setSelectedTask(null)}>
                <div
                  className="browser-studio__modal"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="browser-studio__modal-header">
                    <div>
                      <h3 className="browser-studio__modal-title">{selectedTask.title}</h3>
                      <p className="browser-studio__modal-url">{selectedTask.url}</p>
                    </div>
                    <button
                      type="button"
                      className="browser-studio__close-btn"
                      onClick={() => setSelectedTask(null)}
                    >
                      ✕
                    </button>
                  </div>

                  <div className="browser-studio__modal-body">
                    <div className="browser-studio__modal-meta-row">
                      <span className="browser-studio__modal-meta-item">
                        <strong>Status:</strong> {selectedTask.status}
                      </span>
                      <span className="browser-studio__modal-meta-item">
                        <strong>Type:</strong> {selectedTask.action_type}
                      </span>
                      {selectedTask.requires_confirmation && (
                        <span className="browser-studio__sensitive-pill">
                          <ShieldAlert size={12} /> Requires Confirmation
                        </span>
                      )}
                    </div>

                    <h4 className="browser-studio__section-title">Result Data Payload:</h4>
                    <pre className="browser-studio__modal-json">
                      {JSON.stringify(selectedTask.result_data, null, 2)}
                    </pre>
                  </div>

                  <div className="browser-studio__modal-footer">
                    <button
                      type="button"
                      className="browser-studio__modal-copy-btn"
                      onClick={() => handleCopy(JSON.stringify(selectedTask, null, 2), 'modal-task')}
                    >
                      {copiedId === 'modal-task' ? <Check size={14} /> : <Copy size={14} />}
                      <span>{copiedId === 'modal-task' ? 'Copied' : 'Copy Full Task JSON'}</span>
                    </button>
                    <button
                      type="button"
                      className="browser-studio__modal-close-btn"
                      onClick={() => setSelectedTask(null)}
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default BrowserStudio;
