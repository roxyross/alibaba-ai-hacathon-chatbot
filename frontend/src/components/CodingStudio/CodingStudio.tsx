import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Code2,
  Play,
  Save,
  Copy,
  Trash2,
  Star,
  Sparkles,
  ArrowLeft,
  Terminal,
  FileCode,
  Search,
  Bug,
  BookOpen,
} from 'lucide-react';
import './CodingStudio.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface CodeSnippetItem {
  id: string;
  user_id: string;
  title: string;
  language: string;
  code: string;
  description?: string | null;
  tags: string[];
  is_favorite: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CodeExecutionItem {
  id: string;
  language: string;
  status: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  execution_time_ms: number;
  created_at?: string | null;
}

export interface CodeStatsItem {
  total_snippets: number;
  favorite_snippets: number;
  languages_count: Record<string, number>;
  total_executions: number;
  successful_executions: number;
  success_rate_percentage: number;
}

interface CodingStudioProps {
  onBack?: () => void;
  accessToken?: string | null;
  onSendToChat?: (text: string) => void;
}

const DEFAULT_PYTHON_CODE = `# Welcome to ROXY Autonomous Developer Studio!
# Write or test algorithms, scripts, and utilities below:

def solve(n: int) -> int:
    """Calculate the sum of squares up to n."""
    return sum(i * i for i in range(1, n + 1))

if __name__ == "__main__":
    result = solve(10)
    print(f"Result for n=10: {result}")
`;

