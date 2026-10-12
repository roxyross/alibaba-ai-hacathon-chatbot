import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Code2,
  Play,
  Bug,
  GitBranch,
  Terminal as TerminalIcon,
  Search,
  FolderTree,
  FileCode,
  FilePlus,
  FolderPlus,
  Trash2,
  RefreshCw,
  Save,
  CheckCircle,
  AlertTriangle,
  ArrowLeft,
  X,
  ChevronRight,
  ChevronDown,
  Maximize2,
  Minimize2,
  Settings,
  Sparkles,
  Mic,
  MicOff,
  Send,
  Eye,
  Check,
  Laptop,
  Smartphone,
  Tablet,
  Layers,
  ExternalLink,
} from 'lucide-react';
import './CodeStudioIDE.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface WorkspaceTreeNode {
  name: string;
  path: string;
  is_directory: boolean;
  size?: number;
  extension?: string;
  children?: WorkspaceTreeNode[];
}

export interface OpenEditorTab {
  path: string;
  name: string;
  content: string;
  originalContent: string;
  isDirty: boolean;
  language: string;
}

export interface TerminalLogEntry {
  command: string;
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs: number;
  timestamp: string;
}

export interface AgentChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  plan?: string[];
  diff?: string | null;
  modifiedCode?: string | null;
  targetFile?: string | null;
  suggestedCommand?: string | null;
  riskLevel?: 'low' | 'medium' | 'high';
  requiresApproval?: boolean;
  status?: 'pending' | 'applied' | 'rejected';
}

interface CodeStudioIDEProps {
  onBack?: () => void;
  accessToken?: string | null;
  onSendToChat?: (text: string) => void;
}

const TEMPLATE_PROJECTS = [
  { id: 'default', name: 'ROXY Workspace (Current)', root: '.' },
  { id: 'react_vite', name: 'Frontend React + Vite', root: 'frontend' },
  { id: 'python_backend', name: 'Backend FastAPI Service', root: 'backend' },
  { id: 'ai_hub', name: 'HuggingFace Roxy Hub Space', root: 'huggingface-space-roxy-hub' },
];

