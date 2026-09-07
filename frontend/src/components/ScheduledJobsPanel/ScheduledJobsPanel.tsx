// ScheduledJobsPanel — list, create, cancel, pause, resume scheduled jobs
// Uses GET/POST /api/v1/skills/schedule_job

import React, { useEffect, useState, useCallback } from 'react';
import './ScheduledJobsPanel.css';

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

interface JobAction {
  agent_slug: string;
  skill_slug: string | null;
  inputs: Record<string, unknown>;
}

interface JobEntry {
  job_id: string;
  name: string;
  schedule: string;
  timezone: string;
  action: JobAction;
  confirm_on_fire: boolean;
  status: string;
  created_at: string;
  next_fire_at: string | null;
  tag: string | null;
}

interface ScheduleJobResponse {
  op: string;
  success: boolean;
  job_id?: string;
  jobs?: JobEntry[];
  message?: string;
  error?: string;
}

async function fetchJSON<T>(url: string, accessToken: string | null | undefined, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

const AGENT_OPTIONS = ['research', 'files', 'coding', 'planner', 'browser', 'study', 'voice', 'automation', 'web_search'];
const SKILL_OPTIONS = [
  'web_search', 'document_rag_query', 'store_memory', 'retrieve_memory',
  'email_draft', 'browser_navigate', 'flashcard_generate', 'quiz_generate',
  'calendar_read', 'calculator',
];

// ─── Create job form ──────────────────────────────────────────────

interface CreateJobFormProps {
  accessToken: string | null;
  onCreated: () => void;
}

const CreateJobForm: React.FC<CreateJobFormProps> = ({ accessToken, onCreated }) => {
  const [name, setName] = useState('');
  const [schedule, setSchedule] = useState('');
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [agentSlug, setAgentSlug] = useState('research');
  const [skillSlug, setSkillSlug] = useState('web_search');
  const [message, setMessage] = useState('');
  const [confirmOnFire, setConfirmOnFire] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSensitive = ['email_draft', 'browser_fill_form', 'bank_connect'].includes(skillSlug);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !schedule.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await fetchJSON<ScheduleJobResponse>(
        `${API_BASE}/skills/schedule_job`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({
            op: 'create',
            name: name.trim(),
            schedule: schedule.trim(),
            timezone,
            action: {
              agent_slug: agentSlug,
              skill_slug: skillSlug || null,
              inputs: message.trim() ? { message: message.trim() } : {},
            },
            confirm_on_fire: isSensitive ? true : confirmOnFire,
          }),
        }
      );
      if (result.success) {
        setName('');
        setSchedule('');
        setMessage('');
        onCreated();
      } else {
        setError(result.error ?? 'Failed to create job');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="sjp-create-form" onSubmit={handleSubmit}>
      <h3 className="sjp-create-form__title">Create Scheduled Job</h3>

      <div className="sjp-create-form__row">
        <label className="sjp-create-form__label">
          Job name *
          <input
            type="text"
            className="sjp-create-form__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Morning briefing"
            required
            maxLength={100}
          />
        </label>
        <label className="sjp-create-form__label">
          Timezone *
          <input
            type="text"
            className="sjp-create-form__input"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="America/New_York"
            required
          />
        </label>
      </div>

      <label className="sjp-create-form__label">
        Schedule (cron or ISO datetime) *
        <input
          type="text"
          className="sjp-create-form__input"
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
          placeholder="0 8 * * 1-5  (weekdays at 8am)"
          required
        />
        <span className="sjp-create-form__hint">
          Cron: minute hour day month weekday &nbsp;|&nbsp; ISO: 2026-09-10T09:00:00
        </span>
      </label>

      <div className="sjp-create-form__row">
        <label className="sjp-create-form__label">
          Agent *
          <select
            className="sjp-create-form__select"
            value={agentSlug}
            onChange={(e) => setAgentSlug(e.target.value)}
          >
            {AGENT_OPTIONS.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
        </label>
        <label className="sjp-create-form__label">
          Skill
          <select
            className="sjp-create-form__select"
            value={skillSlug}
            onChange={(e) => setSkillSlug(e.target.value)}
          >
            <option value="">None (chat only)</option>
            {SKILL_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="sjp-create-form__label">
        Message / prompt
        <textarea
          className="sjp-create-form__input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="What should the job do each time it fires?"
          rows={2}
          maxLength={500}
        />
      </label>

      {!isSensitive && (
        <label className="sjp-create-form__checkbox">
          <input
            type="checkbox"
            checked={confirmOnFire}
            onChange={(e) => setConfirmOnFire(e.target.checked)}
          />
          Confirm before each fire (for sensitive actions)
        </label>
      )}

      {isSensitive && (
        <p className="sjp-create-form__sensitive-note">
          ⚠️ Sensitive skill — confirm_on_fire will be enabled automatically.
        </p>
      )}

      {error && <p className="sjp-create-form__error">{error}</p>}

      <button
        type="submit"
        className="sjp-create-form__submit"
        disabled={submitting || !name.trim() || !schedule.trim()}
      >
        {submitting ? 'Creating…' : '+ Create Job'}
      </button>
    </form>
  );
};

// ─── Job list item ─────────────────────────────────────────────────

interface JobItemProps {
  job: JobEntry;
  accessToken: string | null;
  onUpdated: () => void;
}

const JobItem: React.FC<JobItemProps> = ({ job, accessToken, onUpdated }) => {
  const [loading, setLoading] = useState(false);

  const op = async (op: string) => {
    setLoading(true);
    try {
      await fetchJSON<ScheduleJobResponse>(
        `${API_BASE}/skills/schedule_job`,
        accessToken,
        { method: 'POST', body: JSON.stringify({ op, job_id: job.job_id }) }
      );
      onUpdated();
    } catch { /* noop */ }
    finally { setLoading(false); }
  };

  const statusClass = job.status === 'active' ? 'job-item--active' : 'job-item--paused';

  return (
    <div className={`job-item ${statusClass}`}>
      <div className="job-item__header">
        <span className="job-item__name">{job.name}</span>
        <span className="job-item__status">{job.status}</span>
      </div>
      <p className="job-item__schedule">⏰ {job.schedule} ({job.timezone})</p>
      <p className="job-item__action">
        🤖 {job.action.agent_slug}
        {job.action.skill_slug && <> → {job.action.skill_slug}</>}
      </p>
      <div className="job-item__footer">
        <span className="job-item__next">
          Next: {fmtDate(job.next_fire_at)}
        </span>
        <div className="job-item__actions">
          {job.status === 'active' ? (
            <button className="job-item__btn" onClick={() => op('pause')} disabled={loading}>
              ⏸ Pause
            </button>
          ) : (
            <button className="job-item__btn" onClick={() => op('resume')} disabled={loading}>
              ▶ Resume
            </button>
          )}
          <button className="job-item__btn job-item__btn--danger" onClick={() => op('cancel')} disabled={loading}>
            ✕ Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Main ScheduledJobsPanel ───────────────────────────────────────

interface ScheduledJobsPanelProps {
  accessToken?: string | null;
}

export const ScheduledJobsPanel: React.FC<ScheduledJobsPanelProps> = ({ accessToken }) => {
  const [jobs, setJobs] = useState<JobEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchJSON<ScheduleJobResponse>(
        `${API_BASE}/skills/schedule_job`,
        accessToken,
        { method: 'POST', body: JSON.stringify({ op: 'list' }) }
      );
      setJobs(data.jobs ?? []);
    } catch { setJobs([]); }
    finally { setLoading(false); }
  }, [accessToken]);

  useEffect(() => { void fetchJobs(); }, [fetchJobs]);

  return (
    <div className="sjp">
      <div className="sjp__header">
        <h2 className="sjp__title">⏰ <span>Scheduled Jobs</span></h2>
        <button
          className="sjp__refresh"
          onClick={() => void fetchJobs()}
          title="Refresh jobs"
        >
          ↻ Refresh
        </button>
      </div>

      <div className="sjp__body">
        <div className="sjp__list-area">
          {loading ? (
            <p className="sjp__loading">Loading jobs…</p>
          ) : jobs.length === 0 ? (
            <div className="sjp__empty">
              <p>No scheduled jobs yet.</p>
              <button
                className="sjp__create-btn"
                onClick={() => setShowCreate(true)}
              >
                + Create your first job
              </button>
            </div>
          ) : (
            <div className="sjp__jobs">
              {jobs.map((j) => (
                <JobItem
                  key={j.job_id}
                  job={j}
                  accessToken={accessToken ?? null}
                  onUpdated={() => void fetchJobs()}
                />
              ))}
            </div>
          )}
        </div>

        {showCreate || jobs.length === 0 ? (
          <div className="sjp__create-area">
            <CreateJobForm
              accessToken={accessToken ?? null}
              onCreated={() => {
                void fetchJobs();
                setShowCreate(false);
              }}
            />
          </div>
        ) : (
          <button
            className="sjp__create-btn sjp__create-btn--float"
            onClick={() => setShowCreate(true)}
          >
            + New Job
          </button>
        )}
      </div>
    </div>
  );
};
