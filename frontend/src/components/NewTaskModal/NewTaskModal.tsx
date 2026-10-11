import React, { useState } from 'react';
import {
  Sparkles,
  Zap,
  Shield,
  X,
  Code,
  Globe,
  Monitor,
} from 'lucide-react';
import type { DeviceInfo } from '../DeviceHub';
import './NewTaskModal.css';

export interface NewTaskConfig {
  title: string;
  category: string;
  mode: 'autonomous' | 'guided';
  targetDevice?: string;
  targetApp?: string;
  initialPrompt: string;
}

export interface NewTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  devices: DeviceInfo[];
  onSubmitTask: (task: NewTaskConfig) => void;
}

export const NewTaskModal: React.FC<NewTaskModalProps> = ({
  isOpen,
  onClose,
  devices,
  onSubmitTask,
}) => {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('development');
  const [mode, setMode] = useState<'autonomous' | 'guided'>('autonomous');
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>(
    devices.find((d) => d.is_current_host)?.id || devices[0]?.id || ''
  );
  const [targetApp, setTargetApp] = useState('');
  const [initialPrompt, setInitialPrompt] = useState('');

  if (!isOpen) return null;

  const quickTemplates = [
    {
      title: 'Full-Stack Web App Development',
      category: 'development',
      app: 'Visual Studio Code',
      prompt: 'Scaffold a modern React + TypeScript dashboard with Vite, configure components and tests, and run dev server.',
      icon: <Code size={14} />,
    },
    {
      title: 'Cross-Device Security & Permission Audit',
      category: 'security',
      app: 'ROXY Audit Studio',
      prompt: 'Inspect target-scoped permissions across all registered devices, flag high-risk scopes, and generate security summary.',
      icon: <Shield size={14} />,
    },
    {
      title: 'Web Scraping & Competitive Intelligence',
      category: 'research',
      app: 'Browser Studio',
      prompt: 'Navigate to target technical documentation, extract key API specs, and summarize findings into Knowledge Vault.',
      icon: <Globe size={14} />,
    },
    {
      title: 'Host Process Automation & Health Check',
      category: 'system',
      app: 'Host Machine',
      prompt: 'Scan running processes on primary workstation, analyze memory usage, and report background anomalies.',
      icon: <Monitor size={14} />,
    },
  ];

  const handleApplyTemplate = (tpl: (typeof quickTemplates)[0]) => {
    setTitle(tpl.title);
    setCategory(tpl.category);
    setTargetApp(tpl.app);
    setInitialPrompt(tpl.prompt);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() && !initialPrompt.trim()) return;

    onSubmitTask({
      title: title.trim() || initialPrompt.slice(0, 40) + '...',
      category,
      mode,
      targetDevice: selectedDeviceId,
      targetApp: targetApp.trim() || undefined,
      initialPrompt: initialPrompt.trim() || title.trim(),
    });
    onClose();
  };

  return (
    <div className="new-task-modal__backdrop" onClick={onClose}>
      <div
        className="new-task-modal__window"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="new-task-title"
      >
        {/* Header */}
        <div className="new-task-modal__header">
          <div className="new-task-modal__title-wrap">
            <div className="new-task-modal__icon-badge">
              <Zap size={20} />
            </div>
            <div>
              <h2 id="new-task-title">Launch New ROXY Task</h2>
              <p className="new-task-modal__subtitle">
                Define an objective for autonomous execution, multi-agent planning, and workspace coordination.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="new-task-modal__close-btn"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Quick Templates Ribbon */}
        <div className="new-task-modal__templates-section">
          <span className="new-task-modal__section-label">Quick Task Templates:</span>
          <div className="new-task-modal__templates-grid">
            {quickTemplates.map((tpl) => (
              <button
                key={tpl.title}
                type="button"
                className="new-task-modal__template-chip"
                onClick={() => handleApplyTemplate(tpl)}
              >
                {tpl.icon}
                <span>{tpl.title}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="new-task-modal__form">
          <div className="new-task-modal__form-group">
            <label htmlFor="task-title">Task Title / Goal *</label>
            <input
              id="task-title"
              type="text"
              required
              placeholder="e.g. Build and verify payment reconciliation report"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="new-task-modal__input"
            />
          </div>

          <div className="new-task-modal__form-row">
            <div className="new-task-modal__form-group">
              <label htmlFor="task-category">Category</label>
              <select
                id="task-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="new-task-modal__select"
              >
                <option value="development">Software Engineering</option>
                <option value="research">Deep Research & Insights</option>
                <option value="system">Host & System Automation</option>
                <option value="security">Security & Permissions Audit</option>
                <option value="browser">Web & Browser Navigation</option>
              </select>
            </div>

            <div className="new-task-modal__form-group">
              <label htmlFor="task-device">Target Device</label>
              <select
                id="task-device"
                value={selectedDeviceId}
                onChange={(e) => setSelectedDeviceId(e.target.value)}
                className="new-task-modal__select"
              >
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.device_name} ({d.os_platform.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="new-task-modal__form-group">
            <label htmlFor="task-prompt">Detailed Instructions & Constraints</label>
            <textarea
              id="task-prompt"
              rows={3}
              placeholder="Provide specific guidelines, files to inspect, or acceptance criteria..."
              value={initialPrompt}
              onChange={(e) => setInitialPrompt(e.target.value)}
              className="new-task-modal__textarea"
            />
          </div>

          {/* Execution Mode Selector */}
          <div className="new-task-modal__mode-section">
            <span className="new-task-modal__section-label">Execution Strategy:</span>
            <div className="new-task-modal__mode-cards">
              <div
                className={`new-task-modal__mode-card ${
                  mode === 'autonomous' ? 'new-task-modal__mode-card--active' : ''
                }`}
                onClick={() => setMode('autonomous')}
              >
                <div className="new-task-modal__mode-header">
                  <Sparkles size={16} className="new-task-modal__mode-icon" />
                  <span className="new-task-modal__mode-name">Autonomous Operator</span>
                </div>
                <p className="new-task-modal__mode-desc">
                  ROXY self-plans, inspects environment, attempts actions, and self-corrects via
                  multi-tier fallbacks without pausing for low-risk approvals.
                </p>
              </div>

              <div
                className={`new-task-modal__mode-card ${
                  mode === 'guided' ? 'new-task-modal__mode-card--active' : ''
                }`}
                onClick={() => setMode('guided')}
              >
                <div className="new-task-modal__mode-header">
                  <Shield size={16} className="new-task-modal__mode-icon" />
                  <span className="new-task-modal__mode-name">Supervised / Guided</span>
                </div>
                <p className="new-task-modal__mode-desc">
                  Requires explicit user confirmation before executing file writes, process terminations,
                  or external webhooks.
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="new-task-modal__actions">
            <button
              type="button"
              className="new-task-modal__btn new-task-modal__btn--secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="new-task-modal__btn new-task-modal__btn--primary"
            >
              <Zap size={15} />
              <span>Launch Autonomous Task</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default NewTaskModal;
