// ScheduledJobsPanel — list, create, cancel, pause, resume scheduled jobs
// Uses GET/POST /api/v1/skills/schedule_job

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { parseNaturalSchedule, formatHumanSchedule } from '../../utils/naturalCron';
import './ScheduledJobsPanel.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

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
    throw new Error(typeof err.detail === 'string' ? err.detail : err.error || `HTTP ${res.status}`);
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

const SCHEDULE_PRESETS = [
  { label: 'Every day at 9am', value: 'Every day at 9am' },
  { label: 'Weekdays at 8am', value: 'Every weekday at 8am' },
  { label: 'Every hour', value: 'Every hour' },
  { label: 'Every Monday at 10am', value: 'Every Monday at 10am' },
  { label: 'Every 30 mins', value: 'Every 30 minutes' },
  { label: 'Every Friday at 5pm', value: 'Every Friday at 5pm' },
];

export interface TimezoneOption {
  value: string;
  label: string;
  region: string;
  offset?: string;
  country?: string;
}

const DEFAULT_TIMEZONE_OPTIONS: TimezoneOption[] = [
  // South Asia & Gulf
  { value: 'Asia/Karachi', label: '🇵🇰 Asia/Karachi (PKT - UTC+5)', region: 'South Asia & Gulf', offset: 'UTC+5', country: 'Pakistan' },
  { value: 'Asia/Kolkata', label: '🇮🇳 Asia/Kolkata (IST - UTC+5:30)', region: 'South Asia & Gulf', offset: 'UTC+5:30', country: 'India' },
  { value: 'Asia/Dhaka', label: '🇧🇩 Asia/Dhaka (BST - UTC+6)', region: 'South Asia & Gulf', offset: 'UTC+6', country: 'Bangladesh' },
  { value: 'Asia/Colombo', label: '🇱🇰 Asia/Colombo (SLST - UTC+5:30)', region: 'South Asia & Gulf', offset: 'UTC+5:30', country: 'Sri Lanka' },
  { value: 'Asia/Kathmandu', label: '🇳🇵 Asia/Kathmandu (NPT - UTC+5:45)', region: 'South Asia & Gulf', offset: 'UTC+5:45', country: 'Nepal' },
  { value: 'Asia/Dubai', label: '🇦🇪 Asia/Dubai (GST - UTC+4)', region: 'South Asia & Gulf', offset: 'UTC+4', country: 'United Arab Emirates' },
  { value: 'Asia/Riyadh', label: '🇸🇦 Asia/Riyadh (AST - UTC+3)', region: 'South Asia & Gulf', offset: 'UTC+3', country: 'Saudi Arabia' },
  { value: 'Asia/Qatar', label: '🇶🇦 Asia/Qatar (AST - UTC+3)', region: 'South Asia & Gulf', offset: 'UTC+3', country: 'Qatar' },
  { value: 'Asia/Kuwait', label: '🇰🇼 Asia/Kuwait (AST - UTC+3)', region: 'South Asia & Gulf', offset: 'UTC+3', country: 'Kuwait' },
  { value: 'Asia/Muscat', label: '🇴🇲 Asia/Muscat (GST - UTC+4)', region: 'South Asia & Gulf', offset: 'UTC+4', country: 'Oman' },
  { value: 'Asia/Bahrain', label: '🇧🇭 Asia/Bahrain (AST - UTC+3)', region: 'South Asia & Gulf', offset: 'UTC+3', country: 'Bahrain' },

  // East & Southeast Asia
  { value: 'Asia/Singapore', label: '🇸🇬 Asia/Singapore (SGT - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'Singapore' },
  { value: 'Asia/Kuala_Lumpur', label: '🇲🇾 Asia/Kuala_Lumpur (MYT - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'Malaysia' },
  { value: 'Asia/Bangkok', label: '🇹🇭 Asia/Bangkok (ICT - UTC+7)', region: 'East & Southeast Asia', offset: 'UTC+7', country: 'Thailand' },
  { value: 'Asia/Jakarta', label: '🇮🇩 Asia/Jakarta (WIB - UTC+7)', region: 'East & Southeast Asia', offset: 'UTC+7', country: 'Indonesia' },
  { value: 'Asia/Makassar', label: '🇮🇩 Asia/Makassar (WITA - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'Indonesia' },
  { value: 'Asia/Manila', label: '🇵🇭 Asia/Manila (PST/PHT - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'Philippines' },
  { value: 'Asia/Ho_Chi_Minh', label: '🇻🇳 Asia/Ho_Chi_Minh (ICT - UTC+7)', region: 'East & Southeast Asia', offset: 'UTC+7', country: 'Vietnam' },
  { value: 'Asia/Shanghai', label: '🇨🇳 Asia/Shanghai (CST - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'China' },
  { value: 'Asia/Hong_Kong', label: '🇭🇰 Asia/Hong_Kong (HKT - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'Hong Kong' },
  { value: 'Asia/Taipei', label: '🇹🇼 Asia/Taipei (CST - UTC+8)', region: 'East & Southeast Asia', offset: 'UTC+8', country: 'Taiwan' },
  { value: 'Asia/Tokyo', label: '🇯🇵 Asia/Tokyo (JST - UTC+9)', region: 'East & Southeast Asia', offset: 'UTC+9', country: 'Japan' },
  { value: 'Asia/Seoul', label: '🇰🇷 Asia/Seoul (KST - UTC+9)', region: 'East & Southeast Asia', offset: 'UTC+9', country: 'South Korea' },

  // Central & West Asia
  { value: 'Asia/Baku', label: '🇦🇿 Asia/Baku (AZT - UTC+4)', region: 'Central & West Asia', offset: 'UTC+4', country: 'Azerbaijan' },
  { value: 'Asia/Tashkent', label: '🇺🇿 Asia/Tashkent (UZT - UTC+5)', region: 'Central & West Asia', offset: 'UTC+5', country: 'Uzbekistan' },
  { value: 'Asia/Almaty', label: '🇰🇿 Asia/Almaty (ALMT - UTC+5)', region: 'Central & West Asia', offset: 'UTC+5', country: 'Kazakhstan' },
  { value: 'Europe/Istanbul', label: '🇹🇷 Europe/Istanbul (TRT - UTC+3)', region: 'Central & West Asia', offset: 'UTC+3', country: 'Turkey' },
  { value: 'Asia/Jerusalem', label: '🇮🇱 Asia/Jerusalem (IST/IDT - UTC+2/+3)', region: 'Central & West Asia', offset: 'UTC+2', country: 'Israel' },
  { value: 'Asia/Beirut', label: '🇱🇧 Asia/Beirut (EET/EEST - UTC+2/+3)', region: 'Central & West Asia', offset: 'UTC+2', country: 'Lebanon' },

  // Europe & UK
  { value: 'Europe/London', label: '🇬🇧 Europe/London (GMT/BST - UTC+0/+1)', region: 'Europe & UK', offset: 'UTC+0', country: 'United Kingdom' },
  { value: 'Europe/Dublin', label: '🇮🇪 Europe/Dublin (IST/GMT - UTC+0/+1)', region: 'Europe & UK', offset: 'UTC+0', country: 'Ireland' },
  { value: 'Europe/Paris', label: '🇫🇷 Europe/Paris (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'France' },
  { value: 'Europe/Berlin', label: '🇩🇪 Europe/Berlin (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Germany' },
  { value: 'Europe/Rome', label: '🇮🇹 Europe/Rome (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Italy' },
  { value: 'Europe/Madrid', label: '🇪🇸 Europe/Madrid (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Spain' },
  { value: 'Europe/Amsterdam', label: '🇳🇱 Europe/Amsterdam (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Netherlands' },
  { value: 'Europe/Brussels', label: '🇧🇪 Europe/Brussels (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Belgium' },
  { value: 'Europe/Zurich', label: '🇨🇭 Europe/Zurich (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Switzerland' },
  { value: 'Europe/Vienna', label: '🇦🇹 Europe/Vienna (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Austria' },
  { value: 'Europe/Stockholm', label: '🇸🇪 Europe/Stockholm (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Sweden' },
  { value: 'Europe/Oslo', label: '🇳🇴 Europe/Oslo (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Norway' },
  { value: 'Europe/Copenhagen', label: '🇩🇰 Europe/Copenhagen (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Denmark' },
  { value: 'Europe/Helsinki', label: '🇫🇮 Europe/Helsinki (EET/EEST - UTC+2/+3)', region: 'Europe & UK', offset: 'UTC+2', country: 'Finland' },
  { value: 'Europe/Warsaw', label: '🇵🇱 Europe/Warsaw (CET/CEST - UTC+1/+2)', region: 'Europe & UK', offset: 'UTC+1', country: 'Poland' },
  { value: 'Europe/Athens', label: '🇬🇷 Europe/Athens (EET/EEST - UTC+2/+3)', region: 'Europe & UK', offset: 'UTC+2', country: 'Greece' },
  { value: 'Europe/Lisbon', label: '🇵🇹 Europe/Lisbon (WET/WEST - UTC+0/+1)', region: 'Europe & UK', offset: 'UTC+0', country: 'Portugal' },
  { value: 'Europe/Moscow', label: '🇷🇺 Europe/Moscow (MSK - UTC+3)', region: 'Europe & UK', offset: 'UTC+3', country: 'Russia' },

  // Americas
  { value: 'America/New_York', label: '🇺🇸 America/New_York (EST/EDT - UTC-5/-4)', region: 'Americas', offset: 'UTC-5', country: 'United States' },
  { value: 'America/Chicago', label: '🇺🇸 America/Chicago (CST/CDT - UTC-6/-5)', region: 'Americas', offset: 'UTC-6', country: 'United States' },
  { value: 'America/Denver', label: '🇺🇸 America/Denver (MST/MDT - UTC-7/-6)', region: 'Americas', offset: 'UTC-7', country: 'United States' },
  { value: 'America/Phoenix', label: '🇺🇸 America/Phoenix (MST - UTC-7)', region: 'Americas', offset: 'UTC-7', country: 'United States' },
  { value: 'America/Los_Angeles', label: '🇺🇸 America/Los_Angeles (PST/PDT - UTC-8/-7)', region: 'Americas', offset: 'UTC-8', country: 'United States' },
  { value: 'America/Anchorage', label: '🇺🇸 America/Anchorage (AKST/AKDT - UTC-9/-8)', region: 'Americas', offset: 'UTC-9', country: 'United States' },
  { value: 'Pacific/Honolulu', label: '🇺🇸 Pacific/Honolulu (HST - UTC-10)', region: 'Americas', offset: 'UTC-10', country: 'United States' },
  { value: 'America/Toronto', label: '🇨🇦 America/Toronto (EST/EDT - UTC-5/-4)', region: 'Americas', offset: 'UTC-5', country: 'Canada' },
  { value: 'America/Vancouver', label: '🇨🇦 America/Vancouver (PST/PDT - UTC-8/-7)', region: 'Americas', offset: 'UTC-8', country: 'Canada' },
  { value: 'America/Edmonton', label: '🇨🇦 America/Edmonton (MST/MDT - UTC-7/-6)', region: 'Americas', offset: 'UTC-7', country: 'Canada' },
  { value: 'America/Halifax', label: '🇨🇦 America/Halifax (AST/ADT - UTC-4/-3)', region: 'Americas', offset: 'UTC-4', country: 'Canada' },
  { value: 'America/Mexico_City', label: '🇲🇽 America/Mexico_City (CST - UTC-6)', region: 'Americas', offset: 'UTC-6', country: 'Mexico' },
  { value: 'America/Bogota', label: '🇨🇴 America/Bogota (COT - UTC-5)', region: 'Americas', offset: 'UTC-5', country: 'Colombia' },
  { value: 'America/Lima', label: '🇵🇪 America/Lima (PET - UTC-5)', region: 'Americas', offset: 'UTC-5', country: 'Peru' },
  { value: 'America/Sao_Paulo', label: '🇧🇷 America/Sao_Paulo (BRT - UTC-3)', region: 'Americas', offset: 'UTC-3', country: 'Brazil' },
  { value: 'America/Buenos_Aires', label: '🇦🇷 America/Buenos_Aires (ART - UTC-3)', region: 'Americas', offset: 'UTC-3', country: 'Argentina' },
  { value: 'America/Santiago', label: '🇨🇱 America/Santiago (CLT/CLST - UTC-4/-3)', region: 'Americas', offset: 'UTC-4', country: 'Chile' },

  // Africa
  { value: 'Africa/Cairo', label: '🇪🇬 Africa/Cairo (EET/EEST - UTC+2/+3)', region: 'Africa', offset: 'UTC+2', country: 'Egypt' },
  { value: 'Africa/Johannesburg', label: '🇿🇦 Africa/Johannesburg (SAST - UTC+2)', region: 'Africa', offset: 'UTC+2', country: 'South Africa' },
  { value: 'Africa/Lagos', label: '🇳🇬 Africa/Lagos (WAT - UTC+1)', region: 'Africa', offset: 'UTC+1', country: 'Nigeria' },
  { value: 'Africa/Nairobi', label: '🇰🇪 Africa/Nairobi (EAT - UTC+3)', region: 'Africa', offset: 'UTC+3', country: 'Kenya' },
  { value: 'Africa/Casablanca', label: '🇲🇦 Africa/Casablanca (WET/WEST - UTC+1)', region: 'Africa', offset: 'UTC+1', country: 'Morocco' },
  { value: 'Africa/Accra', label: '🇬🇭 Africa/Accra (GMT - UTC+0)', region: 'Africa', offset: 'UTC+0', country: 'Ghana' },
  { value: 'Africa/Addis_Ababa', label: '🇪🇹 Africa/Addis_Ababa (EAT - UTC+3)', region: 'Africa', offset: 'UTC+3', country: 'Ethiopia' },

  // Australia & Pacific
  { value: 'Australia/Sydney', label: '🇦🇺 Australia/Sydney (AEST/AEDT - UTC+10/+11)', region: 'Australia & Pacific', offset: 'UTC+10', country: 'Australia' },
  { value: 'Australia/Melbourne', label: '🇦🇺 Australia/Melbourne (AEST/AEDT - UTC+10/+11)', region: 'Australia & Pacific', offset: 'UTC+10', country: 'Australia' },
  { value: 'Australia/Brisbane', label: '🇦🇺 Australia/Brisbane (AEST - UTC+10)', region: 'Australia & Pacific', offset: 'UTC+10', country: 'Australia' },
  { value: 'Australia/Adelaide', label: '🇦🇺 Australia/Adelaide (ACST/ACDT - UTC+9:30/+10:30)', region: 'Australia & Pacific', offset: 'UTC+9:30', country: 'Australia' },
  { value: 'Australia/Perth', label: '🇦🇺 Australia/Perth (AWST - UTC+8)', region: 'Australia & Pacific', offset: 'UTC+8', country: 'Australia' },
  { value: 'Pacific/Auckland', label: '🇳🇿 Pacific/Auckland (NZST/NZDT - UTC+12/+13)', region: 'Australia & Pacific', offset: 'UTC+12', country: 'New Zealand' },
  { value: 'Pacific/Fiji', label: '🇫🇯 Pacific/Fiji (FJT - UTC+12)', region: 'Australia & Pacific', offset: 'UTC+12', country: 'Fiji' },

  // UTC / Universal
  { value: 'UTC', label: '🌐 UTC (Coordinated Universal Time - UTC+0)', region: 'UTC / Universal', offset: 'UTC+0', country: 'Global' },
];

// ─── Create job form ──────────────────────────────────────────────

interface CreateJobFormProps {
  accessToken: string | null;
  onCreated: () => void;
}

const CreateJobForm: React.FC<CreateJobFormProps> = ({ accessToken, onCreated }) => {
  const [name, setName] = useState('');
  const [schedule, setSchedule] = useState('');
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Karachi');
  const [isCustomTz, setIsCustomTz] = useState(false);
  const [timezoneOptions, setTimezoneOptions] = useState<TimezoneOption[]>(DEFAULT_TIMEZONE_OPTIONS);
  const [tzFilter, setTzFilter] = useState('');
  const [message, setMessage] = useState('');
  const [confirmOnFire, setConfirmOnFire] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Dynamic timezone discovery from backend
  useEffect(() => {
    let unmounted = false;
    fetch(`${API_BASE}/skills/schedule_job/timezones`)
      .then((res) => res.json())
      .then((data) => {
        if (!unmounted && data.success && Array.isArray(data.timezones) && data.timezones.length > 0) {
          setTimezoneOptions(data.timezones);
        }
      })
      .catch(() => {
        // Fallback already pre-set to DEFAULT_TIMEZONE_OPTIONS
      });
    return () => {
      unmounted = true;
    };
  }, []);

  const parsedSchedule = parseNaturalSchedule(schedule);

  // Filtered and grouped timezones
  const filteredTzOptions = useMemo(() => {
    if (!tzFilter.trim()) return timezoneOptions;
    const q = tzFilter.trim().toLowerCase();
    return timezoneOptions.filter(
      (opt) =>
        opt.value.toLowerCase().includes(q) ||
        opt.label.toLowerCase().includes(q) ||
        (opt.region && opt.region.toLowerCase().includes(q)) ||
        (opt.country && opt.country.toLowerCase().includes(q)) ||
        (opt.offset && opt.offset.toLowerCase().includes(q))
    );
  }, [timezoneOptions, tzFilter]);

  const groupedTimezones = useMemo(() => {
    const groups: Record<string, TimezoneOption[]> = {};
    for (const opt of filteredTzOptions) {
      const reg = opt.region || 'Other';
      if (!groups[reg]) groups[reg] = [];
      groups[reg].push(opt);
    }
    return groups;
  }, [filteredTzOptions]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !schedule.trim()) return;
    setSubmitting(true);
    setError(null);
    setSuccessMsg(null);

    // Use resolved cron if parsed, otherwise send raw
    const scheduleToSend = parsedSchedule.isValid ? parsedSchedule.cron : schedule.trim();

    try {
      const result = await fetchJSON<ScheduleJobResponse>(
        `${API_BASE}/skills/schedule_job`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({
            op: 'create',
            name: name.trim(),
            schedule: scheduleToSend,
            timezone: timezone.trim(),
            action: {
              agent_slug: 'automation',
              skill_slug: null,
              inputs: message.trim() ? { message: message.trim() } : { message: name.trim() },
            },
            confirm_on_fire: confirmOnFire,
            confirm: true,
          }),
        }
      );
      if (result.success) {
        setName('');
        setSchedule('');
        setMessage('');
        setSuccessMsg('Job scheduled successfully!');
        setTimeout(() => setSuccessMsg(null), 4000);
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

      {error && <div className="sjp-create-form__error" role="alert">{error}</div>}
      {successMsg && <div className="sjp-create-form__success" role="alert">{successMsg}</div>}

      <div className="sjp-create-form__row">
        <label className="sjp-create-form__label">
          Job name *
          <input
            type="text"
            className="sjp-create-form__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Daily morning briefing"
            required
            maxLength={100}
          />
        </label>
        <label className="sjp-create-form__label">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Timezone ({timezoneOptions.length} routes) *</span>
            <button
              type="button"
              onClick={() => setIsCustomTz((c) => !c)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-accent, #89b4fa)',
                fontSize: '0.75rem',
                cursor: 'pointer',
                textDecoration: 'underline',
                padding: 0,
              }}
            >
              {isCustomTz ? 'Select from list' : 'Custom IANA'}
            </button>
          </div>
          {isCustomTz ? (
            <input
              type="text"
              className="sjp-create-form__input"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="e.g. Asia/Karachi, UTC, America/New_York"
              required
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <input
                type="text"
                className="sjp-create-form__input"
                style={{ fontSize: '0.8rem', padding: '0.35rem 0.6rem' }}
                placeholder="🔍 Search city, country, or code…"
                value={tzFilter}
                onChange={(e) => setTzFilter(e.target.value)}
              />
              <select
                className="sjp-create-form__input"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                required
              >
                {!timezoneOptions.some((o) => o.value === timezone) && (
                  <option value={timezone}>{timezone} (Detected Local)</option>
                )}
                {(Object.entries(groupedTimezones) as [string, TimezoneOption[]][]).map(([region, opts]) => (
                  <optgroup key={region} label={`🌍 ${region} (${opts.length})`}>
                    {opts.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          )}
        </label>
      </div>

      <div className="sjp-create-form__label">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Schedule (Natural Language or Cron) *</span>
          <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>Powered by Natural Language Cron</span>
        </div>
        <input
          type="text"
          className="sjp-create-form__input"
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
          placeholder="e.g. Every day at 9am, Weekdays at 8am, Every 30 mins"
          required
        />

        {/* Quick Presets */}
        <div className="sjp-presets">
          <span className="sjp-presets__hint">Presets:</span>
          {SCHEDULE_PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              className="sjp-preset-btn"
              onClick={() => setSchedule(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Live Natural Language Feedback */}
        {schedule.trim() && (
          <div className={`sjp-parsed-feedback ${parsedSchedule.isValid ? 'sjp-parsed-feedback--valid' : 'sjp-parsed-feedback--invalid'}`}>
            {parsedSchedule.isValid ? (
              <>
                <span className="sjp-parsed-icon">✨</span>
                <span>
                  <strong>Schedule:</strong> {parsedSchedule.description}
                </span>
                <code className="sjp-parsed-cron">{parsedSchedule.cron}</code>
              </>
            ) : (
              <>
                <span className="sjp-parsed-icon">ℹ️</span>
                <span>Type plain English (e.g. "Every day at 9am") or standard 5-part cron.</span>
              </>
            )}
          </div>
        )}
      </div>

      <label className="sjp-create-form__label">
        Task Instructions / Prompt *
        <textarea
          className="sjp-create-form__input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="What should ROXY AI do when this job runs? (e.g. 'Summarize top market news and send an alert')"
          rows={3}
          maxLength={500}
        />
      </label>

      <label className="sjp-create-form__checkbox">
        <input
          type="checkbox"
          checked={confirmOnFire}
          onChange={(e) => setConfirmOnFire(e.target.checked)}
        />
        Require my confirmation before executing each run
      </label>

      <div className="sjp-create-form__actions">
        <button
          type="submit"
          className="sjp-create-form__submit"
          disabled={submitting || !name.trim() || !schedule.trim()}
        >
          {submitting ? 'Scheduling…' : 'Create Scheduled Job'}
        </button>
      </div>
    </form>
  );
};

// ─── Main panel ───────────────────────────────────────────────────

export interface ScheduledJobsPanelProps {
  accessToken: string | null;
  onBack?: () => void;
  onConfirmRequired?: (token: string, skill: string, action: string) => void;
}

export const ScheduledJobsPanel: React.FC<ScheduledJobsPanelProps> = ({
  accessToken,
  onBack,
}) => {
  const [jobs, setJobs] = useState<JobEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchJSON<ScheduleJobResponse>(
        `${API_BASE}/skills/schedule_job`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({ op: 'list', confirm: true }),
        }
      );
      if (result.success && result.jobs) {
        setJobs(result.jobs);
      } else {
        setError(result.error ?? 'Failed to list jobs');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleOp = async (op: 'pause' | 'resume' | 'cancel', jobId: string) => {
    setActionLoading(jobId);
    setError(null);

    // Save previous state for rollback if network fails
    const prevJobs = [...jobs];

    // Optimistic UI updates (0ms instantaneous visual feedback)
    if (op === 'cancel') {
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    } else if (op === 'pause') {
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? { ...j, status: 'paused' } : j)));
    } else if (op === 'resume') {
      setJobs((prev) => prev.map((j) => (j.job_id === jobId ? { ...j, status: 'active' } : j)));
    }

    try {
      const result = await fetchJSON<ScheduleJobResponse>(
        `${API_BASE}/skills/schedule_job`,
        accessToken,
        {
          method: 'POST',
          body: JSON.stringify({ op, job_id: jobId, confirm: true }),
        }
      );
      if (!result.success) {
        throw new Error(result.error || `Failed to ${op} job`);
      }
      await loadJobs();
    } catch (err) {
      // Revert optimistic state on failure
      setJobs(prevJobs);
      setError((err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="sjp-panel">
      <div className="sjp-header">
        <div className="sjp-header__left">
          {onBack && (
            <button
              type="button"
              className="view-back-btn"
              onClick={onBack}
              title="Return to Chat"
              aria-label="Return to Chat"
            >
              ← Back to Chat
            </button>
          )}
          <h2 className="sjp-title">⏰ Scheduled Jobs & Reminders</h2>
        </div>
        <button
          type="button"
          className="sjp-refresh-btn"
          onClick={loadJobs}
          disabled={loading}
          title="Refresh job list"
        >
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      <CreateJobForm accessToken={accessToken} onCreated={loadJobs} />

      <div className="sjp-list-section">
        <h3 className="sjp-list-title">Active & Past Jobs ({jobs.length})</h3>

        {error && <div className="sjp-error" role="alert">{error}</div>}

        {loading ? (
          <p className="sjp-status">Loading jobs…</p>
        ) : jobs.length === 0 ? (
          <div className="sjp-empty">
            <p>No scheduled jobs yet.</p>
            <p className="sjp-empty__hint">
              Use the form above to schedule automated tasks, reminders, or briefings.
            </p>
          </div>
        ) : (
          <div className="sjp-jobs-table-wrapper">
            <table className="sjp-jobs-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Schedule</th>
                  <th>Status</th>
                  <th>Next Fire</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.job_id} className={`sjp-row sjp-row--${job.status}`}>
                    <td className="sjp-cell__name">
                      <strong>{job.name}</strong>
                      {job.confirm_on_fire && (
                        <span className="sjp-badge sjp-badge--confirm" title="Requires confirmation">
                          Gated
                        </span>
                      )}
                    </td>
                    <td className="sjp-cell__schedule">
                      <div className="sjp-schedule-human">{formatHumanSchedule(job.schedule)}</div>
                      <div className="sjp-schedule-sub">
                        <code>{job.schedule}</code>
                        <span className="sjp-tz"> · {job.timezone}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`sjp-status-pill sjp-status-pill--${job.status}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>{fmtDate(job.next_fire_at)}</td>
                    <td>{fmtDate(job.created_at)}</td>
                    <td className="sjp-cell__actions">
                      {job.status === 'active' && (
                        <button
                          type="button"
                          className="sjp-btn sjp-btn--pause"
                          onClick={() => handleOp('pause', job.job_id)}
                          disabled={actionLoading === job.job_id}
                        >
                          Pause
                        </button>
                      )}
                      {job.status === 'paused' && (
                        <button
                          type="button"
                          className="sjp-btn sjp-btn--resume"
                          onClick={() => handleOp('resume', job.job_id)}
                          disabled={actionLoading === job.job_id}
                        >
                          Resume
                        </button>
                      )}
                      <button
                        type="button"
                        className="sjp-btn sjp-btn--cancel"
                        onClick={() => handleOp('cancel', job.job_id)}
                        disabled={actionLoading === job.job_id}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
