/* TaskWorkspacePanel — Developer Workspace for New Task & Coding Agent */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Folder,
  FolderOpen,
  FileCode,
  Play,
  Save,
  Copy,
  Trash2,
  Plus,
  Search,
  RotateCw,
  Eye,
  CheckCircle2,
  Code2,
  Terminal as TerminalIcon,
  GitCompare,
  X,
  Smartphone,
  Tablet,
  Monitor,
  Check,
  Undo2,
} from 'lucide-react';
import './TaskWorkspacePanel.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface WorkspaceFile {
  id: string;
  name: string;
  path: string;
  language: string;
  content: string;
  originalContent: string;
  isModified: boolean;
}

export interface TerminalExecution {
  id: string;
  command: string;
  language: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  timestamp: string;
  status: 'running' | 'success' | 'error' | 'stopped';
}

export interface TaskWorkspacePanelProps {
  isOpen: boolean;
  onClose: () => void;
  accessToken?: string | null;
  activeSessionId?: string | null;
  taskTitle?: string;
  onSendToChat?: (text: string) => void;
}

const DEFAULT_WORKSPACE_FILES: WorkspaceFile[] = [
  {
    id: 'file-1',
    name: 'App.tsx',
    path: 'src/App.tsx',
    language: 'typescript',
    content: `import React, { useState } from 'react';\nimport './App.css';\n\nexport function App() {\n  const [count, setCount] = useState(0);\n\n  return (\n    <div className="container">\n      <h1>ROXY Task Workspace</h1>\n      <p>Developer Project Active.</p>\n      <button onClick={() => setCount((c) => c + 1)}>\n        Clicks: {count}\n      </button>\n    </div>\n  );\n}`,
    originalContent: `import React, { useState } from 'react';\nimport './App.css';\n\nexport function App() {\n  const [count, setCount] = useState(0);\n\n  return (\n    <div className="container">\n      <h1>ROXY Task Workspace</h1>\n      <p>Developer Project Active.</p>\n      <button onClick={() => setCount((c) => c + 1)}>\n        Clicks: {count}\n      </button>\n    </div>\n  );\n}`,
    isModified: false,
  },
  {
    id: 'file-2',
    name: 'auth.ts',
    path: 'src/api/auth.ts',
    language: 'typescript',
    content: `// Authentication service & token validation\nexport interface AuthSession {\n  token: string;\n  userId: string;\n  expiresAt: number;\n}\n\nexport async function validateSession(token: string): Promise<boolean> {\n  if (!token) return false;\n  const parts = token.split('.');\n  return parts.length === 3;\n}\n\nexport function getAuthHeaders(session?: AuthSession | null): Record<string, string> {\n  return session ? { Authorization: \`Bearer \${session.token}\` } : {};\n}`,
    originalContent: `// Authentication service & token validation\nexport interface AuthSession {\n  token: string;\n  userId: string;\n  expiresAt: number;\n}\n\nexport async function validateSession(token: string): Promise<boolean> {\n  if (!token) return false;\n  const parts = token.split('.');\n  return parts.length === 3;\n}\n\nexport function getAuthHeaders(session?: AuthSession | null): Record<string, string> {\n  return session ? { Authorization: \`Bearer \${session.token}\` } : {};\n}`,
    isModified: false,
  },
  {
    id: 'file-3',
    name: 'routes.py',
    path: 'backend/routes.py',
    language: 'python',
    content: `from fastapi import APIRouter, HTTPException, Depends\nfrom typing import Dict, Any\n\nrouter = APIRouter(prefix="/v1", tags=["api"])\n\n@router.get("/health")\ndef health_check() -> Dict[str, str]:\n    """Health check endpoint."""\n    return {"status": "ok", "service": "roxy-agent"}\n\n@router.post("/process")\ndef process_task(data: Dict[str, Any]) -> Dict[str, Any]:\n    """Process verified developer task."""\n    if not data.get("task_id"):\n        raise HTTPException(status_code=400, detail="task_id required")\n    return {"result": "success", "processed": True}`,
    originalContent: `from fastapi import APIRouter, HTTPException, Depends\nfrom typing import Dict, Any\n\nrouter = APIRouter(prefix="/v1", tags=["api"])\n\n@router.get("/health")\ndef health_check() -> Dict[str, str]:\n    """Health check endpoint."""\n    return {"status": "ok", "service": "roxy-agent"}\n\n@router.post("/process")\ndef process_task(data: Dict[str, Any]) -> Dict[str, Any]:\n    """Process verified developer task."""\n    if not data.get("task_id"):\n        raise HTTPException(status_code=400, detail="task_id required")\n    return {"result": "success", "processed": True}`,
    isModified: false,
  },
  {
    id: 'file-4',
    name: 'package.json',
    path: 'package.json',
    language: 'json',
    content: `{\n  "name": "roxy-task-workspace",\n  "version": "1.0.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "tsc && vite build",\n    "test": "vitest"\n  },\n  "dependencies": {\n    "react": "^18.3.1",\n    "react-dom": "^18.3.1"\n  }\n}`,
    originalContent: `{\n  "name": "roxy-task-workspace",\n  "version": "1.0.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "tsc && vite build",\n    "test": "vitest"\n  },\n  "dependencies": {\n    "react": "^18.3.1",\n    "react-dom": "^18.3.1"\n  }\n}`,
    isModified: false,
  },
  {
    id: 'file-5',
    name: 'README.md',
    path: 'README.md',
    language: 'markdown',
    content: `# Roxy AI Task Workspace\n\nAutonomous Coding Agent developer environment.\n\n- Real sandboxed execution\n- Multi-file editor\n- Unified Diff Review\n- Real-time terminal output\n`,
    originalContent: `# Roxy AI Task Workspace\n\nAutonomous Coding Agent developer environment.\n\n- Real sandboxed execution\n- Multi-file editor\n- Unified Diff Review\n- Real-time terminal output\n`,
    isModified: false,
  },
];

