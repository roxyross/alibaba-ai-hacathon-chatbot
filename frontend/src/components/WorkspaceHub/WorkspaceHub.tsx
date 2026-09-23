import React, { useState, useEffect, useCallback } from 'react';
import './WorkspaceHub.css';

interface ProjectItem {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'in_progress' | 'archived' | 'completed';
  lastUpdated: string;
  tasksCount: number;
  completedCount: number;
}

interface TaskItem {
  id: string;
  project_id: string;
  title: string;
  description?: string;
  status: 'todo' | 'in_progress' | 'done' | 'blocked';
  priority?: string;
  assigned_agent?: string;
}

interface DocItem {
  id: string;
  project_id: string;
  document_id: string;
  title: string;
  file_type?: string;
}

interface WorkspaceHubProps {
  accessToken: string | null;
  onBack: () => void;
  onOpenProject?: (projectId: string) => void;
}

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const WorkspaceHub: React.FC<WorkspaceHubProps> = ({
  accessToken,
  onBack,
  onOpenProject,
}) => {
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showNewModal, setShowNewModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  // Project Detail Drawer / Modal
  const [activeProject, setActiveProject] = useState<ProjectItem | null>(null);
  const [projectTasks, setProjectTasks] = useState<TaskItem[]>([]);
  const [projectDocs, setProjectDocs] = useState<DocItem[]>([]);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newDocTitle, setNewDocTitle] = useState('');
  const [newDocId, setNewDocId] = useState('');

  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [_isLoading, setIsLoading] = useState(false);

  const fetchProjects = useCallback(async () => {
    if (!accessToken) {
      setProjects([]);
      return;
    }
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const queryParam = filterStatus !== 'all' ? `?status=${filterStatus}` : '';
      const res = await fetch(`${API_BASE}/projects${queryParam}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.projects)) {
          setProjects(
            data.projects.map((p: any) => ({
              id: p.id,
              name: p.name,
              description: p.description || '',
              status: p.status || 'active',
              lastUpdated: p.last_updated || 'Recently',
              tasksCount: p.tasks_count || 0,
              completedCount: p.completed_count || 0,
            }))
          );
        }
      } else {
        setErrorBanner('Failed to load workspace projects.');
      }
    } catch (err) {
      console.error('Failed to fetch projects', err);
      setErrorBanner('Could not load projects from server. Check network connection.');
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, filterStatus]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const openProjectDetails = async (project: ProjectItem) => {
    setActiveProject(project);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch(`${API_BASE}/projects/${project.id}`, { headers });
      if (res.ok) {
        const data = await res.json();
        const p = data.project;
        setProjectTasks(p.tasks || []);
        setProjectDocs(p.documents || []);
      } else {
        setErrorBanner('Failed to fetch full project details.');
      }
    } catch {
      setProjectTasks([]);
      setProjectDocs([]);
      setErrorBanner('Network error loading project details.');
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProject || !newTaskTitle.trim()) return;

    if (!accessToken) {
      setErrorBanner('Please sign in to add and persist tasks.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/projects/${activeProject.id}/tasks`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          title: newTaskTitle.trim(),
          status: 'todo',
          priority: 'medium',
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setProjectTasks((prev) => [...prev, data.task]);
        setNewTaskTitle('');
        fetchProjects();
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorBanner(errData.detail || 'Could not create task on server.');
      }
    } catch {
      setErrorBanner('Network error while creating task.');
    }
  };

  const handleToggleTaskStatus = async (task: TaskItem) => {
    if (!activeProject) return;
    const nextStatus = task.status === 'done' ? 'todo' : 'done';
    const previousTasks = [...projectTasks];

    setProjectTasks((prev) =>
      prev.map((t) => (t.id === task.id ? { ...t, status: nextStatus } : t))
    );

    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/projects/${activeProject.id}/tasks/${task.id}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ status: nextStatus }),
        });
        if (!res.ok) {
          setProjectTasks(previousTasks);
          setErrorBanner('Failed to update task status on server.');
        } else {
          fetchProjects();
        }
      }
    } catch {
      setProjectTasks(previousTasks);
      setErrorBanner('Network error while updating task status.');
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!activeProject) return;
    const previousTasks = [...projectTasks];
    setProjectTasks((prev) => prev.filter((t) => t.id !== taskId));

    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/projects/${activeProject.id}/tasks/${taskId}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!res.ok) {
          setProjectTasks(previousTasks);
          setErrorBanner('Failed to delete task on server.');
        } else {
          fetchProjects();
        }
      }
    } catch {
      setProjectTasks(previousTasks);
      setErrorBanner('Network error while deleting task.');
    }
  };

  const handleLinkDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProject || !newDocTitle.trim()) return;

    if (!accessToken) {
      setErrorBanner('Please sign in to link documents to this workspace project.');
      return;
    }

    const docId = newDocId.trim() || `doc_${newDocTitle.trim().toLowerCase().replace(/\s+/g, '_')}`;
    try {
      const res = await fetch(`${API_BASE}/projects/${activeProject.id}/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          document_id: docId,
          title: newDocTitle.trim(),
          file_type: 'document',
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setProjectDocs((prev) => [data.document, ...prev]);
        setNewDocTitle('');
        setNewDocId('');
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorBanner(errData.detail || 'Could not link document.');
      }
    } catch {
      setErrorBanner('Network error while linking document.');
    }
  };

  const handleUnlinkDocument = async (docLinkId: string) => {
    if (!activeProject) return;
    const previousDocs = [...projectDocs];
    setProjectDocs((prev) => prev.filter((d) => d.id !== docLinkId));

    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/projects/${activeProject.id}/documents/${docLinkId}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!res.ok) {
          setProjectDocs(previousDocs);
          setErrorBanner('Failed to unlink document on server.');
        }
      }
    } catch {
      setProjectDocs(previousDocs);
      setErrorBanner('Network error while unlinking document.');
    }
  };

  const filteredProjects = projects.filter((p) => {
    if (filterStatus === 'all') return true;
    return p.status === filterStatus;
  });

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    if (!accessToken) {
      setErrorBanner('Please sign in to create persistent workspace projects.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          name: newTitle.trim(),
          description: newDesc.trim() || 'Custom workspace project.',
          status: 'active',
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const p = data.project;
        const newProject: ProjectItem = {
          id: p.id,
          name: p.name,
          description: p.description,
          status: p.status || 'active',
          lastUpdated: p.last_updated || 'Just now',
          tasksCount: 0,
          completedCount: 0,
        };
        setProjects((prev) => [newProject, ...prev]);
        setNewTitle('');
        setNewDesc('');
        setShowNewModal(false);
        setNotification(`Created project "${p.name}".`);
        setTimeout(() => setNotification(null), 4000);
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorBanner(errData.detail || 'Could not create project.');
      }
    } catch {
      setErrorBanner('Network error creating workspace project.');
    }
  };

  const handleStatusChange = async (id: string, newStatus: ProjectItem['status']) => {
    const previousProjects = [...projects];
    setProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: newStatus, lastUpdated: 'Just now' } : p))
    );

    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/projects/${id}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ status: newStatus }),
        });
        if (!res.ok) {
          setProjects(previousProjects);
          setErrorBanner('Failed to update project status on server.');
        }
      }
    } catch {
      setProjects(previousProjects);
      setErrorBanner('Network error while updating project status.');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this project? All associated tasks will be removed.')) return;
    const previousProjects = [...projects];
    setProjects((prev) => prev.filter((p) => p.id !== id));
    if (activeProject && activeProject.id === id) {
      setActiveProject(null);
    }

    try {
      if (accessToken) {
        const res = await fetch(`${API_BASE}/projects/${id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!res.ok) {
          setProjects(previousProjects);
          setErrorBanner('Failed to delete project on server.');
        }
      }
    } catch {
      setProjects(previousProjects);
      setErrorBanner('Network error while deleting project.');
    }
  };

  return (
    <div className="workspace-hub">
      <header className="workspace-hub__header">
        <div className="workspace-hub__header-left">
          <button type="button" className="workspace-hub__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <span className="workspace-hub__badge">🗂️ Workspace Hub</span>
        </div>
        <button
          type="button"
          className="workspace-hub__new-btn"
          onClick={() => setShowNewModal(true)}
        >
          + New Project
        </button>
      </header>

      <div className="workspace-hub__body">
        <div className="workspace-hub__hero">
          <h1 className="workspace-hub__title">Projects & Workspace Hub</h1>
          <p className="workspace-hub__subtitle">
            Manage your autonomous multi-agent projects, active tasks, and team knowledge artifacts.
          </p>
        </div>

        {!accessToken && (
          <div className="workspace-hub__alert" role="status" style={{ background: '#f8fafc', border: '1px solid #cbd5e1', color: '#475569', padding: '0.85rem 1.25rem', borderRadius: '0.75rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
            <span>🔒</span>
            <span>You are currently in guest mode. Sign in to create persistent workspace projects, assign agent tasks, and link documents.</span>
          </div>
        )}

        {errorBanner && (
          <div className="workspace-hub__alert" role="alert" style={{ background: '#fef2f2', border: '1px solid #fca5a5', color: '#991b1b', padding: '0.85rem 1.25rem', borderRadius: '0.75rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
            <span>⚠️</span>
            <span>{errorBanner}</span>
            <button
              type="button"
              onClick={fetchProjects}
              style={{ marginLeft: 'auto', background: '#991b1b', color: '#fff', border: 'none', borderRadius: '4px', padding: '3px 10px', fontSize: '11px', cursor: 'pointer', fontWeight: 600 }}
            >
              Retry
            </button>
            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              style={{ background: 'transparent', border: 'none', color: '#991b1b', cursor: 'pointer', fontWeight: 'bold' }}
            >
              ✕
            </button>
          </div>
        )}

        {notification && (
          <div className="workspace-hub__alert" role="status" style={{ background: '#f0fdfa', border: '1px solid #99f6e4', color: '#0d9488', padding: '0.85rem 1.25rem', borderRadius: '0.75rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
            <span>✨</span>
            <span>{notification}</span>
          </div>
        )}

        {/* Filter Bar */}
        <div className="workspace-hub__filters">
          {['all', 'active', 'in_progress', 'completed', 'archived'].map((status) => (
            <button
              key={status}
              type="button"
              className={`filter-btn ${filterStatus === status ? 'active' : ''}`}
              onClick={() => setFilterStatus(status)}
            >
              {status === 'all' ? 'All Projects' : status.replace('_', ' ')}
            </button>
          ))}
        </div>

        {/* Projects List */}
        <div className="workspace-hub__grid">
          {filteredProjects.length === 0 ? (
            <div
              className="workspace-hub__empty"
              style={{
                gridColumn: '1 / -1',
                padding: '3.5rem 1.5rem',
                textAlign: 'center',
                background: 'var(--color-surface, #fff)',
                border: '1px dashed var(--color-border, #e2e8e6)',
                borderRadius: '0.85rem',
              }}
            >
              <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '0.6rem' }}>📁</span>
              <h3 style={{ margin: '0 0 0.4rem 0', fontWeight: 700, fontSize: '1.15rem' }}>
                No workspace projects yet
              </h3>
              <p
                style={{
                  color: 'var(--color-muted, #64748b)',
                  fontSize: '0.88rem',
                  maxWidth: '440px',
                  margin: '0 auto 1.2rem',
                }}
              >
                Create a workspace project to organize multi-turn tasks, documents, and agent workflows in one dedicated space.
              </p>
              <button
                type="button"
                className="workspace-hub__new-btn"
                onClick={() => setShowNewModal(true)}
              >
                + New Project
              </button>
            </div>
          ) : (
            filteredProjects.map((project) => (
              <div key={project.id} className="project-card">
                <div className="project-card__top">
                  <span className={`project-card__status project-card__status--${project.status}`}>
                    {project.status.replace('_', ' ')}
                  </span>
                  <span className="project-card__date">Updated {project.lastUpdated}</span>
                </div>

                <h3 className="project-card__name">{project.name}</h3>
                <p className="project-card__desc">{project.description}</p>

                {/* Progress bar */}
                <div className="project-card__progress">
                  <div className="project-card__progress-label">
                    <span>Tasks</span>
                    <span>
                      {project.completedCount} / {project.tasksCount}
                    </span>
                  </div>
                  <div className="project-card__bar-bg">
                    <div
                      className="project-card__bar-fill"
                      style={{
                        width: `${
                          project.tasksCount > 0
                            ? (project.completedCount / project.tasksCount) * 100
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                </div>

                {/* Quick Actions */}
                <div className="project-card__actions">
                  <button
                    type="button"
                    className="project-card__action-btn"
                    onClick={() => openProjectDetails(project)}
                  >
                    🚀 Open
                  </button>
                  <select
                    className="project-card__status-select"
                    value={project.status}
                    onChange={(e) =>
                      handleStatusChange(project.id, e.target.value as ProjectItem['status'])
                    }
                  >
                    <option value="active">Active</option>
                    <option value="in_progress">In Progress</option>
                    <option value="completed">Completed</option>
                    <option value="archived">Archived</option>
                  </select>
                  <button
                    type="button"
                    className="project-card__delete-btn"
                    onClick={() => handleDelete(project.id)}
                    title="Delete project"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Project Details Modal / Drawer */}
      {activeProject && (
        <div className="workspace-modal-overlay">
          <div className="workspace-modal" style={{ maxWidth: '640px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2 className="workspace-modal__title" style={{ margin: 0 }}>{activeProject.name}</h2>
                <p style={{ margin: '0.2rem 0 0', color: 'var(--color-muted, #64748b)', fontSize: '0.85rem' }}>
                  {activeProject.description}
                </p>
              </div>
              <button
                type="button"
                className="modal-cancel-btn"
                style={{ padding: '0.25rem 0.6rem' }}
                onClick={() => setActiveProject(null)}
              >
                ✕
              </button>
            </div>

            {/* Tasks Section */}
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>
                  Tasks ({projectTasks.filter((t) => t.status === 'done').length}/{projectTasks.length})
                </h3>
              </div>

              {/* Add Task Form */}
              <form onSubmit={handleCreateTask} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.8rem' }}>
                <input
                  type="text"
                  placeholder="Add a new milestone or action item..."
                  value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)}
                  style={{
                    flex: 1,
                    padding: '0.45rem 0.75rem',
                    borderRadius: '0.4rem',
                    border: '1px solid var(--color-border, #e2e8e6)',
                    fontSize: '0.85rem',
                  }}
                />
                <button type="submit" className="modal-submit-btn" style={{ padding: '0.45rem 0.8rem', fontSize: '0.82rem' }}>
                  + Add
                </button>
              </form>

              {/* Tasks List */}
              <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {projectTasks.length === 0 ? (
                  <p style={{ color: 'var(--color-muted, #64748b)', fontSize: '0.82rem', margin: '0.5rem 0' }}>
                    No tasks yet. Add one above!
                  </p>
                ) : (
                  projectTasks.map((task) => (
                    <div
                      key={task.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.4rem 0.6rem',
                        background: 'var(--color-input-bg, #f8faf9)',
                        borderRadius: '0.4rem',
                        border: '1px solid var(--color-border, #e2e8e6)',
                      }}
                    >
                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', flex: 1 }}>
                        <input
                          type="checkbox"
                          checked={task.status === 'done'}
                          onChange={() => handleToggleTaskStatus(task)}
                        />
                        <span style={{ textDecoration: task.status === 'done' ? 'line-through' : 'none', fontSize: '0.85rem' }}>
                          {task.title}
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => handleDeleteTask(task.id)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: '0.8rem' }}
                      >
                        ✕
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Linked Documents Section */}
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ margin: '0 0 0.6rem 0', fontSize: '0.95rem', fontWeight: 700 }}>
                Linked Documents ({projectDocs.length})
              </h3>
              <form onSubmit={handleLinkDocument} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.6rem' }}>
                <input
                  type="text"
                  placeholder="Document title or reference..."
                  value={newDocTitle}
                  onChange={(e) => setNewDocTitle(e.target.value)}
                  style={{
                    flex: 1,
                    padding: '0.45rem 0.75rem',
                    borderRadius: '0.4rem',
                    border: '1px solid var(--color-border, #e2e8e6)',
                    fontSize: '0.85rem',
                  }}
                />
                <button type="submit" className="modal-submit-btn" style={{ padding: '0.45rem 0.8rem', fontSize: '0.82rem' }}>
                  + Link
                </button>
              </form>
              <div style={{ maxHeight: '120px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {projectDocs.length === 0 ? (
                  <p style={{ color: 'var(--color-muted, #64748b)', fontSize: '0.82rem', margin: '0.3rem 0' }}>
                    No linked documents. Link files from Knowledge Vault to ground AI project memory.
                  </p>
                ) : (
                  projectDocs.map((doc) => (
                    <div
                      key={doc.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.35rem 0.6rem',
                        background: 'var(--color-input-bg, #f8faf9)',
                        borderRadius: '0.4rem',
                        border: '1px solid var(--color-border, #e2e8e6)',
                        fontSize: '0.82rem',
                      }}
                    >
                      <span>📄 {doc.title}</span>
                      <button
                        type="button"
                        onClick={() => handleUnlinkDocument(doc.id)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: '0.8rem' }}
                      >
                        ✕
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Modal Actions */}
            <div className="workspace-modal__actions" style={{ justifyContent: 'space-between' }}>
              <button
                type="button"
                className="modal-submit-btn"
                style={{ background: 'var(--color-accent, #0d9488)' }}
                onClick={() => {
                  onOpenProject?.(activeProject.id);
                  setActiveProject(null);
                }}
              >
                💬 Chat with Roxy about this Project
              </button>
              <button
                type="button"
                className="modal-cancel-btn"
                onClick={() => setActiveProject(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Project Modal */}
      {showNewModal && (
        <div className="workspace-modal-overlay">
          <div className="workspace-modal">
            <h2 className="workspace-modal__title">Create New Project</h2>
            <form onSubmit={handleCreate}>
              <div className="workspace-modal__field">
                <label>Project Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Q4 Growth & Autonomous Marketing"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                />
              </div>

              <div className="workspace-modal__field">
                <label>Description</label>
                <textarea
                  rows={3}
                  placeholder="What is this workspace project achieving?"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                />
              </div>

              <div className="workspace-modal__actions">
                <button
                  type="button"
                  className="modal-cancel-btn"
                  onClick={() => setShowNewModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="modal-submit-btn">
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
