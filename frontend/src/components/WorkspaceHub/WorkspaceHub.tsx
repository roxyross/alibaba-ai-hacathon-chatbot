import React, { useState } from 'react';
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

interface WorkspaceHubProps {
  accessToken: string | null;
  onBack: () => void;
  onOpenProject?: (projectId: string) => void;
}

export const WorkspaceHub: React.FC<WorkspaceHubProps> = ({
  accessToken: _accessToken,
  onBack,
  onOpenProject,
}) => {
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showNewModal, setShowNewModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');

  const [projects, setProjects] = useState<ProjectItem[]>([
    {
      id: 'proj-1',
      name: 'Personal AI Assistant Orchestration',
      description: 'Multi-agent runtime for automated schedule management, finance tracking, and document indexing.',
      status: 'active',
      lastUpdated: 'Sep 15, 2026',
      tasksCount: 14,
      completedCount: 11,
    },
    {
      id: 'proj-2',
      name: 'Q3 Financial Modeling & Expense Automation',
      description: 'Plaid and Raast integration pipelines with automated anomaly alerts and budget triggers.',
      status: 'in_progress',
      lastUpdated: 'Sep 14, 2026',
      tasksCount: 8,
      completedCount: 5,
    },
    {
      id: 'proj-3',
      name: 'Enterprise Document Vector Vault',
      description: 'OCR, chunking, and semantic vector embeddings for technical documentation and whitepapers.',
      status: 'completed',
      lastUpdated: 'Sep 12, 2026',
      tasksCount: 22,
      completedCount: 22,
    },
    {
      id: 'proj-4',
      name: 'Autonomous Matter Smart-Home Bridge',
      description: 'Local IoT bridge orchestrating smart-home devices through voice commands and scheduled rules.',
      status: 'archived',
      lastUpdated: 'Aug 29, 2026',
      tasksCount: 6,
      completedCount: 6,
    },
  ]);

  const filteredProjects = projects.filter((p) => {
    if (filterStatus === 'all') return true;
    return p.status === filterStatus;
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    const newProject: ProjectItem = {
      id: `proj-${Date.now()}`,
      name: newTitle.trim(),
      description: newDesc.trim() || 'Custom workspace project.',
      status: 'active',
      lastUpdated: 'Just now',
      tasksCount: 0,
      completedCount: 0,
    };

    setProjects((prev) => [newProject, ...prev]);
    setNewTitle('');
    setNewDesc('');
    setShowNewModal(false);
  };

  const handleStatusChange = (id: string, newStatus: ProjectItem['status']) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: newStatus, lastUpdated: 'Just now' } : p))
    );
  };

  const handleDelete = (id: string) => {
    if (confirm('Are you sure you want to delete this project?')) {
      setProjects((prev) => prev.filter((p) => p.id !== id));
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
            Manage your autonomous multi-agent projects, active jobs, and team artifacts.
          </p>
        </div>

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
          {filteredProjects.map((project) => (
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
                  onClick={() => onOpenProject?.(project.id)}
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
          ))}
        </div>
      </div>

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
                  placeholder="Brief summary of goals and deliverables..."
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
