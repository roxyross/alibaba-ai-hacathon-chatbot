import React, { useState, useRef, useEffect } from 'react';
import './ScheduledJobsView.css';

interface ScheduledJobItem {
  id: string;
  name: string;
  description: string;
  schedule: string;
  timezone: string;
  status: 'Active' | 'Pause';
  next_run?: string;
  last_status?: string;
}

interface JobExecutionItem {
  id: string;
  job_id: string;
  status: string;
  triggered_by: string;
  duration_ms: number;
  result_summary: string | null;
  error_message: string | null;
  created_at: string;
}

interface ScheduledJobsViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigateView?: (view: string) => void;
}

export const ScheduledJobsView: React.FC<ScheduledJobsViewProps> = ({
  accessToken,
  onBack,
  onNavigateView,
}) => {
  const [promptText, setPromptText] = useState('');
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [selectedModel, setSelectedModel] = useState('Google Gemini 2.0 Flash');
  const [isListening, setIsListening] = useState(false);
  const [selectedTimezone, setSelectedTimezone] = useState('Asia/Karachi (PKT, UTC+5)');
  const fileUploadRef = useRef<HTMLInputElement>(null);

  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'user' | 'assistant'; text: string }>>([
    {
      sender: 'assistant',
      text: 'Scheduled agent active. You can type or speak tasks like "Run daily portfolio recap at 9am" or "Monitor competitor pricing every Monday".',
    },
  ]);

  const [jobs, setJobs] = useState<ScheduledJobItem[]>([]);
  const [_isLoading, setIsLoading] = useState(false);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // History Drawer / Modal state
  const [historyModalJob, setHistoryModalJob] = useState<ScheduledJobItem | null>(null);
  const [executions, setExecutions] = useState<JobExecutionItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const fetchJobs = async () => {
    setIsLoading(true);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch('/api/v1/jobs', { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.jobs)) {
          setJobs(
            data.jobs.map((j: any) => ({
              id: j.id,
              name: j.name,
              description: j.description || '',
              schedule: j.schedule || 'Daily',
              timezone: j.timezone || 'UTC',
              status: j.status === 'Pause' ? 'Pause' : 'Active',
              next_run: j.next_run || '',
              last_status: j.last_status,
            }))
          );
        }
      }
    } catch {
      // Keep empty
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [accessToken]);

  // Voice input support
  const toggleSpeech = () => {
    const SpeechRecognition =
      (window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser.');
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setPromptText(transcript);
        }
      };

      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleSend = async () => {
    if (!promptText.trim()) return;
    const userPrompt = promptText.trim();
    setChatMessages((prev) => [...prev, { sender: 'user', text: userPrompt }]);
    setPromptText('');

    const jobName = userPrompt.length > 35 ? `${userPrompt.slice(0, 35)}...` : userPrompt;
    const jobDesc = `Automated scheduled action configured via prompt: "${userPrompt}". Model: ${selectedModel}`;

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch('/api/v1/jobs', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          name: jobName,
          description: jobDesc,
          schedule: 'Every day at 08:00 AM',
          timezone: selectedTimezone,
          prompt: userPrompt,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const created = data.job;
        const newJob: ScheduledJobItem = {
          id: created.id,
          name: created.name,
          description: created.description,
          schedule: created.schedule,
          timezone: created.timezone,
          status: created.status === 'Pause' ? 'Pause' : 'Active',
          next_run: created.next_run,
        };
        setJobs((prev) => [newJob, ...prev]);
        setChatMessages((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: `✅ Scheduled task created: **"${newJob.name}"** running on schedule (${selectedTimezone}). Added to your active jobs below.`,
          },
        ]);
        return;
      }
    } catch {
      // fallback local
    }

    const localJob: ScheduledJobItem = {
      id: `job-${Date.now()}`,
      name: jobName,
      description: jobDesc,
      schedule: 'Every day at 08:00 AM',
      timezone: selectedTimezone,
      status: 'Active',
    };
    setJobs((prev) => [localJob, ...prev]);
    setChatMessages((prev) => [
      ...prev,
      {
        sender: 'assistant',
        text: `✅ Scheduled task created: **"${localJob.name}"** running on schedule (${selectedTimezone}). Added to your active jobs below.`,
      },
    ]);
  };

  const toggleJobStatus = async (id: string) => {
    const job = jobs.find((j) => j.id === id);
    if (!job) return;
    const newStatus: 'Active' | 'Pause' = job.status === 'Active' ? 'Pause' : 'Active';
    setJobs((prev) =>
      prev.map((j) => (j.id === id ? { ...j, status: newStatus } : j))
    );

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch(`/api/v1/jobs/${id}/status`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.job?.next_run) {
          setJobs((prev) =>
            prev.map((j) => (j.id === id ? { ...j, next_run: data.job.next_run } : j))
          );
        }
      }
    } catch {
      // local state already toggled
    }
  };

  const handleRunNow = async (id: string, name: string) => {
    setRunningJobId(id);
    setActionNotice(null);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch(`/api/v1/jobs/${id}/run`, {
        method: 'POST',
        headers,
      });
      if (res.ok) {
        const data = await res.json();
        const duration = data.execution?.duration_ms ? ` (${data.execution.duration_ms}ms)` : '';
        setActionNotice({
          type: 'success',
          text: `Task "${name}" ran successfully${duration}! ${data.execution?.result_summary || ''}`,
        });
        if (data.job?.next_run) {
          setJobs((prev) =>
            prev.map((j) => (j.id === id ? { ...j, next_run: data.job.next_run } : j))
          );
        }
      } else {
        const err = await res.json().catch(() => ({}));
        setActionNotice({
          type: 'error',
          text: `Failed to run task: ${err.detail || 'Execution error'}`,
        });
      }
    } catch (err: any) {
      setActionNotice({
        type: 'error',
        text: `Execution failed: ${err.message || 'Network error'}`,
      });
    } finally {
      setRunningJobId(null);
      setTimeout(() => setActionNotice(null), 6000);
    }
  };

  const handleOpenHistory = async (job: ScheduledJobItem) => {
    setHistoryModalJob(job);
    setLoadingHistory(true);
    setExecutions([]);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      const res = await fetch(`/api/v1/jobs/${job.id}/history`, { headers });
      if (res.ok) {
        const data = await res.json();
        setExecutions(data.executions || []);
      }
    } catch {
      // ignore
    } finally {
      setLoadingHistory(false);
    }
  };

  const deleteJob = async (id: string) => {
    if (!confirm('Are you sure you want to delete this scheduled job?')) return;
    setJobs((prev) => prev.filter((j) => j.id !== id));

    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      await fetch(`/api/v1/jobs/${id}`, {
        method: 'DELETE',
        headers,
      });
    } catch {
      // local state already deleted
    }
  };

  return (
    <div className="sched-view">
      {/* Top Header */}
      <header className="sched-view__header">
        <div className="sched-view__header-left">
          <button type="button" className="sched-view__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <h1 className="sched-view__title">Scheduled Automation</h1>
        </div>
        <span className="sched-view__status-pill">Engine Active</span>
      </header>

      <div className="sched-view__body">
        {/* Description */}
        <p className="sched-view__desc">
          Ask Roxy-AI to schedule background tasks, set recurring reminders, or monitor APIs autonomously.
        </p>

        {/* Global Notice Toast */}
        {actionNotice && (
          <div className={`sched-notice sched-notice--${actionNotice.type}`}>
            <span>{actionNotice.type === 'success' ? '⚡' : '⚠️'}</span>
            <span className="sched-notice__text">{actionNotice.text}</span>
            <button
              type="button"
              className="sched-notice__close"
              onClick={() => setActionNotice(null)}
            >
              ×
            </button>
          </div>
        )}

        {/* Chat Messages area */}
        <div className="sched-view__chat-box">
          {chatMessages.map((m, idx) => (
            <div key={idx} className={`sched-bubble sched-bubble--${m.sender}`}>
              {m.text}
            </div>
          ))}
        </div>

        {/* Clean chat-style input bar */}
        <div className="sched-view__input-container">
          <div className="sched-view__input-bar">
            {/* Left: "+" button */}
            <div className="sched-view__plus-wrap">
              <button
                type="button"
                className="sched-view__plus-btn"
                onClick={() => setShowPlusMenu((v) => !v)}
                title="Tools & Actions"
              >
                +
              </button>

              {/* "+" popup menu */}
              {showPlusMenu && (
                <div className="sched-view__plus-menu">
                  <div className="plus-menu__header">Quick Actions & Tools</div>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      fileUploadRef.current?.click();
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>📎</span> Add files (UPLOAD)
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      fileUploadRef.current?.click();
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>📁</span> Add folder
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      onNavigateView?.('calculator');
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>🧮</span> Calculator (TOOL)
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      onNavigateView?.('calendar');
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>📅</span> Calendar & Schedule (EVENTS)
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      setPromptText('Write a Python script to monitor API health and alert me');
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>💻</span> Write or edit code
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      onNavigateView?.('knowledge_vault');
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>📚</span> Knowledge Vault
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      setPromptText('Search the web daily for: ');
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>🌐</span> Search the web
                  </button>
                  <button
                    type="button"
                    className="plus-menu__item"
                    onClick={() => {
                      onNavigateView?.('finance');
                      setShowPlusMenu(false);
                    }}
                  >
                    <span>💰</span> Check finances & balances
                  </button>

                  <div className="plus-menu__divider" />

                  {/* Model Picker */}
                  <div className="plus-menu__model-picker">
                    <label>Model Picker</label>
                    <select
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                    >
                      <option value="Google Gemini 2.0 Flash">Gemini 2.0 Flash</option>
                      <option value="Anthropic Claude 3.5 Sonnet">Claude 3.5 Sonnet</option>
                      <option value="OpenAI GPT-4o">GPT-4o</option>
                      <option value="DeepSeek R1">DeepSeek R1</option>
                      <option value="Grok 2">Grok 2</option>
                    </select>
                  </div>

                  {/* Timezone selector */}
                  <div className="plus-menu__model-picker">
                    <label>Timezone</label>
                    <select
                      value={selectedTimezone}
                      onChange={(e) => setSelectedTimezone(e.target.value)}
                    >
                      <option value="Asia/Karachi (PKT, UTC+5)">Asia/Karachi (UTC+5)</option>
                      <option value="UTC">UTC (Universal Time)</option>
                      <option value="America/New_York (EST, UTC-5)">America/New_York (UTC-5)</option>
                      <option value="Europe/London (BST, UTC+1)">Europe/London (UTC+1)</option>
                      <option value="Asia/Dubai (GST, UTC+4)">Asia/Dubai (UTC+4)</option>
                    </select>
                  </div>
                </div>
              )}
            </div>

            {/* Input Placeholder: "Schedule a task" */}
            <input
              type="text"
              className="sched-view__input"
              placeholder="Schedule an autonomous task (e.g. 'Daily recap at 8 AM')"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSend();
              }}
            />

            {/* Right: microphone icon + circular send button */}
            <button
              type="button"
              className={`sched-view__mic-btn ${isListening ? 'listening' : ''}`}
              onClick={toggleSpeech}
              title="Voice input"
              aria-label="Voice input"
            >
              🎤
            </button>

            <button
              type="button"
              className="sched-view__send-btn"
              onClick={handleSend}
              disabled={!promptText.trim()}
              aria-label="Send scheduled prompt"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
          <input type="file" ref={fileUploadRef} style={{ display: 'none' }} />
        </div>

        {/* Scheduled Jobs in horizontal rows */}
        <div className="sched-view__jobs-section">
          <h2 className="sched-view__section-title">Active & Configured Jobs</h2>

          {jobs.length === 0 ? (
            <div className="sched-view__empty-state">
              <div className="sched-view__empty-icon">⏱️</div>
              <h3 className="sched-view__empty-title">No scheduled jobs yet</h3>
              <p className="sched-view__empty-desc">
                Type or speak a prompt like "Run daily market briefing at 9am" or "Audit cloud expenses every Monday" to schedule an autonomous recurring task.
              </p>
            </div>
          ) : (
            <div className="sched-view__rows">
              {jobs.map((job) => (
                <div key={job.id} className="sched-job-row">
                  <div className="sched-job-row__left">
                    <div className="sched-job-row__title-wrap">
                      <h3 className="sched-job-row__name">{job.name}</h3>
                      <span className={`sched-job-badge sched-job-badge--${job.status.toLowerCase()}`}>
                        {job.status}
                      </span>
                    </div>
                    <p className="sched-job-row__desc">{job.description}</p>
                    <div className="sched-job-row__meta">
                      <span>🕒 Schedule: {job.schedule}</span>
                      <span>•</span>
                      <span>🌐 {job.timezone}</span>
                      {job.next_run && (
                        <>
                          <span>•</span>
                          <span className="sched-job-row__next-run">⏳ Next: {new Date(job.next_run).toLocaleString()}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Buttons: Run Now | History | Pause/Resume | Delete */}
                  <div className="sched-job-row__actions">
                    <button
                      type="button"
                      className="job-btn job-btn--run"
                      onClick={() => handleRunNow(job.id, job.name)}
                      disabled={runningJobId === job.id}
                      title="Trigger execution immediately"
                    >
                      {runningJobId === job.id ? '⏳ Running...' : '▶ Run Now'}
                    </button>
                    <button
                      type="button"
                      className="job-btn job-btn--history"
                      onClick={() => handleOpenHistory(job)}
                      title="View execution run logs"
                    >
                      ⏱ History
                    </button>
                    <button
                      type="button"
                      className={`job-btn ${job.status === 'Active' ? 'job-btn--active' : 'job-btn--pause'}`}
                      onClick={() => toggleJobStatus(job.id)}
                      title={job.status === 'Active' ? 'Click to Pause' : 'Click to Resume'}
                    >
                      {job.status === 'Active' ? 'Pause' : 'Resume'}
                    </button>
                    <button
                      type="button"
                      className="job-btn job-btn--delete"
                      onClick={() => deleteJob(job.id)}
                      title="Delete scheduled task"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Execution History Modal / Drawer */}
      {historyModalJob && (
        <div className="sched-modal-overlay" onClick={() => setHistoryModalJob(null)}>
          <div className="sched-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sched-modal__header">
              <div>
                <h3 className="sched-modal__title">Execution History</h3>
                <p className="sched-modal__subtitle">{historyModalJob.name}</p>
              </div>
              <button
                type="button"
                className="sched-modal__close"
                onClick={() => setHistoryModalJob(null)}
              >
                ×
              </button>
            </div>

            <div className="sched-modal__body">
              {loadingHistory ? (
                <div className="sched-modal__loading">
                  <span className="sched-spinner" />
                  <p>Loading execution history...</p>
                </div>
              ) : executions.length === 0 ? (
                <div className="sched-modal__empty">
                  <p>No execution records found for this job yet.</p>
                  <p className="sched-modal__hint">Click "Run Now" to trigger a manual run and generate execution logs.</p>
                </div>
              ) : (
                <div className="sched-modal__list">
                  {executions.map((item) => (
                    <div key={item.id} className="sched-history-item">
                      <div className="sched-history-item__header">
                        <span className={`sched-history-badge sched-history-badge--${item.status}`}>
                          {item.status.toUpperCase()}
                        </span>
                        <span className="sched-history-trigger">
                          Triggered by: <strong>{item.triggered_by}</strong>
                        </span>
                        <span className="sched-history-duration">
                          {item.duration_ms}ms
                        </span>
                        <span className="sched-history-time">
                          {new Date(item.created_at).toLocaleString()}
                        </span>
                      </div>
                      <div className="sched-history-item__content">
                        {item.result_summary && (
                          <div className="sched-history-result">
                            <strong>Result:</strong> {item.result_summary}
                          </div>
                        )}
                        {item.error_message && (
                          <div className="sched-history-error">
                            <strong>Error:</strong> {item.error_message}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="sched-modal__footer">
              <button
                type="button"
                className="sched-modal__btn-secondary"
                onClick={() => setHistoryModalJob(null)}
              >
                Close
              </button>
              <button
                type="button"
                className="job-btn job-btn--run"
                disabled={runningJobId === historyModalJob.id}
                onClick={async () => {
                  await handleRunNow(historyModalJob.id, historyModalJob.name);
                  await handleOpenHistory(historyModalJob);
                }}
              >
                {runningJobId === historyModalJob.id ? 'Running...' : '▶ Run Now Again'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