export const TaskWorkspacePanel: React.FC<TaskWorkspacePanelProps> = ({
  isOpen,
  onClose,
  accessToken,
  activeSessionId,
  taskTitle = 'Developer Task',
  onSendToChat: _onSendToChat,
}) => {
  const [activeTab, setActiveTab] = useState<'files' | 'editor' | 'terminal' | 'diff' | 'preview'>('editor');

  // Files state with localStorage persistence per session
  const storageKey = `roxy_task_files_${activeSessionId || 'default'}`;
  const [files, setFiles] = useState<WorkspaceFile[]>(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      return saved ? JSON.parse(saved) : DEFAULT_WORKSPACE_FILES;
    } catch {
      return DEFAULT_WORKSPACE_FILES;
    }
  });

  const [activeFileId, setActiveFileId] = useState<string>('file-1');
  const [openTabs, setOpenTabs] = useState<string[]>(['file-1', 'file-2']);
  const [fileSearch, setFileSearch] = useState('');
  const [newFileName, setNewFileName] = useState('');
  const [showNewFileInput, setShowNewFileInput] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Editor state
  const activeFile = files.find((f) => f.id === activeFileId) || files[0];
  const [editorCode, setEditorCode] = useState(activeFile ? activeFile.content : '');
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [findQuery, setFindQuery] = useState('');
  const [showFindBar, setShowFindBar] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);

  // Terminal state
  const [terminalHistory, setTerminalHistory] = useState<TerminalExecution[]>([]);
  const [terminalCmd, setTerminalCmd] = useState('python main.py');
  const [isRunningCmd, setIsRunningCmd] = useState(false);
  const abortCtrlRef = useRef<AbortController | null>(null);
  const terminalBottomRef = useRef<HTMLDivElement>(null);

  // Preview state
  const [previewViewport, setPreviewViewport] = useState<'desktop' | 'tablet' | 'mobile'>('desktop');
  const [previewKey, setPreviewKey] = useState(0);

  // Sync editorCode whenever activeFile changes
  useEffect(() => {
    if (activeFile) {
      setEditorCode(activeFile.content);
    }
  }, [activeFileId]);

  // Persist files to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(files));
    } catch {
      // ignore
    }
  }, [files, storageKey]);

  // External Window Events listener (synchronization from Chat code blocks)
  useEffect(() => {
    const handleOpenEditor = (e: CustomEvent<{ code: string; language?: string; filename?: string }>) => {
      const { code, language = 'python', filename = 'script.py' } = e.detail;
      setFiles((prev) => {
        let existing = prev.find((f) => f.name === filename);
        if (!existing) {
          const newFile: WorkspaceFile = {
            id: `file-${Date.now()}`,
            name: filename,
            path: `src/${filename}`,
            language: language,
            content: code,
            originalContent: code,
            isModified: false,
          };
          setActiveFileId(newFile.id);
          setOpenTabs((tabs) => (tabs.includes(newFile.id) ? tabs : [...tabs, newFile.id]));
          return [...prev, newFile];
        } else {
          setActiveFileId(existing.id);
          setOpenTabs((tabs) => (tabs.includes(existing!.id) ? tabs : [...tabs, existing!.id]));
          return prev.map((f) =>
            f.id === existing!.id ? { ...f, content: code, isModified: f.originalContent !== code } : f
          );
        }
      });
      setActiveTab('editor');
    };

    const handleRunTerminal = (e: CustomEvent<{ code: string; language?: string }>) => {
      const { code, language = 'python' } = e.detail;
      setActiveTab('terminal');
      executeCodePayload(code, language);
    };

    const handleOpenDiff = (_e: CustomEvent<{ filename: string; diffContent?: string }>) => {
      setActiveTab('diff');
    };

    window.addEventListener('roxy-open-editor' as any, handleOpenEditor as any);
    window.addEventListener('roxy-run-terminal' as any, handleRunTerminal as any);
    window.addEventListener('roxy-open-diff' as any, handleOpenDiff as any);

    return () => {
      window.removeEventListener('roxy-open-editor' as any, handleOpenEditor as any);
      window.removeEventListener('roxy-run-terminal' as any, handleRunTerminal as any);
      window.removeEventListener('roxy-open-diff' as any, handleOpenDiff as any);
    };
  }, []);

  // Update file content
  const handleEditorChange = (newContent: string) => {
    setEditorCode(newContent);
    setFiles((prev) =>
      prev.map((f) =>
        f.id === activeFileId
          ? {
              ...f,
              content: newContent,
              isModified: f.originalContent !== newContent,
            }
          : f
      )
    );
  };

  // Open file in editor
  const handleSelectFile = (fileId: string) => {
    setActiveFileId(fileId);
    if (!openTabs.includes(fileId)) {
      setOpenTabs((prev) => [...prev, fileId]);
    }
    setActiveTab('editor');
  };

  // Close tab
  const handleCloseTab = (e: React.MouseEvent, fileId: string) => {
    e.stopPropagation();
    const nextTabs = openTabs.filter((id) => id !== fileId);
    setOpenTabs(nextTabs);
    if (activeFileId === fileId && nextTabs.length > 0) {
      setActiveFileId(nextTabs[nextTabs.length - 1]);
    }
  };

  // Create new file
  const handleCreateFile = () => {
    if (!newFileName.trim()) return;
    const name = newFileName.trim();
    const ext = name.split('.').pop()?.toLowerCase() || '';
    let lang = 'typescript';
    if (['py'].includes(ext)) lang = 'python';
    else if (['js', 'jsx'].includes(ext)) lang = 'javascript';
    else if (['html'].includes(ext)) lang = 'html';
    else if (['css'].includes(ext)) lang = 'css';
    else if (['json'].includes(ext)) lang = 'json';
    else if (['md'].includes(ext)) lang = 'markdown';
    else if (['sql'].includes(ext)) lang = 'sql';

    const newF: WorkspaceFile = {
      id: `file-${Date.now()}`,
      name,
      path: `src/${name}`,
      language: lang,
      content: `// ${name}\n`,
      originalContent: `// ${name}\n`,
      isModified: false,
    };
    setFiles((prev) => [...prev, newF]);
    setOpenTabs((prev) => [...prev, newF.id]);
    setActiveFileId(newF.id);
    setNewFileName('');
    setShowNewFileInput(false);
    setActiveTab('editor');
  };

  // Delete file
  const handleDeleteFile = (fileId: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== fileId));
    setOpenTabs((prev) => prev.filter((id) => id !== fileId));
    if (activeFileId === fileId) {
      const remaining = files.filter((f) => f.id !== fileId);
      if (remaining.length > 0) setActiveFileId(remaining[0].id);
    }
    setDeleteConfirmId(null);
  };

  // Save Snippet to Backend
  const handleSaveSnippet = async () => {
    if (!activeFile) return;
    setSaveStatus('Saving…');
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`;
      }
      const res = await fetch(`${API_BASE}/coding/snippets`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          title: activeFile.name,
          language: activeFile.language,
          code: activeFile.content,
          description: `Saved from task: ${taskTitle}`,
          tags: ['workspace', activeFile.language],
        }),
      });
      if (res.ok) {
        setSaveStatus('✓ Saved snippet');
        // Mark as clean
        setFiles((prev) =>
          prev.map((f) =>
            f.id === activeFileId ? { ...f, originalContent: f.content, isModified: false } : f
          )
        );
      } else {
        setSaveStatus('Save error');
      }
    } catch {
      setSaveStatus('Save error');
    }
    setTimeout(() => setSaveStatus(null), 2500);
  };

  // Revert changes
  const handleRevertFile = (fileId: string) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId ? { ...f, content: f.originalContent, isModified: false } : f
      )
    );
    if (activeFileId === fileId) {
      const target = files.find((f) => f.id === fileId);
      if (target) setEditorCode(target.originalContent);
    }
  };

  // Apply Diff
  const handleApplyDiff = (fileId: string) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId ? { ...f, originalContent: f.content, isModified: false } : f
      )
    );
  };

  // Real Subprocess Code Execution via Backend /api/v1/coding/execute
  const executeCodePayload = async (codeToRun: string, langToRun: string) => {
    setIsRunningCmd(true);
    const execId = `exec-${Date.now()}`;
    const startTime = Date.now();

    const newExec: TerminalExecution = {
      id: execId,
      command: `run ${langToRun}`,
      language: langToRun,
      stdout: '',
      stderr: '',
      exit_code: 0,
      duration_ms: 0,
      timestamp: new Date().toLocaleTimeString(),
      status: 'running',
    };

    setTerminalHistory((prev) => [...prev, newExec]);

    const abortController = new AbortController();
    abortCtrlRef.current = abortController;

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`;
      }

      const res = await fetch(`${API_BASE}/coding/execute`, {
        method: 'POST',
        headers,
        signal: abortController.signal,
        body: JSON.stringify({
          language: langToRun.toLowerCase().includes('py') ? 'python' : 'javascript',
          code: codeToRun,
          timeout_seconds: 10,
        }),
      });

      const elapsed = Date.now() - startTime;

      if (res.ok) {
        const data = await res.json();
        setTerminalHistory((prev) =>
          prev.map((item) =>
            item.id === execId
              ? {
                  ...item,
                  stdout: data.stdout || '(no output)',
                  stderr: data.stderr || '',
                  exit_code: data.exit_code,
                  duration_ms: data.execution_time_ms || elapsed,
                  status: data.exit_code === 0 ? 'success' : 'error',
                }
              : item
          )
        );
      } else {
        const errText = await res.text();
        setTerminalHistory((prev) =>
          prev.map((item) =>
            item.id === execId
              ? {
                  ...item,
                  stderr: `Execution error (${res.status}): ${errText}`,
                  exit_code: 1,
                  duration_ms: elapsed,
                  status: 'error',
                }
              : item
          )
        );
      }
    } catch (err: unknown) {
      const elapsed = Date.now() - startTime;
      if (err instanceof DOMException && err.name === 'AbortError') {
        setTerminalHistory((prev) =>
          prev.map((item) =>
            item.id === execId
              ? {
                  ...item,
                  stderr: 'Execution stopped by user.',
                  exit_code: 130,
                  duration_ms: elapsed,
                  status: 'stopped',
                }
              : item
          )
        );
      } else {
        setTerminalHistory((prev) =>
          prev.map((item) =>
            item.id === execId
              ? {
                  ...item,
                  stderr: err instanceof Error ? err.message : 'Execution failed.',
                  exit_code: 1,
                  duration_ms: elapsed,
                  status: 'error',
                }
              : item
          )
        );
      }
    } finally {
      setIsRunningCmd(false);
      abortCtrlRef.current = null;
      setTimeout(() => {
        terminalBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 50);
    }
  };

  const handleStopExecution = () => {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
    }
  };

  // Run command from terminal input
  const handleRunCustomCommand = (e: React.FormEvent) => {
    e.preventDefault();
    if (!terminalCmd.trim() || isRunningCmd) return;
    const cmd = terminalCmd.trim();

    // Determine target code based on active file or command
    if (cmd.startsWith('python') || cmd.startsWith('py')) {
      const pyFile = files.find((f) => f.language === 'python') || activeFile;
      executeCodePayload(pyFile ? pyFile.content : `print("Hello from ROXY Terminal")`, 'python');
    } else if (cmd.startsWith('node') || cmd.startsWith('npm')) {
      const jsFile = files.find((f) => f.language === 'javascript' || f.language === 'typescript') || activeFile;
      executeCodePayload(jsFile ? jsFile.content : `console.log("Hello from ROXY Node")`, 'javascript');
    } else {
      executeCodePayload(activeFile.content, activeFile.language);
    }
  };

  // Filtered files for search
  const filteredFiles = useMemo(() => {
    if (!fileSearch.trim()) return files;
    const q = fileSearch.toLowerCase();
    return files.filter(
      (f) => f.name.toLowerCase().includes(q) || f.path.toLowerCase().includes(q)
    );
  }, [files, fileSearch]);

  // Modified files count
  const modifiedFilesCount = files.filter((f) => f.isModified).length;

  if (!isOpen) return null;

  return (
    <aside className="task-workspace" aria-label="Task Developer Workspace">
      {/* Workspace Header */}
      <div className="task-workspace__header">
        <div className="task-workspace__title-wrap">
          <Code2 size={16} className="task-workspace__icon" />
          <span className="task-workspace__title">Coding Studio Workspace</span>
          <span className="task-workspace__branch-pill">main</span>
        </div>

        {/* Tab switchers */}
        <div className="task-workspace__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'files'}
            className={`task-workspace__tab ${activeTab === 'files' ? 'task-workspace__tab--active' : ''}`}
            onClick={() => setActiveTab('files')}
            title="Project File Explorer"
          >
            <Folder size={14} />
            <span>Files ({files.length})</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'editor'}
            className={`task-workspace__tab ${activeTab === 'editor' ? 'task-workspace__tab--active' : ''}`}
            onClick={() => setActiveTab('editor')}
            title="Code Editor"
          >
            <FileCode size={14} />
            <span>Editor</span>
            {activeFile?.isModified && <span className="task-workspace__dirty-dot" />}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'terminal'}
            className={`task-workspace__tab ${activeTab === 'terminal' ? 'task-workspace__tab--active' : ''}`}
            onClick={() => setActiveTab('terminal')}
            title="Terminal & Command Runner"
          >
            <TerminalIcon size={14} />
            <span>Terminal</span>
            {isRunningCmd && <span className="task-workspace__pulse-dot" />}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'diff'}
            className={`task-workspace__tab ${activeTab === 'diff' ? 'task-workspace__tab--active' : ''}`}
            onClick={() => setActiveTab('diff')}
            title="Review Unified Diff"
          >
            <GitCompare size={14} />
            <span>Diff {modifiedFilesCount > 0 && `(${modifiedFilesCount})`}</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'preview'}
            className={`task-workspace__tab ${activeTab === 'preview' ? 'task-workspace__tab--active' : ''}`}
            onClick={() => setActiveTab('preview')}
            title="Web Application Live Preview"
          >
            <Eye size={14} />
            <span>Preview</span>
          </button>
        </div>

        <button
          type="button"
          className="task-workspace__close-btn"
          onClick={onClose}
          aria-label="Close Developer Workspace"
          title="Close Workspace"
        >
          <X size={16} />
        </button>
      </div>

      {/* Main Workspace Body */}
      <div className="task-workspace__body">
        {/* ─── TAB 1: FILES ─── */}
        {activeTab === 'files' && (
          <div className="task-workspace__files-view">
            <div className="task-workspace__files-toolbar">
              <div className="task-workspace__search-box">
                <Search size={13} className="task-workspace__search-icon" />
                <input
                  type="text"
                  placeholder="Search project files…"
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  className="task-workspace__search-input"
                />
              </div>
              <button
                type="button"
                className="task-workspace__action-btn"
                onClick={() => setShowNewFileInput((v) => !v)}
                title="Create new file"
              >
                <Plus size={14} />
                <span>New</span>
              </button>
            </div>

            {showNewFileInput && (
              <div className="task-workspace__new-file-form">
                <input
                  type="text"
                  placeholder="e.g. index.ts, utils.py..."
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateFile()}
                  className="task-workspace__new-file-input"
                  autoFocus
                />
                <button
                  type="button"
                  className="task-workspace__btn-primary-sm"
                  onClick={handleCreateFile}
                >
                  Create
                </button>
                <button
                  type="button"
                  className="task-workspace__btn-secondary-sm"
                  onClick={() => setShowNewFileInput(false)}
                >
                  Cancel
                </button>
              </div>
            )}

            <div className="task-workspace__file-tree">
              <div className="task-workspace__tree-root">
                <FolderOpen size={14} className="task-workspace__folder-icon" />
                <span className="task-workspace__tree-root-label">roxy-project /</span>
              </div>
              {filteredFiles.map((file) => (
                <div
                  key={file.id}
                  className={`task-workspace__file-item ${file.id === activeFileId ? 'task-workspace__file-item--active' : ''}`}
                  onClick={() => handleSelectFile(file.id)}
                >
                  <FileCode size={14} className="task-workspace__file-icon" />
                  <span className="task-workspace__file-name">{file.name}</span>
                  <span className="task-workspace__file-path">{file.path}</span>
                  {file.isModified && <span className="task-workspace__dirty-badge">Modified</span>}

                  <button
                    type="button"
                    className="task-workspace__file-del-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteConfirmId(file.id);
                    }}
                    title="Delete file"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>

            {deleteConfirmId && (
              <div className="task-workspace__confirm-modal">
                <p>Are you sure you want to delete this file from workspace?</p>
                <div className="task-workspace__confirm-actions">
                  <button
                    type="button"
                    className="task-workspace__btn-danger-sm"
                    onClick={() => handleDeleteFile(deleteConfirmId)}
                  >
                    Confirm Delete
                  </button>
                  <button
                    type="button"
                    className="task-workspace__btn-secondary-sm"
                    onClick={() => setDeleteConfirmId(null)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── TAB 2: EDITOR ─── */}
        {activeTab === 'editor' && (
          <div className="task-workspace__editor-view">
            {/* Open Tab bar */}
            <div className="task-workspace__open-tabs">
              {openTabs.map((tid) => {
                const f = files.find((item) => item.id === tid);
                if (!f) return null;
                const isActive = tid === activeFileId;
                return (
                  <div
                    key={tid}
                    className={`task-workspace__editor-tab ${isActive ? 'task-workspace__editor-tab--active' : ''}`}
                    onClick={() => setActiveFileId(tid)}
                  >
                    <span className="task-workspace__tab-name">{f.name}</span>
                    {f.isModified && <span className="task-workspace__tab-dot" />}
                    <button
                      type="button"
                      className="task-workspace__tab-close"
                      onClick={(e) => handleCloseTab(e, tid)}
                      aria-label="Close tab"
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Editor Action Bar */}
            <div className="task-workspace__editor-bar">
              <div className="task-workspace__editor-bar-left">
                <span className="task-workspace__lang-badge">{activeFile?.language || 'text'}</span>
                <span className="task-workspace__file-loc">{activeFile?.path}</span>
                {saveStatus && <span className="task-workspace__save-status">{saveStatus}</span>}
              </div>

              <div className="task-workspace__editor-bar-right">
                <button
                  type="button"
                  className="task-workspace__tool-btn"
                  onClick={() => setShowFindBar((v) => !v)}
                  title="Find in code"
                >
                  <Search size={13} />
                  <span>Find</span>
                </button>
                <button
                  type="button"
                  className="task-workspace__tool-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(editorCode);
                    setCopiedCode(true);
                    setTimeout(() => setCopiedCode(false), 2000);
                  }}
                  title="Copy code"
                >
                  <Copy size={13} />
                  <span>{copiedCode ? 'Copied' : 'Copy'}</span>
                </button>
                <button
                  type="button"
                  className="task-workspace__tool-btn task-workspace__tool-btn--accent"
                  onClick={handleSaveSnippet}
                  title="Save file snippet to library"
                >
                  <Save size={13} />
                  <span>Save</span>
                </button>
                <button
                  type="button"
                  className="task-workspace__tool-btn task-workspace__tool-btn--primary"
                  onClick={() => {
                    setActiveTab('terminal');
                    executeCodePayload(editorCode, activeFile?.language || 'python');
                  }}
                  title="Run active file in terminal"
                >
                  <Play size={13} />
                  <span>Run</span>
                </button>
              </div>
            </div>

            {/* Find bar */}
            {showFindBar && (
              <div className="task-workspace__find-bar">
                <input
                  type="text"
                  placeholder="Find in code…"
                  value={findQuery}
                  onChange={(e) => setFindQuery(e.target.value)}
                  className="task-workspace__find-input"
                  autoFocus
                />
                <span className="task-workspace__find-count">
                  {findQuery
                    ? `${(editorCode.match(new RegExp(findQuery, 'gi')) || []).length} matches`
                    : ''}
                </span>
                <button
                  type="button"
                  className="task-workspace__find-close"
                  onClick={() => setShowFindBar(false)}
                >
                  ✕
                </button>
              </div>
            )}

            {/* Code Textarea with Line Numbers */}
            <div className="task-workspace__editor-pane">
              <div className="task-workspace__gutter" aria-hidden="true">
                {editorCode.split('\n').map((_, i) => (
                  <div key={i} className="task-workspace__gutter-num">
                    {i + 1}
                  </div>
                ))}
              </div>
              <textarea
                value={editorCode}
                onChange={(e) => handleEditorChange(e.target.value)}
                className="task-workspace__textarea"
                spellCheck={false}
                autoCapitalize="off"
                autoComplete="off"
                aria-label="Code editor"
              />
            </div>
          </div>
        )}

        {/* ─── TAB 3: TERMINAL ─── */}
        {activeTab === 'terminal' && (
          <div className="task-workspace__terminal-view">
            <div className="task-workspace__terminal-bar">
              <div className="task-workspace__term-title">
                <TerminalIcon size={14} />
                <span>Interactive Subprocess Console</span>
              </div>
              <div className="task-workspace__term-actions">
                {isRunningCmd ? (
                  <button
                    type="button"
                    className="task-workspace__btn-danger-sm"
                    onClick={handleStopExecution}
                  >
                    Stop Execution
                  </button>
                ) : (
                  <button
                    type="button"
                    className="task-workspace__btn-primary-sm"
                    onClick={() => executeCodePayload(activeFile.content, activeFile.language)}
                  >
                    <Play size={12} />
                    <span>Run {activeFile.name}</span>
                  </button>
                )}
                <button
                  type="button"
                  className="task-workspace__btn-secondary-sm"
                  onClick={() => setTerminalHistory([])}
                >
                  Clear
                </button>
              </div>
            </div>

            {/* Terminal Output Stream */}
            <div className="task-workspace__terminal-screen">
              <div className="task-workspace__term-welcome">
                ROXY Developer Sandbox v1.0 [Sandboxed Node.js &amp; Python Subprocess Engine]
                <br />
                Ready to execute code and test workflows.
              </div>

              {terminalHistory.map((item) => (
                <div key={item.id} className="task-workspace__term-entry">
                  <div className="task-workspace__term-entry-header">
                    <span className="task-workspace__term-prompt">$</span>
                    <span className="task-workspace__term-command">{item.command}</span>
                    <span className="task-workspace__term-meta">
                      {item.timestamp} · {item.duration_ms}ms · exit {item.exit_code}
                    </span>
                    <span
                      className={`task-workspace__term-status-tag task-workspace__term-status-tag--${item.status}`}
                    >
                      {item.status === 'running'
                        ? 'Running…'
                        : item.status === 'success'
                        ? 'Exit 0'
                        : item.status === 'stopped'
                        ? 'Stopped'
                        : 'Error'}
                    </span>
                  </div>

                  {item.stdout && (
                    <pre className="task-workspace__term-stdout">{item.stdout}</pre>
                  )}
                  {item.stderr && (
                    <pre className="task-workspace__term-stderr">{item.stderr}</pre>
                  )}
                </div>
              ))}

              {isRunningCmd && (
                <div className="task-workspace__term-running">
                  <span className="task-workspace__pulse-dot" />
                  <span>Executing in sandbox environment…</span>
                </div>
              )}
              <div ref={terminalBottomRef} />
            </div>

            {/* Command Line Input */}
            <form onSubmit={handleRunCustomCommand} className="task-workspace__term-form">
              <span className="task-workspace__term-input-prompt">$</span>
              <input
                type="text"
                placeholder="Command (e.g. python main.py, node test.js)..."
                value={terminalCmd}
                onChange={(e) => setTerminalCmd(e.target.value)}
                className="task-workspace__term-input"
                disabled={isRunningCmd}
              />
              <button
                type="submit"
                className="task-workspace__term-send-btn"
                disabled={isRunningCmd || !terminalCmd.trim()}
              >
                Send
              </button>
            </form>
          </div>
        )}

        {/* ─── TAB 4: DIFF ─── */}
        {activeTab === 'diff' && (
          <div className="task-workspace__diff-view">
            <div className="task-workspace__diff-toolbar">
              <span className="task-workspace__diff-file-title">
                Reviewing Diff: <strong>{activeFile.name}</strong>
              </span>
              <div className="task-workspace__diff-actions">
                <button
                  type="button"
                  className="task-workspace__btn-primary-sm"
                  onClick={() => handleApplyDiff(activeFile.id)}
                  title="Accept and apply verified code changes"
                >
                  <Check size={13} />
                  <span>Apply Changes</span>
                </button>
                <button
                  type="button"
                  className="task-workspace__btn-secondary-sm"
                  onClick={() => handleRevertFile(activeFile.id)}
                  title="Revert back to original code"
                >
                  <Undo2 size={13} />
                  <span>Revert</span>
                </button>
              </div>
            </div>

            <div className="task-workspace__diff-container">
              {activeFile.content === activeFile.originalContent ? (
                <div className="task-workspace__diff-empty">
                  <CheckCircle2 size={32} className="task-workspace__diff-check" />
                  <p>No uncommitted code modifications in {activeFile.name}.</p>
                  <span>Edit code in Editor to generate instant side-by-side verification diff.</span>
                </div>
              ) : (
                <div className="task-workspace__diff-lines">
                  {/* Unified Diff computation */}
                  {(() => {
                    const origLines = activeFile.originalContent.split('\n');
                    const currLines = activeFile.content.split('\n');
                    const maxLen = Math.max(origLines.length, currLines.length);
                    const rows = [];
                    for (let i = 0; i < maxLen; i++) {
                      const o = origLines[i];
                      const c = currLines[i];
                      if (o === c) {
                        rows.push(
                          <div key={i} className="task-workspace__diff-row">
                            <span className="task-workspace__diff-marker">&nbsp;</span>
                            <span className="task-workspace__diff-line">{c}</span>
                          </div>
                        );
                      } else {
                        if (o !== undefined) {
                          rows.push(
                            <div key={`rem-${i}`} className="task-workspace__diff-row task-workspace__diff-row--removed">
                              <span className="task-workspace__diff-marker">-</span>
                              <span className="task-workspace__diff-line">{o}</span>
                            </div>
                          );
                        }
                        if (c !== undefined) {
                          rows.push(
                            <div key={`add-${i}`} className="task-workspace__diff-row task-workspace__diff-row--added">
                              <span className="task-workspace__diff-marker">+</span>
                              <span className="task-workspace__diff-line">{c}</span>
                            </div>
                          );
                        }
                      }
                    }
                    return rows;
                  })()}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── TAB 5: PREVIEW ─── */}
        {activeTab === 'preview' && (
          <div className="task-workspace__preview-view">
            <div className="task-workspace__preview-bar">
              <div className="task-workspace__preview-sizes">
                <button
                  type="button"
                  className={`task-workspace__preview-btn ${previewViewport === 'desktop' ? 'task-workspace__preview-btn--active' : ''}`}
                  onClick={() => setPreviewViewport('desktop')}
                  title="Desktop View (100%)"
                >
                  <Monitor size={14} />
                  <span>Desktop</span>
                </button>
                <button
                  type="button"
                  className={`task-workspace__preview-btn ${previewViewport === 'tablet' ? 'task-workspace__preview-btn--active' : ''}`}
                  onClick={() => setPreviewViewport('tablet')}
                  title="Tablet View (768px)"
                >
                  <Tablet size={14} />
                  <span>Tablet</span>
                </button>
                <button
                  type="button"
                  className={`task-workspace__preview-btn ${previewViewport === 'mobile' ? 'task-workspace__preview-btn--active' : ''}`}
                  onClick={() => setPreviewViewport('mobile')}
                  title="Mobile View (375px)"
                >
                  <Smartphone size={14} />
                  <span>Mobile</span>
                </button>
              </div>

              <div className="task-workspace__preview-actions">
                <button
                  type="button"
                  className="task-workspace__tool-btn"
                  onClick={() => setPreviewKey((k) => k + 1)}
                  title="Refresh Preview"
                >
                  <RotateCw size={13} />
                  <span>Refresh</span>
                </button>
              </div>
            </div>

            <div className="task-workspace__preview-frame-wrap">
              <div className={`task-workspace__preview-frame-box task-workspace__preview-frame-box--${previewViewport}`}>
                <iframe
                  key={previewKey}
                  title="Application Output Preview"
                  sandbox="allow-scripts allow-modals"
                  srcDoc={`
                    <!DOCTYPE html>
                    <html>
                    <head>
                      <meta charset="utf-8">
                      <meta name="viewport" content="width=device-width, initial-scale=1">
                      <style>
                        body {
                          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                          padding: 2rem;
                          margin: 0;
                          color: #1e292b;
                          background: #fafcfb;
                        }
                        .container {
                          max-width: 600px;
                          margin: 0 auto;
                          background: #ffffff;
                          padding: 2rem;
                          border-radius: 12px;
                          box-shadow: 0 4px 12px rgba(0,0,0,0.06);
                          border: 1px solid #e2e8e6;
                        }
                        h1 { color: #0d9488; font-size: 1.5rem; margin-top: 0; }
                        button {
                          background: #0d9488;
                          color: white;
                          border: none;
                          padding: 0.6rem 1.2rem;
                          border-radius: 6px;
                          font-size: 0.9rem;
                          font-weight: 600;
                          cursor: pointer;
                        }
                        button:hover { background: #0f766e; }
                      </style>
                    </head>
                    <body>
                      <div class="container">
                        <h1>🚀 Application Output Preview</h1>
                        <p><strong>Active Project:</strong> ROXY Task Workspace</p>
                        <p><strong>File:</strong> ${activeFile.name}</p>
                        <hr style="border: 0; border-top: 1px solid #e2e8e6; margin: 1.5rem 0;" />
                        <button onclick="alert('ROXY interactive click event!')">Test Component Interaction</button>
                      </div>
                    </body>
                    </html>
                  `}
                  className="task-workspace__iframe"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
