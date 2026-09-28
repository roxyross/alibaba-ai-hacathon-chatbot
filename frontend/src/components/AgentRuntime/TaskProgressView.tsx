import React, { useEffect, useState, useCallback } from 'react';
import './TaskProgressView.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface TaskStepItem {
  id: string;
  step_number: number;
  description: string;
  tool_id: string | null;
  tool_input: Record<string, unknown>;
  tool_output?: unknown;
  status: 'pending' | 'running' | 'waiting_for_approval' | 'completed' | 'failed' | 'skipped';
  error?: string | null;
}

export interface TaskItem {
  id: string;
  title: string;
  objective: string;
  status: 'draft' | 'planning' | 'running' | 'waiting_for_input' | 'waiting_for_permission' | 'paused' | 'completed' | 'failed' | 'cancelled';
  plan: Record<string, unknown>[];
  deliverables: Record<string, unknown>[];
  steps: TaskStepItem[];
  error?: string | null;
}

interface TaskProgressViewProps {
  taskId: string;
  accessToken?: string | null;
  onTaskChange?: (task: TaskItem) => void;
}

export const TaskProgressView: React.FC<TaskProgressViewProps> = ({
  taskId,
  accessToken,
  onTaskChange,
}) => {
  const [task, setTask] = useState<TaskItem | null>(null);
  const [latestMilestone, setLatestMilestone] = useState<string>('Analyzing task...');
  const [loading, setLoading] = useState<boolean>(false);

  const fetchTask = useCallback(async () => {
    if (!accessToken || !taskId) return;
    try {
      const res = await fetch(`${API_BASE}/agents/tasks/${taskId}`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      if (res.ok) {
        const data: TaskItem = await res.json();
        setTask(data);
        if (data.status === 'completed') setLatestMilestone('Task completed successfully');
        else if (data.status === 'waiting_for_permission') setLatestMilestone('Awaiting approval in Action Center');
        else if (data.status === 'running') setLatestMilestone('Executing autonomous steps');
        onTaskChange?.(data);
      }
    } catch {
      // Graceful error handling
    }
  }, [accessToken, taskId, onTaskChange]);

  useEffect(() => {
    fetchTask();
  }, [fetchTask]);

  // Connect SSE progress stream
  useEffect(() => {
    if (!accessToken || !taskId) return;

    // Use polling or SSE endpoint
    const interval = setInterval(fetchTask, 3000);
    return () => clearInterval(interval);
  }, [accessToken, taskId, fetchTask]);

  const handleControl = async (action: 'pause' | 'run' | 'cancel' | 'retry') => {
    if (!accessToken || !taskId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/agents/tasks/${taskId}/${action}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      if (res.ok) {
        const updated: TaskItem = await res.json();
        setTask(updated);
        onTaskChange?.(updated);
      }
    } finally {
      setLoading(false);
    }
  };

  if (!task) {
    return (
      <div className="task-progress">
        <span style={{ color: '#94a3b8' }}>Loading autonomous task details...</span>
      </div>
    );
  }

  return (
    <div className="task-progress" role="region" aria-label="Task Progress Execution">
      <div className="task-progress__header">
        <div className="task-progress__title-wrap">
          <h3 className="task-progress__title">{task.title}</h3>
          <p className="task-progress__objective">{task.objective}</p>
          <span style={{ fontSize: '0.78rem', color: '#38bdf8', marginTop: 2 }}>
            ⚡ {latestMilestone}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
          <span className={`task-progress__status-badge badge--${task.status}`}>
            ● {task.status.replace(/_/g, ' ')}
          </span>
          <div className="task-progress__controls">
            {task.status === 'running' && (
              <button
                type="button"
                className="task-ctrl-btn"
                onClick={() => handleControl('pause')}
                disabled={loading}
              >
                Pause
              </button>
            )}
            {task.status === 'paused' && (
              <button
                type="button"
                className="task-ctrl-btn task-ctrl-btn--primary"
                onClick={() => handleControl('run')}
                disabled={loading}
              >
                Resume
              </button>
            )}
            {(task.status === 'failed' || task.status === 'cancelled') && (
              <button
                type="button"
                className="task-ctrl-btn task-ctrl-btn--primary"
                onClick={() => handleControl('retry')}
                disabled={loading}
              >
                Retry
              </button>
            )}
            {task.status !== 'completed' && task.status !== 'cancelled' && (
              <button
                type="button"
                className="task-ctrl-btn"
                onClick={() => handleControl('cancel')}
                disabled={loading}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="task-progress__milestones">
        {task.steps.map((step) => {
          let iconChar = '•';
          if (step.status === 'completed') iconChar = '✓';
          else if (step.status === 'running') iconChar = '⚡';
          else if (step.status === 'waiting_for_approval') iconChar = '⚠️';
          else if (step.status === 'failed') iconChar = '✕';

          return (
            <div
              key={step.id}
              className={`task-step-card task-step-card--${step.status}`}
            >
              <div className={`task-step-card__icon icon--${step.status}`}>
                {iconChar}
              </div>
              <div className="task-step-card__content">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="task-step-card__title">
                    Step {step.step_number}: {step.description}
                  </span>
                  {step.tool_id && (
                    <span className="task-step-card__tool">
                      {step.tool_id}
                    </span>
                  )}
                </div>

                {step.status === 'waiting_for_approval' && (
                  <span style={{ color: '#fbbf24', fontSize: '0.8rem' }}>
                    Requires approval: Pending in Action Center
                  </span>
                )}

                {step.tool_output != null && (
                  <div className="task-step-card__output">
                    <pre style={{ margin: 0 }}>
                      {typeof step.tool_output === 'string'
                        ? step.tool_output
                        : JSON.stringify(step.tool_output, null, 2)}
                    </pre>
                  </div>
                )}

                {step.error && (
                  <span style={{ color: '#f87171', fontSize: '0.8rem', marginTop: 4 }}>
                    Error: {step.error}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {task.deliverables && task.deliverables.length > 0 && (
        <div className="task-progress__deliverables">
          <h4 className="task-progress__deliverables-title">
            ✨ Verified Deliverables ({task.deliverables.length})
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {task.deliverables.map((item, idx) => (
              <div
                key={idx}
                style={{
                  background: 'rgba(15, 23, 42, 0.5)',
                  borderRadius: 6,
                  padding: 8,
                  fontSize: '0.82rem',
                }}
              >
                <strong>{String(item.title || `Deliverable #${idx + 1}`)}</strong>
                <pre style={{ margin: '4px 0 0 0', color: '#94a3b8' }}>
                  {JSON.stringify(item.data, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