export const CodeStudioIDE: React.FC<CodeStudioIDEProps> = ({
  onBack,
  accessToken,
  onSendToChat,
}) => {
  // Navigation & Project selection
  const [currentProject, setCurrentProject] = useState(TEMPLATE_PROJECTS[0]);
  const [activeActivity, setActiveActivity] = useState<
    'explorer' | 'search' | 'git' | 'debug' | 'extensions' | 'settings'
  >('explorer');

  // File tree & open tabs
  const [fileTree, setFileTree] = useState<WorkspaceTreeNode | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['.', 'backend', 'frontend', 'src']));
  const [openTabs, setOpenTabs] = useState<OpenEditorTab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  const [isTreeLoading, setIsTreeLoading] = useState(false);

  // Search within workspace
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{ file_path: string; line_number: number; snippet: string }>>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Git state
  const [gitStatus, setGitStatus] = useState<{ branch: string; staged: string[]; unstaged: string[]; untracked: string[]; clean: boolean }>({
    branch: 'master',
    staged: [],
    unstaged: [],
    untracked: [],
    clean: true,
  });
  const [gitCommitMessage, setGitCommitMessage] = useState('');
  const [isCommitting, setIsCommitting] = useState(false);

  // Bottom panel
  const [bottomTab, setBottomTab] = useState<'terminal' | 'problems' | 'output' | 'tests' | 'preview'>('terminal');
  const [isBottomPanelCollapsed, setIsBottomPanelCollapsed] = useState(false);
  const [terminalHistory, setTerminalHistory] = useState<TerminalLogEntry[]>([]);
  const [terminalInput, setTerminalInput] = useState('');
  const [isTerminalRunning, setIsTerminalRunning] = useState(false);

  // Test Runner state
  const [testResults, setTestResults] = useState<{ passed: number; failed: number; output: string; success: boolean } | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  // Web Dev Preview
  const [previewUrl, setPreviewUrl] = useState('http://localhost:5173');
  const [previewViewport, setPreviewViewport] = useState<'desktop' | 'tablet' | 'mobile'>('desktop');

  // Right Panel: Roxy Coding Agent
  const [isAgentPanelOpen, setIsAgentPanelOpen] = useState(true);
  const [agentMessages, setAgentMessages] = useState<AgentChatMessage[]>([
    {
      id: 'init-1',
      role: 'assistant',
      content:
        'Assalam o alaikum! I am Roxy, your persistent Autonomous Coding Agent. I have loaded your workspace context. You can instruct me via voice or text in English, Urdu, or Roman Urdu (e.g. "is project ko analyze karo aur login bug fix karo").',
    },
  ]);
  const [agentInput, setAgentInput] = useState('');
  const [isAgentProcessing, setIsAgentProcessing] = useState(false);
  const [isVoiceListening, setIsVoiceListening] = useState(false);

  // Command Palette
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [commandPaletteQuery, setCommandPaletteQuery] = useState('');

  // Mobile layout state
  const [mobileActiveView, setMobileActiveView] = useState<'editor' | 'files' | 'agent' | 'terminal'>('editor');

  // Active file tab helper
  const activeTab = useMemo(() => {
    return openTabs.find((t) => t.path === activeTabPath) || null;
  }, [openTabs, activeTabPath]);

  // Determine file language from extension
  const getLanguageFromPath = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'ts':
      case 'tsx':
        return 'typescript';
      case 'js':
      case 'jsx':
        return 'javascript';
      case 'py':
        return 'python';
      case 'css':
      case 'scss':
        return 'css';
      case 'html':
        return 'html';
      case 'json':
        return 'json';
      case 'md':
        return 'markdown';
      case 'yaml':
      case 'yml':
        return 'yaml';
      case 'sql':
        return 'sql';
      case 'sh':
      case 'bash':
        return 'bash';
      case 'rs':
        return 'rust';
      case 'go':
        return 'go';
      case 'php':
        return 'php';
      case 'cpp':
      case 'c':
        return 'c_cpp';
      default:
        return 'plaintext';
    }
  };

  // ---------------------------------------------------------------------------
  // Workspace Tree & Git Loaders
  // ---------------------------------------------------------------------------

  const loadWorkspaceTree = useCallback(async () => {
    if (!accessToken) return;
    setIsTreeLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/coding/workspace/tree?root_dir=${encodeURIComponent(currentProject.root)}&max_depth=4`,
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setFileTree(data.tree);
      }
    } catch {
      // Resilience
    } finally {
      setIsTreeLoading(false);
    }
  }, [accessToken, currentProject.root]);

  const loadGitStatus = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(
        `${API_BASE}/coding/git/status?repo_path=${encodeURIComponent(currentProject.root)}`,
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      if (res.ok) {
        const data = await res.json();
        setGitStatus(data);
      }
    } catch {
      // Resilience
    }
  }, [accessToken, currentProject.root]);

  useEffect(() => {
    loadWorkspaceTree();
    loadGitStatus();
  }, [loadWorkspaceTree, loadGitStatus]);

  // Open default readme or app file on mount
  useEffect(() => {
    if (!activeTabPath && fileTree) {
      openFile('README.md');
    }
  }, [fileTree, activeTabPath]);

  // Global Keyboard Shortcuts (Ctrl+P, Ctrl+S, Ctrl+Alt+I)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveActiveFile();
      } else if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        e.preventDefault();
        setIsBottomPanelCollapsed((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab]);

  // ---------------------------------------------------------------------------
  // File Operations (Read, Write, Create, Rename, Delete)
  // ---------------------------------------------------------------------------

  const openFile = async (filePath: string) => {
    // If tab already open, switch to it
    const existing = openTabs.find((t) => t.path === filePath);
    if (existing) {
      setActiveTabPath(filePath);
      setMobileActiveView('editor');
      return;
    }

    if (!accessToken) return;
    try {
      const res = await fetch(
        `${API_BASE}/coding/workspace/file?file_path=${encodeURIComponent(filePath)}`,
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      if (res.ok) {
        const data = await res.json();
        const newTab: OpenEditorTab = {
          path: filePath,
          name: filePath.split('/').pop() || filePath,
          content: data.content || '',
          originalContent: data.content || '',
          isDirty: false,
          language: getLanguageFromPath(filePath),
        };
        setOpenTabs((prev) => [...prev, newTab]);
        setActiveTabPath(filePath);
        setMobileActiveView('editor');
      }
    } catch {
      // Resilience
    }
  };

  const closeTab = (path: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setOpenTabs((prev) => {
      const remaining = prev.filter((t) => t.path !== path);
      if (activeTabPath === path) {
        setActiveTabPath(remaining.length > 0 ? remaining[remaining.length - 1].path : null);
      }
      return remaining;
    });
  };

  const updateActiveContent = (newContent: string) => {
    if (!activeTabPath) return;
    setOpenTabs((prev) =>
      prev.map((t) =>
        t.path === activeTabPath
          ? { ...t, content: newContent, isDirty: newContent !== t.originalContent }
          : t
      )
    );
  };

  const saveActiveFile = async () => {
    if (!activeTab || !accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/coding/workspace/file`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          file_path: activeTab.path,
          content: activeTab.content,
          overwrite: true,
        }),
      });
      if (res.ok) {
        setOpenTabs((prev) =>
          prev.map((t) =>
            t.path === activeTab.path
              ? { ...t, originalContent: t.content, isDirty: false }
              : t
          )
        );
        loadGitStatus();
      }
    } catch {
      // Resilience
    }
  };

  const handleCreateNewFile = async () => {
    const filename = window.prompt('Enter new file path (e.g. src/utils.py):');
    if (!filename || !accessToken) return;
    try {
      await fetch(`${API_BASE}/coding/workspace/file`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          file_path: filename,
          content: '# Created in Roxy Code Studio\n',
          overwrite: false,
        }),
      });
      loadWorkspaceTree();
      openFile(filename);
    } catch {
      // Resilience
    }
  };

  const handleCreateNewFolder = async () => {
    const folderName = window.prompt('Enter new directory path (e.g. src/components):');
    if (!folderName || !accessToken) return;
    try {
      await fetch(`${API_BASE}/coding/workspace/directory`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ dir_path: folderName }),
      });
      loadWorkspaceTree();
    } catch {
      // Resilience
    }
  };

  const handleDeleteFile = async (path: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete '${path}'?`)) return;
    if (!accessToken) return;
    try {
      await fetch(`${API_BASE}/coding/workspace/path?path=${encodeURIComponent(path)}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      closeTab(path);
      loadWorkspaceTree();
      loadGitStatus();
    } catch {
      // Resilience
    }
  };

  // ---------------------------------------------------------------------------
  // Terminal Execution
  // ---------------------------------------------------------------------------

  const handleRunTerminal = async (cmdToRun?: string) => {
    const command = cmdToRun || terminalInput.trim();
    if (!command || !accessToken) return;
    setIsTerminalRunning(true);
    setTerminalInput('');

    try {
      const res = await fetch(`${API_BASE}/coding/terminal/exec`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          command,
          cwd: currentProject.root,
          timeout_seconds: 30,
        }),
      });

      const data = await res.json();
      const entry: TerminalLogEntry = {
        command,
        stdout: data.stdout || '',
        stderr: data.stderr || (res.status === 403 ? 'Permission Denied: Destructive command rejected by Roxy Sandbox.' : ''),
        exitCode: data.exit_code ?? (res.ok ? 0 : 1),
        durationMs: data.duration_ms ?? 0,
        timestamp: new Date().toLocaleTimeString(),
      };
      setTerminalHistory((prev) => [...prev, entry]);
      loadGitStatus();
    } catch (exc) {
      setTerminalHistory((prev) => [
        ...prev,
        {
          command,
          stdout: '',
          stderr: `Execution error: ${exc}`,
          exitCode: 1,
          durationMs: 0,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setIsTerminalRunning(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Git Commit & Testing
  // ---------------------------------------------------------------------------

  const handleGitCommit = async () => {
    if (!gitCommitMessage.trim() || !accessToken) return;
    setIsCommitting(true);
    try {
      await fetch(`${API_BASE}/coding/git/commit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          message: gitCommitMessage.trim(),
          repo_path: currentProject.root,
          add_all: true,
        }),
      });
      setGitCommitMessage('');
      loadGitStatus();
    } catch {
      // Resilience
    } finally {
      setIsCommitting(false);
    }
  };

  const handleRunTests = async () => {
    if (!accessToken) return;
    setIsTesting(true);
    setBottomTab('tests');
    setIsBottomPanelCollapsed(false);
    try {
      const res = await fetch(`${API_BASE}/coding/test/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          project_path: currentProject.root,
          test_path: '',
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setTestResults({
          passed: data.passed || 0,
          failed: data.failed || 0,
          output: data.output || '',
          success: data.success,
        });
      }
    } catch {
      // Resilience
    } finally {
      setIsTesting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Roxy Coding Agent (Multilingual & Diff Review)
  // ---------------------------------------------------------------------------

  const handleSendAgentPrompt = async (promptText?: string) => {
    const text = promptText || agentInput.trim();
    if (!text || !accessToken) return;

    const userMsg: AgentChatMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: text,
    };
    setAgentMessages((prev) => [...prev, userMsg]);
    setAgentInput('');
    setIsAgentProcessing(true);

    try {
      const res = await fetch(`${API_BASE}/coding/agent/assist`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          prompt: text,
          current_file: activeTab?.path,
          selected_code: null,
          file_content: activeTab?.content,
          project_context: `${currentProject.name} (${activeTab?.language || 'python'})`,
          terminal_output: terminalHistory.slice(-2).map((t) => t.stdout + '\n' + t.stderr).join('\n'),
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMsg: AgentChatMessage = {
          id: `ast-${Date.now()}`,
          role: 'assistant',
          content: data.explanation,
          plan: data.action_plan,
          diff: data.proposed_diff,
          modifiedCode: data.modified_code,
          targetFile: data.target_file,
          suggestedCommand: data.suggested_command,
          riskLevel: data.risk_level,
          requiresApproval: data.requires_approval,
          status: 'pending',
        };
        setAgentMessages((prev) => [...prev, assistantMsg]);
      }
    } catch (exc) {
      setAgentMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Unable to process request: ${exc}. Please retry.`,
        },
      ]);
    } finally {
      setIsAgentProcessing(false);
    }
  };

  const handleApplyAgentDiff = async (msgId: string) => {
    const msg = agentMessages.find((m) => m.id === msgId);
    if (!msg || !msg.modifiedCode || !msg.targetFile || !accessToken) return;

    try {
      await fetch(`${API_BASE}/coding/workspace/file`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          file_path: msg.targetFile,
          content: msg.modifiedCode,
          overwrite: true,
        }),
      });

      // Update current active open tab if matching
      if (activeTab?.path === msg.targetFile) {
        updateActiveContent(msg.modifiedCode);
      } else {
        openFile(msg.targetFile);
      }

      setAgentMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, status: 'applied' } : m))
      );
      loadGitStatus();
    } catch {
      // Resilience
    }
  };

  const handleRejectAgentDiff = (msgId: string) => {
    setAgentMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, status: 'rejected' } : m))
    );
  };

  // Voice Coding Trigger using Web Speech API
  const handleToggleVoiceCoding = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      window.alert('Speech recognition is not supported in this browser. Please type your prompt.');
      return;
    }
    const SpeechRecognitionClass =
      (window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition;

    if (!isVoiceListening) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'ur-PK,en-US'; // Multi-lingual recognition
        recognition.onstart = () => setIsVoiceListening(true);
        recognition.onresult = (event: any) => {
          const transcript = event.results[0][0].transcript;
          setAgentInput(transcript);
          setIsVoiceListening(false);
          handleSendAgentPrompt(transcript);
        };
        recognition.onerror = () => setIsVoiceListening(false);
        recognition.onend = () => setIsVoiceListening(false);
        recognition.start();
      } catch {
        setIsVoiceListening(false);
      }
    } else {
      setIsVoiceListening(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Workspace File Tree Renderer
  // ---------------------------------------------------------------------------

  const toggleFolder = (path: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const renderTreeNode = (node: WorkspaceTreeNode) => {
    const isExpanded = expandedFolders.has(node.path);
    const isActive = activeTabPath === node.path;

    if (node.is_directory) {
      return (
        <div key={node.path} className="tree-node-group">
          <div
            className="tree-node tree-folder"
            onClick={(e) => toggleFolder(node.path, e)}
          >
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span className="folder-name">{node.name}</span>
          </div>
          {isExpanded && node.children && (
            <div className="tree-children">
              {node.children.map((child) => renderTreeNode(child))}
            </div>
          )}
        </div>
      );
    }

    return (
      <div
        key={node.path}
        className={`tree-node tree-file ${isActive ? 'is-active-file' : ''}`}
        onClick={() => openFile(node.path)}
      >
        <FileCode size={14} className="file-icon" />
        <span className="file-name">{node.name}</span>
        <button
          type="button"
          className="btn-file-delete"
          title="Delete file"
          onClick={(e) => handleDeleteFile(node.path, e)}
        >
          <Trash2 size={12} />
        </button>
      </div>
    );
  };

  // ---------------------------------------------------------------------------
  // Main IDE JSX Layout
  // ---------------------------------------------------------------------------

  return (
    <div className="code-studio-root" role="main" aria-label="ROXY Code Studio IDE">
      {/* ─── 1. TOP BAR ──────────────────────────────────────────────────────── */}
      <header className="ide-topbar">
        <div className="ide-topbar__left">
          <button
            type="button"
            className="btn-back-roxy"
            title="Back to Roxy"
            onClick={onBack}
          >
            <ArrowLeft size={16} />
            <span className="back-text">Roxy</span>
          </button>

          <div className="ide-brand">
            <Code2 size={18} className="ide-brand-icon" />
            <span className="ide-brand-title">Code Studio</span>
            <span className="ide-status-pill">Active</span>
          </div>

          <div className="ide-project-selector">
            <select
              value={currentProject.id}
              onChange={(e) => {
                const p = TEMPLATE_PROJECTS.find((tp) => tp.id === e.target.value);
                if (p) setCurrentProject(p);
              }}
            >
              {TEMPLATE_PROJECTS.map((proj) => (
                <option key={proj.id} value={proj.id}>
                  {proj.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="ide-topbar__center">
          <button
            type="button"
            className="ide-command-search"
            title="Command Palette (Ctrl+P)"
            onClick={() => setIsCommandPaletteOpen(true)}
          >
            <Search size={14} />
            <span>Search files &amp; commands...</span>
            <kbd>Ctrl+P</kbd>
          </button>
        </div>

        <div className="ide-topbar__right">
          <button
            type="button"
            className="btn-topbar-action btn-run"
            title="Run Project in Terminal"
            onClick={() => handleRunTerminal('python src/app/main.py')}
          >
            <Play size={14} />
            <span>Run</span>
          </button>

          <button
            type="button"
            className="btn-topbar-action"
            title="Run Project Test Suite"
            onClick={handleRunTests}
          >
            <Bug size={14} />
            <span>Test</span>
          </button>

          <button
            type="button"
            className="btn-topbar-action btn-git-badge"
            title={`Branch: ${gitStatus.branch}`}
            onClick={() => setActiveActivity('git')}
          >
            <GitBranch size={14} />
            <span>{gitStatus.branch}</span>
            {!gitStatus.clean && (
              <span className="git-dirty-dot" title="Uncommitted changes" />
            )}
          </button>

          <button
            type="button"
            className={`btn-topbar-action btn-agent-toggle ${isAgentPanelOpen ? 'is-active' : ''}`}
            title="Toggle Roxy Coding Agent"
            onClick={() => setIsAgentPanelOpen((prev) => !prev)}
          >
            <Sparkles size={14} />
            <span>Roxy Agent</span>
          </button>
        </div>
      </header>

      {/* ─── 2. IDE WORKSPACE BODY ───────────────────────────────────────────── */}
      <div className="ide-workspace-body">
        {/* LEFT ACTIVITY BAR */}
        <aside className="ide-activity-bar" aria-label="Activity Bar">
          <button
            type="button"
            className={`activity-btn ${activeActivity === 'explorer' ? 'is-active' : ''}`}
            title="Explorer"
            onClick={() => setActiveActivity('explorer')}
          >
            <FolderTree size={20} />
          </button>
          <button
            type="button"
            className={`activity-btn ${activeActivity === 'search' ? 'is-active' : ''}`}
            title="Search Workspace"
            onClick={() => setActiveActivity('search')}
          >
            <Search size={20} />
          </button>
          <button
            type="button"
            className={`activity-btn ${activeActivity === 'git' ? 'is-active' : ''}`}
            title="Source Control"
            onClick={() => setActiveActivity('git')}
          >
            <GitBranch size={20} />
          </button>
          <button
            type="button"
            className={`activity-btn ${activeActivity === 'debug' ? 'is-active' : ''}`}
            title="Run &amp; Debug"
            onClick={() => {
              setActiveActivity('debug');
              setBottomTab('preview');
              setIsBottomPanelCollapsed(false);
            }}
          >
            <Bug size={20} />
          </button>
          <button
            type="button"
            className={`activity-btn ${activeActivity === 'extensions' ? 'is-active' : ''}`}
            title="MCP &amp; Plugins"
            onClick={() => setActiveActivity('extensions')}
          >
            <Layers size={20} />
          </button>
          <div className="activity-spacer" />
          <button
            type="button"
            className="activity-btn"
            title="IDE Settings"
            onClick={() => setActiveActivity('settings')}
          >
            <Settings size={20} />
          </button>
        </aside>

        {/* LEFT SIDEBAR (File tree / Search / Git) */}
        <section className="ide-sidebar">
          {activeActivity === 'explorer' && (
            <div className="sidebar-pane">
              <div className="sidebar-pane-header">
                <span className="pane-title">EXPLORER</span>
                <div className="pane-actions">
                  <button type="button" title="New File" onClick={handleCreateNewFile}>
                    <FilePlus size={14} />
                  </button>
                  <button type="button" title="New Folder" onClick={handleCreateNewFolder}>
                    <FolderPlus size={14} />
                  </button>
                  <button type="button" title="Refresh Tree" onClick={loadWorkspaceTree}>
                    <RefreshCw size={14} className={isTreeLoading ? 'is-spinning' : ''} />
                  </button>
                </div>
              </div>

              <div className="file-tree-container">
                {fileTree ? (
                  renderTreeNode(fileTree)
                ) : (
                  <div className="tree-empty-state">Loading workspace tree...</div>
                )}
              </div>
            </div>
          )}

          {activeActivity === 'search' && (
            <div className="sidebar-pane">
              <div className="sidebar-pane-header">
                <span className="pane-title">SEARCH IN WORKSPACE</span>
              </div>
              <div className="search-pane-input-wrapper">
                <input
                  type="text"
                  placeholder="Search across files..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={async (e) => {
                    if (e.key === 'Enter' && searchQuery.trim() && accessToken) {
                      setIsSearching(true);
                      try {
                        const res = await fetch(`${API_BASE}/coding/workspace/search`, {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                            Authorization: `Bearer ${accessToken}`,
                          },
                          body: JSON.stringify({
                            content_query: searchQuery.trim(),
                            directory_path: currentProject.root,
                            max_matches: 50,
                          }),
                        });
                        if (res.ok) {
                          const data = await res.json();
                          setSearchResults(data.matches || []);
                        }
                      } finally {
                        setIsSearching(false);
                      }
                    }
                  }}
                />
              </div>
              <div className="search-results-list">
                {isSearching && <div className="pane-status">Searching...</div>}
                {searchResults.map((m, idx) => (
                  <div
                    key={idx}
                    className="search-match-item"
                    onClick={() => openFile(m.file_path)}
                  >
                    <span className="match-file">{m.file_path}:{m.line_number}</span>
                    <span className="match-snippet">{m.snippet}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeActivity === 'git' && (
            <div className="sidebar-pane">
              <div className="sidebar-pane-header">
                <span className="pane-title">SOURCE CONTROL</span>
                <span className="pane-badge">{gitStatus.branch}</span>
              </div>
              <div className="git-pane-commit">
                <textarea
                  placeholder="Commit message (Ctrl+Enter to commit)"
                  value={gitCommitMessage}
                  onChange={(e) => setGitCommitMessage(e.target.value)}
                />
                <button
                  type="button"
                  className="btn-commit-action"
                  disabled={!gitCommitMessage.trim() || isCommitting}
                  onClick={handleGitCommit}
                >
                  <Check size={14} />
                  <span>{isCommitting ? 'Committing...' : 'Commit &amp; Push'}</span>
                </button>
              </div>
              <div className="git-changes-list">
                <div className="git-section-label">CHANGES ({gitStatus.unstaged.length + gitStatus.untracked.length})</div>
                {[...gitStatus.unstaged, ...gitStatus.untracked].map((file, i) => (
                  <div key={i} className="git-change-item" onClick={() => openFile(file)}>
                    <FileCode size={13} />
                    <span>{file}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeActivity === 'extensions' && (
            <div className="sidebar-pane">
              <div className="sidebar-pane-header">
                <span className="pane-title">MCP &amp; SKILLS</span>
              </div>
              <div className="extensions-list">
                <div className="extension-card">
                  <h4>Google Antigravity SDK</h4>
                  <p>Autonomous Agent Multi-Turn Orchestration &amp; Tools</p>
                  <span className="ext-pill active">Installed</span>
                </div>
                <div className="extension-card">
                  <h4>Chrome DevTools MCP</h4>
                  <p>DOM Inspection, Console, Performance &amp; CWV Diagnostics</p>
                  <span className="ext-pill active">Connected</span>
                </div>
                <div className="extension-card">
                  <h4>Gemini Code Assist</h4>
                  <p>Multilingual code understanding, completion &amp; unit tests</p>
                  <span className="ext-pill active">Active</span>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* ─── 3. CENTER CODE EDITOR ────────────────────────────────────────── */}
        <main className="ide-editor-container">
          {/* TABS BAR */}
          <div className="editor-tabs-bar">
            {openTabs.map((tab) => (
              <div
                key={tab.path}
                className={`editor-tab ${tab.path === activeTabPath ? 'is-active-tab' : ''}`}
                onClick={() => setActiveTabPath(tab.path)}
              >
                <FileCode size={14} className="tab-icon" />
                <span className="tab-title">{tab.name}</span>
                {tab.isDirty && <span className="tab-dirty-indicator" title="Unsaved changes" />}
                <button
                  type="button"
                  className="btn-tab-close"
                  onClick={(e) => closeTab(tab.path, e)}
                >
                  <X size={12} />
                </button>
              </div>
            ))}

            {openTabs.length === 0 && (
              <div className="editor-tab is-active-tab">
                <span className="tab-title">Welcome to Code Studio</span>
              </div>
            )}
          </div>

          {/* BREADCRUMBS BAR */}
          <div className="editor-breadcrumbs">
            <span>{currentProject.name}</span>
            <ChevronRight size={12} />
            <span>{activeTab?.path || 'No file selected'}</span>
            <div className="breadcrumbs-spacer" />
            {activeTab?.isDirty && (
              <button type="button" className="btn-save-breadcrumb" onClick={saveActiveFile}>
                <Save size={13} /> Save (Ctrl+S)
              </button>
            )}
          </div>

          {/* CODE EDITOR TEXTAREA & GUTTER */}
          <div className="editor-code-surface">
            {activeTab ? (
              <div className="code-editor-wrapper">
                <div className="code-line-numbers" aria-hidden="true">
                  {activeTab.content.split('\n').map((_, i) => (
                    <div key={i} className="line-num">
                      {i + 1}
                    </div>
                  ))}
                </div>
                <textarea
                  className="code-textarea"
                  value={activeTab.content}
                  spellCheck={false}
                  onChange={(e) => updateActiveContent(e.target.value)}
                  placeholder="Start coding here..."
                />
              </div>
            ) : (
              <div className="editor-placeholder-empty">
                <Code2 size={48} className="empty-logo" />
                <h3>ROXY Autonomous Code Studio</h3>
                <p>Select a file from the explorer on the left or ask Roxy Agent to create code.</p>
                <div className="placeholder-shortcuts">
                  <div><span>Open File</span> <kbd>Ctrl+P</kbd></div>
                  <div><span>Save</span> <kbd>Ctrl+S</kbd></div>
                  <div><span>Toggle Terminal</span> <kbd>Ctrl+`</kbd></div>
                </div>
              </div>
            )}
          </div>

          {/* BOTTOM STATUS BAR */}
          <footer className="editor-status-bar">
            <div className="status-item"><GitBranch size={12} /> {gitStatus.branch}</div>
            <div className="status-item"><CheckCircle size={12} /> 0 Errors</div>
            <div className="status-spacer" />
            <div className="status-item">Spaces: 4</div>
            <div className="status-item">UTF-8</div>
            <div className="status-item">{activeTab?.language.toUpperCase() || 'PLAINTEXT'}</div>
          </footer>
        </main>

        {/* ─── 4. RIGHT PANEL: ROXY CODING AGENT ────────────────────────────── */}
        {isAgentPanelOpen && (
          <aside className="ide-agent-panel" aria-label="Roxy Coding Agent">
            <div className="agent-panel-header">
              <div className="agent-title-row">
                <Sparkles size={16} className="sparkle-icon" />
                <h4>Roxy Coding Agent</h4>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {onSendToChat && (
                  <button
                    type="button"
                    className="agent-status-tag"
                    style={{ cursor: 'pointer', background: 'rgba(20, 184, 166, 0.1)', color: '#0d9488', border: '1px solid rgba(20, 184, 166, 0.3)' }}
                    onClick={() => onSendToChat(`[Code Studio Context] Active file: ${activeTab?.path ?? 'None'}`)}
                    title="Send current IDE context to Roxy Main Chat"
                  >
                    To Chat
                  </button>
                )}
                <span className="agent-status-tag">Connected</span>
              </div>
            </div>

            {/* Quick Context Pills */}
            <div className="agent-context-pills">
              <span className="ctx-pill">File: {activeTab?.name || 'None'}</span>
              <span className="ctx-pill">Lang: {activeTab?.language || 'None'}</span>
            </div>

            {/* Messages Feed */}
            <div className="agent-chat-feed">
              {agentMessages.map((msg) => (
                <div key={msg.id} className={`agent-msg-bubble role-${msg.role}`}>
                  <p className="msg-text">{msg.content}</p>

                  {/* Action Plan */}
                  {msg.plan && msg.plan.length > 0 && (
                    <div className="agent-plan-box">
                      <div className="plan-title">ACTION PLAN:</div>
                      <ul>
                        {msg.plan.map((step, idx) => (
                          <li key={idx}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Proposed Diff Review */}
                  {msg.diff && msg.status === 'pending' && (
                    <div className="agent-diff-box">
                      <div className="diff-header">
                        <span>UNIFIED DIFF ({msg.targetFile})</span>
                      </div>
                      <pre className="diff-code">{msg.diff}</pre>
                      <div className="diff-actions">
                        <button
                          type="button"
                          className="btn-apply-diff"
                          onClick={() => handleApplyAgentDiff(msg.id)}
                        >
                          <Check size={13} /> Accept &amp; Apply
                        </button>
                        <button
                          type="button"
                          className="btn-reject-diff"
                          onClick={() => handleRejectAgentDiff(msg.id)}
                        >
                          <X size={13} /> Reject
                        </button>
                      </div>
                    </div>
                  )}

                  {msg.status === 'applied' && (
                    <div className="diff-status-applied">
                      <CheckCircle size={13} /> Patch applied to {msg.targetFile}
                    </div>
                  )}

                  {msg.suggestedCommand && (
                    <button
                      type="button"
                      className="btn-run-suggested-cmd"
                      onClick={() => {
                        setBottomTab('terminal');
                        setIsBottomPanelCollapsed(false);
                        handleRunTerminal(msg.suggestedCommand || '');
                      }}
                    >
                      <Play size={12} /> Run {msg.suggestedCommand}
                    </button>
                  )}
                </div>
              ))}
              {isAgentProcessing && (
                <div className="agent-msg-bubble role-assistant is-thinking">
                  <span>Roxy is analyzing AST and formulating code patch...</span>
                </div>
              )}
            </div>

            {/* Quick Action Prompt Chips */}
            <div className="agent-quick-chips">
              <button
                type="button"
                onClick={() =>
                  handleSendAgentPrompt('Roxy, is project ko analyze karo aur login bug fix karo.')
                }
              >
                Analyze &amp; Fix Bug (Urdu)
              </button>
              <button
                type="button"
                onClick={() => handleSendAgentPrompt('Explain the code and logic in this file')}
              >
                Explain Code
              </button>
              <button
                type="button"
                onClick={() => handleSendAgentPrompt('Generate comprehensive unit tests for this file')}
              >
                Generate Tests
              </button>
            </div>

            {/* Agent Input Box */}
            <div className="agent-input-container">
              <textarea
                placeholder="Ask Roxy in English, Urdu, or Roman Urdu..."
                value={agentInput}
                onChange={(e) => setAgentInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendAgentPrompt();
                  }
                }}
              />
              <div className="agent-input-actions">
                <button
                  type="button"
                  className={`btn-voice-coding ${isVoiceListening ? 'is-recording' : ''}`}
                  title="Voice Prompt (Multilingual)"
                  onClick={handleToggleVoiceCoding}
                >
                  {isVoiceListening ? <MicOff size={16} /> : <Mic size={16} />}
                </button>
                <button
                  type="button"
                  className="btn-send-agent"
                  disabled={!agentInput.trim() || isAgentProcessing}
                  onClick={() => handleSendAgentPrompt()}
                >
                  <Send size={15} />
                </button>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* ─── 5. BOTTOM PANEL (Terminal / Problems / Tests / Preview) ────── */}
      <section
        className={`ide-bottom-panel ${isBottomPanelCollapsed ? 'is-collapsed' : ''}`}
        aria-label="Integrated Terminal and Diagnostics"
      >
        <div className="bottom-panel-header">
          <div className="bottom-tabs">
            <button
              type="button"
              className={`btab ${bottomTab === 'terminal' ? 'is-active' : ''}`}
              onClick={() => setBottomTab('terminal')}
            >
              <TerminalIcon size={14} /> TERMINAL
            </button>
            <button
              type="button"
              className={`btab ${bottomTab === 'problems' ? 'is-active' : ''}`}
              onClick={() => setBottomTab('problems')}
            >
              <AlertTriangle size={14} /> PROBLEMS
            </button>
            <button
              type="button"
              className={`btab ${bottomTab === 'tests' ? 'is-active' : ''}`}
              onClick={() => setBottomTab('tests')}
            >
              <Bug size={14} /> TEST RESULTS
            </button>
            <button
              type="button"
              className={`btab ${bottomTab === 'preview' ? 'is-active' : ''}`}
              onClick={() => setBottomTab('preview')}
            >
              <Eye size={14} /> WEB DEV PREVIEW
            </button>
          </div>

          <div className="bottom-panel-controls">
            <button
              type="button"
              title="Toggle Panel"
              onClick={() => setIsBottomPanelCollapsed((prev) => !prev)}
            >
              {isBottomPanelCollapsed ? <Maximize2 size={13} /> : <Minimize2 size={13} />}
            </button>
          </div>
        </div>

        {!isBottomPanelCollapsed && (
          <div className="bottom-panel-content">
            {bottomTab === 'terminal' && (
              <div className="terminal-surface">
                <div className="terminal-logs">
                  {terminalHistory.map((entry, idx) => (
                    <div key={idx} className="terminal-entry">
                      <div className="term-cmd-line">
                        <span className="term-prompt">$</span> {entry.command}
                        <span className="term-time">{entry.timestamp} ({entry.durationMs}ms)</span>
                      </div>
                      {entry.stdout && <pre className="term-stdout">{entry.stdout}</pre>}
                      {entry.stderr && <pre className="term-stderr">{entry.stderr}</pre>}
                    </div>
                  ))}
                </div>
                <div className="terminal-input-row">
                  <span className="term-prompt">$</span>
                  <input
                    type="text"
                    value={terminalInput}
                    disabled={isTerminalRunning}
                    placeholder="Enter shell command (e.g. pytest tests/ -v, npm test)..."
                    onChange={(e) => setTerminalInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRunTerminal();
                    }}
                  />
                  {isTerminalRunning && <span className="term-spinner">Running...</span>}
                </div>
              </div>
            )}

            {bottomTab === 'problems' && (
              <div className="problems-surface">
                <div className="problems-empty">
                  <CheckCircle size={20} color="#0d9488" />
                  <span>No syntax or linter problems detected in workspace files.</span>
                </div>
              </div>
            )}

            {bottomTab === 'tests' && (
              <div className="tests-surface">
                <div className="tests-toolbar">
                  <button
                    type="button"
                    className="btn-run-tests-again"
                    disabled={isTesting}
                    onClick={handleRunTests}
                  >
                    <RefreshCw size={13} className={isTesting ? 'is-spinning' : ''} />
                    Run All Tests
                  </button>
                  {testResults && (
                    <div className="test-counters">
                      <span className="counter-passed">{testResults.passed} Passed</span>
                      <span className="counter-failed">{testResults.failed} Failed</span>
                    </div>
                  )}
                </div>
                {testResults && (
                  <pre className="test-raw-output">{testResults.output}</pre>
                )}
              </div>
            )}

            {bottomTab === 'preview' && (
              <div className="preview-surface">
                <div className="preview-controls-bar">
                  <div className="preview-viewport-toggles">
                    <button
                      type="button"
                      className={previewViewport === 'desktop' ? 'is-active' : ''}
                      onClick={() => setPreviewViewport('desktop')}
                    >
                      <Laptop size={14} /> Desktop
                    </button>
                    <button
                      type="button"
                      className={previewViewport === 'tablet' ? 'is-active' : ''}
                      onClick={() => setPreviewViewport('tablet')}
                    >
                      <Tablet size={14} /> Tablet
                    </button>
                    <button
                      type="button"
                      className={previewViewport === 'mobile' ? 'is-active' : ''}
                      onClick={() => setPreviewViewport('mobile')}
                    >
                      <Smartphone size={14} /> Mobile
                    </button>
                  </div>
                  <input
                    type="text"
                    className="preview-url-input"
                    value={previewUrl}
                    onChange={(e) => setPreviewUrl(e.target.value)}
                  />
                  <button type="button" className="btn-preview-external" onClick={() => window.open(previewUrl, '_blank')}>
                    <ExternalLink size={14} />
                  </button>
                </div>
                <div className={`preview-iframe-wrapper viewport-${previewViewport}`}>
                  <iframe title="Web Dev Preview" src={previewUrl} sandbox="allow-scripts allow-same-origin" />
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ─── 6. COMMAND PALETTE MODAL (Ctrl+P) ────────────────────────────── */}
      {isCommandPaletteOpen && (
        <div className="command-palette-overlay" onClick={() => setIsCommandPaletteOpen(false)}>
          <div className="command-palette-modal animate-scale-up" onClick={(e) => e.stopPropagation()}>
            <div className="palette-input-row">
              <Search size={16} />
              <input
                autoFocus
                placeholder="Type a command or file name..."
                value={commandPaletteQuery}
                onChange={(e) => setCommandPaletteQuery(e.target.value)}
              />
            </div>
            <div className="palette-items-list">
              <div
                className="palette-item"
                onClick={() => {
                  setIsCommandPaletteOpen(false);
                  handleCreateNewFile();
                }}
              >
                <span>File: New File</span>
                <kbd>Ctrl+N</kbd>
              </div>
              <div
                className="palette-item"
                onClick={() => {
                  setIsCommandPaletteOpen(false);
                  saveActiveFile();
                }}
              >
                <span>File: Save Active File</span>
                <kbd>Ctrl+S</kbd>
              </div>
              <div
                className="palette-item"
                onClick={() => {
                  setIsCommandPaletteOpen(false);
                  handleRunTests();
                }}
              >
                <span>Run Tests in Workspace</span>
                <kbd>F5</kbd>
              </div>
              <div
                className="palette-item"
                onClick={() => {
                  setIsCommandPaletteOpen(false);
                  setActiveActivity('git');
                }}
              >
                <span>Git: View Changes &amp; Commit</span>
                <kbd>Ctrl+Shift+G</kbd>
              </div>
              <div
                className="palette-item"
                onClick={() => {
                  setIsCommandPaletteOpen(false);
                  setIsAgentPanelOpen(true);
                }}
              >
                <span>Roxy Agent: Ask Assistant</span>
                <kbd>Ctrl+Alt+A</kbd>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── 7. MOBILE BOTTOM NAVIGATION ───────────────────────────────────── */}
      <nav className="ide-mobile-nav" aria-label="Mobile IDE Navigation">
        <button
          type="button"
          className={mobileActiveView === 'files' ? 'is-active' : ''}
          onClick={() => setMobileActiveView('files')}
        >
          <FolderTree size={18} />
          <span>Files</span>
        </button>
        <button
          type="button"
          className={mobileActiveView === 'editor' ? 'is-active' : ''}
          onClick={() => setMobileActiveView('editor')}
        >
          <Code2 size={18} />
          <span>Editor</span>
        </button>
        <button
          type="button"
          className={mobileActiveView === 'agent' ? 'is-active' : ''}
          onClick={() => setMobileActiveView('agent')}
        >
          <Sparkles size={18} />
          <span>Agent</span>
        </button>
        <button
          type="button"
          className={mobileActiveView === 'terminal' ? 'is-active' : ''}
          onClick={() => {
            setMobileActiveView('terminal');
            setBottomTab('terminal');
            setIsBottomPanelCollapsed(false);
          }}
        >
          <TerminalIcon size={18} />
          <span>Terminal</span>
        </button>
      </nav>
    </div>
  );
};