export const CodingStudio: React.FC<CodingStudioProps> = ({ onBack, accessToken, onSendToChat }) => {
  const [activeTab, setActiveTab] = useState<'playground' | 'ai' | 'snippets'>('playground');

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
  const [code, setCode] = useState(DEFAULT_PYTHON_CODE);
  const [language, setLanguage] = useState('python');
  const [stdinText, setStdinText] = useState('');
  const [showStdin, setShowStdin] = useState(false);
  const [runningCode, setRunningCode] = useState(false);
  const [lastExecution, setLastExecution] = useState<CodeExecutionItem | null>(null);

  // Snippets State
  const [snippets, setSnippets] = useState<CodeSnippetItem[]>([]);
  const [snippetSearch, setSnippetSearch] = useState('');
  const [snippetLangFilter, setSnippetLangFilter] = useState('All');
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');
  const [saveDesc, setSaveDesc] = useState('');
  const [saveTags, setSaveTags] = useState('');
  const [savingSnippet, setSavingSnippet] = useState(false);

  // AI Assistant State
  const [aiMode, setAiMode] = useState<'generate' | 'explain' | 'debug'>('generate');
  const [genTask, setGenTask] = useState('');
  const [genConstraints, setGenConstraints] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<{
    code: string;
    explanation: string;
    warnings: string[];
  } | null>(null);

  // AI Explain State
  const [explainCodeInput, setExplainCodeInput] = useState('');
  const [explainLevel, setExplainLevel] = useState('intermediate');
  const [explaining, setExplaining] = useState(false);
  const [explainResult, setExplainResult] = useState<{
    explanation: string;
    key_lines: Array<{ line: number; note: string }>;
    followups: string[];
  } | null>(null);

  // AI Debug State
  const [debugCodeInput, setDebugCodeInput] = useState('');
  const [debugErrorMsg, setDebugErrorMsg] = useState('');
  const [debugging, setDebugging] = useState(false);
  const [debugResult, setDebugResult] = useState<{
    hypothesis: string;
    evidence: string;
    fix: string;
    fixed_code: string;
    verification: string;
    alternatives: string[];
  } | null>(null);

  const authHeaders = useMemo((): Record<string, string> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }
    return headers;
  }, [accessToken]);

  // Load Data
  const loadSnippetsAndStats = useCallback(async () => {
    try {
      const [snipRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/coding/snippets`, { headers: authHeaders }),
        fetch(`${API_BASE}/coding/stats`, { headers: authHeaders }),
      ]);
      if (snipRes.ok) {
        const data = await snipRes.json();
        setSnippets(data.snippets || []);
      }
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }
    } catch {
      // Offline fallback
    }
  }, [authHeaders]);

  useEffect(() => {
    loadSnippetsAndStats();
  }, [loadSnippetsAndStats]);

  // Execute Code in Playground
  const handleRunCode = async () => {
    if (!code.trim() || runningCode) return;
    setRunningCode(true);
    try {
      const res = await fetch(`${API_BASE}/coding/execute`, {
        method: 'POST',
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
        await loadSnippetsAndStats();
      }
    } catch (err) {
      setLastExecution({
        id: 'offline-error',
        language,
        status: 'error',
        stdout: '',
        stderr: `Execution failed: ${err}`,
        exit_code: 1,
        execution_time_ms: 0,
      });
    } finally {
      setRunningCode(false);
    }
  };

  // Save Current Code as Snippet
  const handleSaveSnippet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!saveTitle.trim()) return;
    setSavingSnippet(true);
    try {
      const tagList = saveTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      await fetch(`${API_BASE}/coding/snippets`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          title: saveTitle.trim(),
          language,
          code,
          description: saveDesc.trim() || null,
          tags: tagList,
        }),
      });

      setSaveModalOpen(false);
      setSaveTitle('');
      setSaveDesc('');
      setSaveTags('');
      await loadSnippetsAndStats();
    } catch {
      // Offline
    } finally {
      setSavingSnippet(false);
    }
  };

  // Toggle Favorite
  const handleToggleFavorite = async (snippet: CodeSnippetItem) => {
    try {
      await fetch(`${API_BASE}/coding/snippets/${snippet.id}`, {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({ is_favorite: !snippet.is_favorite }),
      });
      await loadSnippetsAndStats();
    } catch {
      // Offline
    }
  };

  // Delete Snippet
  const handleDeleteSnippet = async (snippetId: string) => {
    if (!window.confirm('Delete this code snippet?')) return;
    try {
      await fetch(`${API_BASE}/coding/snippets/${snippetId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      await loadSnippetsAndStats();
    } catch {
      // Offline
    }
  };

  // Load Snippet into Playground
  const handleLoadSnippetIntoPlayground = (snip: CodeSnippetItem) => {
    setCode(snip.code);
    setLanguage(snip.language);
    setActiveTab('playground');
  };

  // AI Generate Handler
  const handleGenerateCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!genTask.trim() || generating) return;
    setGenerating(true);
    setGeneratedResult(null);
    try {
      const res = await fetch(`${API_BASE}/coding/generate`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          task: genTask.trim(),
          language,
          constraints: genConstraints
            ? genConstraints.split(',').map((c) => c.trim()).filter(Boolean)
            : null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setGeneratedResult(data);
      }
    } catch {
      // Offline
    } finally {
      setGenerating(false);
    }
  };

  // AI Explain Handler
  const handleExplainCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!explainCodeInput.trim() || explaining) return;
    setExplaining(true);
    setExplainResult(null);
    try {
      const res = await fetch(`${API_BASE}/coding/explain`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          code: explainCodeInput.trim(),
          language,
          level: explainLevel,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setExplainResult(data);
      }
    } catch {
      // Offline
    } finally {
      setExplaining(false);
    }
  };

  // AI Debug Handler
  const handleDebugCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!debugCodeInput.trim() || debugging) return;
    setDebugging(true);
    setDebugResult(null);
    try {
      const res = await fetch(`${API_BASE}/coding/debug`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          code: debugCodeInput.trim(),
          language,
          error_message: debugErrorMsg.trim() || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setDebugResult(data);
      }
    } catch {
      // Offline
    } finally {
      setDebugging(false);
    }
  };

  // Filtered Snippets
  const filteredSnippets = useMemo(() => {
    return snippets.filter((s) => {
      const matchesSearch =
        !snippetSearch ||
        s.title.toLowerCase().includes(snippetSearch.toLowerCase()) ||
        (s.description && s.description.toLowerCase().includes(snippetSearch.toLowerCase())) ||
        s.tags.some((t) => t.toLowerCase().includes(snippetSearch.toLowerCase()));

      const matchesLang =
        snippetLangFilter === 'All' ||
        s.language.toLowerCase() === snippetLangFilter.toLowerCase();

      return matchesSearch && matchesLang;
    });
  }, [snippets, snippetSearch, snippetLangFilter]);

  // Distinct Languages for Filter Chips
  const languageOptions = useMemo(() => {
    const set = new Set<string>();
    snippets.forEach((s) => {
      if (s.language) set.add(s.language);
    });
    return ['All', ...Array.from(set)];
  }, [snippets]);

  return (
    <div className="coding-studio">
      {/* Header */}
      <header className="coding-studio__header">
        <div className="coding-studio__header-left">
          {onBack && (
            <button type="button" className="coding-studio__back-btn" onClick={onBack}>
              <ArrowLeft size={16} /> Back to Chat
            </button>
          )}
          <h1 className="coding-studio__title">
            <Code2 size={28} /> Developer Studio
          </h1>
          <p className="coding-studio__desc">
            Autonomous coding agent, sandboxed execution playground, and code snippet library.
          </p>
        </div>

        {/* Stats Bar */}
        <div className="coding-studio__stats-bar">
          <div className="coding-studio__stat-chip">
            <span className="coding-studio__stat-val">{stats.total_snippets}</span>
            <span className="coding-studio__stat-label">Snippets</span>
          </div>
          <div className="coding-studio__stat-chip">
            <span className="coding-studio__stat-val fav">{stats.favorite_snippets}</span>
            <span className="coding-studio__stat-label">Favorites</span>
          </div>
          <div className="coding-studio__stat-chip">
            <span className="coding-studio__stat-val">{stats.total_executions}</span>
            <span className="coding-studio__stat-label">Runs</span>
          </div>
          <div className="coding-studio__stat-chip">
            <span className="coding-studio__stat-val success">{stats.success_rate_percentage}%</span>
            <span className="coding-studio__stat-label">Success Rate</span>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <nav className="coding-studio__tabs">
        <button
          type="button"
          className={`coding-studio__tab ${activeTab === 'playground' ? 'active' : ''}`}
          onClick={() => setActiveTab('playground')}
        >
          <Terminal size={18} /> Code Playground & Runner
        </button>
        <button
          type="button"
          className={`coding-studio__tab ${activeTab === 'ai' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai')}
        >
          <Sparkles size={18} /> AI Code Assistant
        </button>
        <button
          type="button"
          className={`coding-studio__tab ${activeTab === 'snippets' ? 'active' : ''}`}
          onClick={() => setActiveTab('snippets')}
        >
          <FileCode size={18} /> Snippet Library ({snippets.length})
        </button>
      </nav>

      {/* Tab 1: Code Playground & Runner */}
      {activeTab === 'playground' && (
        <section className="coding-studio__content">
          <div className="coding-studio__playground-grid">
            {/* Editor Pane */}
            <div className="coding-studio__editor-pane">
              <div className="coding-studio__pane-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Code2 size={16} color="#38bdf8" />
                  <select
                    className="coding-studio__select"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    <option value="python">Python 3</option>
                    <option value="javascript">JavaScript (Node.js)</option>
                    <option value="typescript">TypeScript</option>
                    <option value="bash">Bash / Shell</option>
                    <option value="sql">SQL Query</option>
                    <option value="html">HTML</option>
                    <option value="css">CSS</option>
                  </select>
                </div>
                <div className="coding-studio__pane-actions">
                  <button
                    type="button"
                    className="coding-studio__btn"
                    onClick={() => setShowStdin(!showStdin)}
                  >
                    {showStdin ? 'Hide STDIN' : '+ STDIN'}
                  </button>
                  <button
                    type="button"
                    className="coding-studio__btn"
                    onClick={() => setSaveModalOpen(true)}
                  >
                    <Save size={14} /> Save
                  </button>
                  {onSendToChat && (
                    <button
                      type="button"
                      className="coding-studio__btn"
                      onClick={() => onSendToChat(`Here is my ${language} code:\n\`\`\`${language}\n${code}\n\`\`\``)}
                      title="Send code to Chat"
                    >
                      Send to Chat
                    </button>
                  )}
                  <button
                    type="button"
                    className="coding-studio__btn run"
                    onClick={handleRunCode}
                    disabled={runningCode}
                  >
                    <Play size={14} /> {runningCode ? 'Running...' : 'Run Code'}
                  </button>
                </div>
              </div>

              <textarea
                className="coding-studio__code-textarea"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                spellCheck={false}
                placeholder="// Write code here..."
              />

              {showStdin && (
                <input
                  type="text"
                  className="coding-studio__stdin-input"
                  placeholder="Standard Input (STDIN stream for your program)..."
                  value={stdinText}
                  onChange={(e) => setStdinText(e.target.value)}
                />
              )}
            </div>

            {/* Console Pane */}
            <div className="coding-studio__console-pane">
              <div className="coding-studio__pane-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Terminal size={16} color="#10b981" />
                  <span style={{ fontWeight: 600 }}>Live Output Console</span>
                </div>
                {lastExecution && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        padding: '0.2rem 0.5rem',
                        borderRadius: '4px',
                        fontWeight: 600,
                        background:
                          lastExecution.status === 'success'
                            ? 'rgba(16, 185, 129, 0.2)'
                            : 'rgba(239, 68, 68, 0.2)',
                        color:
                          lastExecution.status === 'success' ? '#34d399' : '#f87171',
                      }}
                    >
                      {lastExecution.status.toUpperCase()} (Exit {lastExecution.exit_code})
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                      {lastExecution.execution_time_ms}ms
                    </span>
                  </div>
                )}
              </div>

              {lastExecution ? (
                <div className="coding-studio__console-output">
                  {lastExecution.stdout && (
                    <div className="coding-studio__stdout">{lastExecution.stdout}</div>
                  )}
                  {lastExecution.stderr && (
                    <div className="coding-studio__stderr">{lastExecution.stderr}</div>
                  )}
                  {!lastExecution.stdout && !lastExecution.stderr && (
                    <div style={{ color: '#6b7280', fontStyle: 'italic' }}>
                      Program executed successfully with no output returned.
                    </div>
                  )}
                </div>
              ) : (
                <div className="coding-studio__console-output empty">
                  Click "Run Code" to execute script in the sandboxed runtime.
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Tab 2: AI Code Assistant */}
      {activeTab === 'ai' && (
        <section className="coding-studio__content">
          <div className="coding-studio__subtabs">
            <button
              type="button"
              className={`coding-studio__subtab-btn ${aiMode === 'generate' ? 'active' : ''}`}
              onClick={() => setAiMode('generate')}
            >
              <Sparkles size={16} /> Code Generation
            </button>
            <button
              type="button"
              className={`coding-studio__subtab-btn ${aiMode === 'explain' ? 'active' : ''}`}
              onClick={() => setAiMode('explain')}
            >
              <BookOpen size={16} /> Code Explanation
            </button>
            <button
              type="button"
              className={`coding-studio__subtab-btn ${aiMode === 'debug' ? 'active' : ''}`}
              onClick={() => setAiMode('debug')}
            >
              <Bug size={16} /> Bug Diagnostics & Fix
            </button>
          </div>

          {/* Submode 1: Generate */}
          {aiMode === 'generate' && (
            <div className="coding-studio__panel">
              <h3 style={{ margin: '0 0 1rem 0', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Sparkles size={20} color="#38bdf8" /> AI Code Synthesizer
              </h3>
              <form onSubmit={handleGenerateCode}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                      Task Description
                    </label>
                    <input
                      type="text"
                      className="coding-studio__input"
                      style={{ width: '100%' }}
                      placeholder="e.g. Implement an LRU Cache with O(1) get and put"
                      value={genTask}
                      onChange={(e) => setGenTask(e.target.value)}
                      required
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                      Target Language
                    </label>
                    <select
                      className="coding-studio__select"
                      style={{ width: '100%' }}
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                    >
                      <option value="python">Python</option>
                      <option value="typescript">TypeScript</option>
                      <option value="javascript">JavaScript</option>
                      <option value="bash">Bash / Shell</option>
                      <option value="sql">SQL</option>
                    </select>
                  </div>
                </div>

                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                    Constraints / Patterns (Optional comma-separated)
                  </label>
                  <input
                    type="text"
                    className="coding-studio__input"
                    style={{ width: '100%' }}
                    placeholder="e.g. no external dependencies, typing annotations, docstrings"
                    value={genConstraints}
                    onChange={(e) => setGenConstraints(e.target.value)}
                  />
                </div>

                <button
                  type="submit"
                  className="coding-studio__btn primary"
                  disabled={generating || !genTask.trim()}
                >
                  {generating ? 'Synthesizing...' : '⚡ Generate Code'}
                </button>
              </form>

              {generatedResult && (
                <div style={{ marginTop: '1.5rem', borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <h4 style={{ color: '#fff', margin: 0 }}>Generated {language} Solution</h4>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        type="button"
                        className="coding-studio__btn"
                        onClick={() => {
                          setCode(generatedResult.code);
                          setActiveTab('playground');
                        }}
                      >
                        <Play size={14} /> Open in Playground
                      </button>
                      <button
                        type="button"
                        className="coding-studio__btn"
                        onClick={() => {
                          navigator.clipboard.writeText(generatedResult.code);
                        }}
                      >
                        <Copy size={14} /> Copy
                      </button>
                    </div>
                  </div>
                  <pre className="coding-studio__code-preview" style={{ maxHeight: '300px' }}>
                    {generatedResult.code}
                  </pre>
                  <p style={{ fontSize: '0.9rem', color: '#d1d5db', marginTop: '0.5rem' }}>
                    {generatedResult.explanation}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Submode 2: Explain */}
          {aiMode === 'explain' && (
            <div className="coding-studio__panel">
              <h3 style={{ margin: '0 0 1rem 0', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <BookOpen size={20} color="#38bdf8" /> AI Code Explainer
              </h3>
              <form onSubmit={handleExplainCode}>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                    Audience Complexity Level
                  </label>
                  <select
                    className="coding-studio__select"
                    value={explainLevel}
                    onChange={(e) => setExplainLevel(e.target.value)}
                  >
                    <option value="eli5">ELI5 (Explain Like I'm 5)</option>
                    <option value="beginner">Beginner</option>
                    <option value="intermediate">Intermediate (Standard)</option>
                    <option value="expert">Expert (Deep Dive)</option>
                  </select>
                </div>

                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                    Paste Code to Explain
                  </label>
                  <textarea
                    className="coding-studio__textarea"
                    style={{ width: '100%', height: '140px', fontFamily: 'monospace' }}
                    placeholder="Paste function, routine, or snippet..."
                    value={explainCodeInput}
                    onChange={(e) => setExplainCodeInput(e.target.value)}
                    required
                  />
                </div>

                <button
                  type="submit"
                  className="coding-studio__btn primary"
                  disabled={explaining || !explainCodeInput.trim()}
                >
                  {explaining ? 'Analyzing...' : '🔍 Explain Code'}
                </button>
              </form>

              {explainResult && (
                <div style={{ marginTop: '1.5rem', borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '1rem' }}>
                  <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, color: '#e5e7eb', marginBottom: '1rem' }}>
                    {explainResult.explanation}
                  </div>
                  {explainResult.followups.length > 0 && (
                    <div>
                      <h5 style={{ color: '#9ca3af', margin: '0 0 0.5rem 0' }}>Suggested Next Concepts:</h5>
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {explainResult.followups.map((f, i) => (
                          <span
                            key={i}
                            style={{
                              background: 'rgba(255, 255, 255, 0.05)',
                              padding: '0.3rem 0.6rem',
                              borderRadius: '6px',
                              fontSize: '0.8rem',
                              color: '#38bdf8',
                            }}
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Submode 3: Debug */}
          {aiMode === 'debug' && (
            <div className="coding-studio__panel">
              <h3 style={{ margin: '0 0 1rem 0', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Bug size={20} color="#f87171" /> AI Bug Diagnostic & Fixer
              </h3>
              <form onSubmit={handleDebugCode}>
                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                    Buggy Code
                  </label>
                  <textarea
                    className="coding-studio__textarea"
                    style={{ width: '100%', height: '120px', fontFamily: 'monospace' }}
                    placeholder="Paste code experiencing issues..."
                    value={debugCodeInput}
                    onChange={(e) => setDebugCodeInput(e.target.value)}
                    required
                  />
                </div>

                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                    Error Message / Stack Trace (Optional)
                  </label>
                  <input
                    type="text"
                    className="coding-studio__input"
                    style={{ width: '100%' }}
                    placeholder="e.g. ZeroDivisionError, IndexError, TypeError..."
                    value={debugErrorMsg}
                    onChange={(e) => setDebugErrorMsg(e.target.value)}
                  />
                </div>

                <button
                  type="submit"
                  className="coding-studio__btn primary"
                  disabled={debugging || !debugCodeInput.trim()}
                >
                  {debugging ? 'Diagnosing...' : '🩺 Diagnose & Fix'}
                </button>
              </form>

              {debugResult && (
                <div style={{ marginTop: '1.5rem', borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '1rem' }}>
                  <div style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem' }}>
                    <strong style={{ color: '#f87171' }}>Root Cause Hypothesis:</strong>
                    <p style={{ margin: '0.3rem 0 0 0', color: '#fca5a5', fontSize: '0.9rem' }}>{debugResult.hypothesis}</p>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <h4 style={{ color: '#34d399', margin: 0 }}>Corrected Solution</h4>
                    <button
                      type="button"
                      className="coding-studio__btn"
                      onClick={() => {
                        setCode(debugResult.fixed_code);
                        setActiveTab('playground');
                      }}
                    >
                      <Play size={14} /> Open in Playground
                    </button>
                  </div>
                  <pre className="coding-studio__code-preview" style={{ maxHeight: '250px' }}>
                    {debugResult.fixed_code}
                  </pre>
                  <p style={{ fontSize: '0.85rem', color: '#9ca3af' }}>{debugResult.fix}</p>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Tab 3: Snippet Library */}
      {activeTab === 'snippets' && (
        <section className="coding-studio__content">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '1rem', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, maxWidth: '400px' }}>
              <Search size={16} color="#9ca3af" />
              <input
                type="text"
                className="coding-studio__input"
                style={{ width: '100%' }}
                placeholder="Search snippets by title, tag, or code..."
                value={snippetSearch}
                onChange={(e) => setSnippetSearch(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>Language:</span>
              <select
                className="coding-studio__select"
                value={snippetLangFilter}
                onChange={(e) => setSnippetLangFilter(e.target.value)}
              >
                {languageOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {filteredSnippets.length > 0 ? (
            <div className="coding-studio__snippets-grid">
              {filteredSnippets.map((snip) => (
                <div key={snip.id} className="coding-studio__snippet-card">
                  <div className="coding-studio__snippet-header">
                    <div>
                      <h4 className="coding-studio__snippet-title">{snip.title}</h4>
                      <span className="coding-studio__lang-badge">{snip.language}</span>
                    </div>
                    <button
                      type="button"
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
                      onClick={() => handleToggleFavorite(snip)}
                    >
                      <Star
                        size={18}
                        color={snip.is_favorite ? '#f59e0b' : '#6b7280'}
                        fill={snip.is_favorite ? '#f59e0b' : 'none'}
                      />
                    </button>
                  </div>

                  <pre className="coding-studio__code-preview">
                    {snip.code}
                  </pre>

                  {snip.description && (
                    <p style={{ fontSize: '0.8rem', color: '#9ca3af', marginBottom: '0.75rem' }}>
                      {snip.description}
                    </p>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
                    <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                      {snip.tags.map((t, idx) => (
                        <span key={idx} style={{ fontSize: '0.7rem', color: '#38bdf8', background: 'rgba(56, 189, 248, 0.1)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>
                          #{t}
                        </span>
                      ))}
                    </div>

                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <button
                        type="button"
                        className="coding-studio__btn"
                        onClick={() => handleLoadSnippetIntoPlayground(snip)}
                        title="Load into Playground"
                      >
                        <Play size={13} />
                      </button>
                      <button
                        type="button"
                        className="coding-studio__btn"
                        onClick={() => navigator.clipboard.writeText(snip.code)}
                        title="Copy Code"
                      >
                        <Copy size={13} />
                      </button>
                      <button
                        type="button"
                        className="coding-studio__btn danger"
                        onClick={() => handleDeleteSnippet(snip.id)}
                        title="Delete Snippet"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="coding-studio__zero-state">
              <Code2 size={48} className="coding-studio__zero-icon" />
              <h3>No Code Snippets Found</h3>
              <p>Save snippets from your playground or generate solutions with AI to build your library.</p>
            </div>
          )}
        </section>
      )}

      {/* Save Snippet Modal */}
      {saveModalOpen && (
        <div className="coding-studio__modal-overlay">
          <div className="coding-studio__modal">
            <h3 style={{ margin: '0 0 1rem 0', color: '#fff' }}>Save Code to Snippets</h3>
            <form onSubmit={handleSaveSnippet}>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                  Snippet Title
                </label>
                <input
                  type="text"
                  className="coding-studio__input"
                  style={{ width: '100%' }}
                  placeholder="e.g. Quick Sort Algorithm"
                  value={saveTitle}
                  onChange={(e) => setSaveTitle(e.target.value)}
                  required
                />
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                  Description (Optional)
                </label>
                <input
                  type="text"
                  className="coding-studio__input"
                  style={{ width: '100%' }}
                  placeholder="e.g. Recursive divide-and-conquer sorting"
                  value={saveDesc}
                  onChange={(e) => setSaveDesc(e.target.value)}
                />
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.4rem' }}>
                  Tags (Comma-separated)
                </label>
                <input
                  type="text"
                  className="coding-studio__input"
                  style={{ width: '100%' }}
                  placeholder="algorithms, python, sorting"
                  value={saveTags}
                  onChange={(e) => setSaveTags(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button
                  type="button"
                  className="coding-studio__btn"
                  onClick={() => setSaveModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="coding-studio__btn primary"
                  disabled={savingSnippet || !saveTitle.trim()}
                >
                  {savingSnippet ? 'Saving...' : 'Save Snippet'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CodingStudio;
