import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { VoiceInputControl } from '../common/VoiceInputControl';
import './CalendarView.css';

interface CalendarEventItem {
  id: string;
  summary: string;
  start: string; // ISO timestamp
  end?: string;
  description?: string;
  location?: string;
  category?: 'meeting' | 'hackathon' | 'deadline' | 'personal' | 'reminder';
}

interface CalendarViewProps {
  onBack: () => void;
  accessToken?: string | null;
  onScheduleWithAI?: (prompt: string) => void;
}

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export const CalendarView: React.FC<CalendarViewProps> = ({
  onBack,
  accessToken,
  onScheduleWithAI,
}) => {
  const today = useMemo(() => new Date(), []);
  const [currentYear, setCurrentYear] = useState(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState(today.getMonth()); // 0-indexed
  const [selectedDate, setSelectedDate] = useState<string>(
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  );

  const [events, setEvents] = useState<CalendarEventItem[]>([]);
  const [loadingBackend, setLoadingBackend] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const showNotification = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification((curr) => (curr?.message === message ? null : curr));
    }, 4000);
  };

  const [showAddModal, setShowAddModal] = useState(false);
  const [newEventSummary, setNewEventSummary] = useState('');
  const [newEventDate, setNewEventDate] = useState(selectedDate);
  const [newEventTime, setNewEventTime] = useState('10:00');
  const [newEventLocation, setNewEventLocation] = useState('');
  const [newEventCategory, setNewEventCategory] = useState<'meeting' | 'hackathon' | 'deadline' | 'personal' | 'reminder'>('meeting');
  const [newEventDescription, setNewEventDescription] = useState('');

  // AI Prompt Scheduling state
  const [aiPrompt, setAiPrompt] = useState('');
  const [isParsingAI, setIsParsingAI] = useState(false);
  const [voicePendingEvent, setVoicePendingEvent] = useState<{
    title: string;
    date: string;
    time: string;
    location?: string;
    category?: string;
    description?: string;
  } | null>(null);
  const [isExecutingVoice, setIsExecutingVoice] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch live events from API
  const fetchEvents = useCallback(async () => {
    if (!accessToken) return;
    setLoadingBackend(true);
    setFetchError(null);
    try {
      const res = await fetch(`${API_BASE}/calendar/events`, {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.events)) {
          const mapped: CalendarEventItem[] = data.events.map((e: {
            id: string;
            title?: string;
            start_time?: string;
            end_time?: string;
            description?: string;
            location?: string;
            category?: string;
          }) => ({
            id: e.id,
            summary: e.title || 'Scheduled Event',
            start: e.start_time || `${currentYear}-01-01T10:00:00`,
            end: e.end_time,
            description: e.description,
            location: e.location,
            category: (e.category as CalendarEventItem['category']) || 'meeting',
          }));
          setEvents(mapped);
        }
      } else {
        setFetchError('Failed to load events from the calendar server.');
      }
    } catch {
      setFetchError('Unable to connect to the calendar service. Please check your network.');
    } finally {
      setLoadingBackend(false);
    }
  }, [accessToken, currentYear]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  // Monthly grid calculations
  const daysInMonth = useMemo(() => {
    return new Date(currentYear, currentMonth + 1, 0).getDate();
  }, [currentYear, currentMonth]);

  const firstDayIndex = useMemo(() => {
    return new Date(currentYear, currentMonth, 1).getDay();
  }, [currentYear, currentMonth]);

  const prevMonthDays = useMemo(() => {
    return new Date(currentYear, currentMonth, 0).getDate();
  }, [currentYear, currentMonth]);

  const handlePrevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear((y) => y - 1);
    } else {
      setCurrentMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear((y) => y + 1);
    } else {
      setCurrentMonth((m) => m + 1);
    }
  };

  const handleToday = () => {
    const now = new Date();
    setCurrentYear(now.getFullYear());
    setCurrentMonth(now.getMonth());
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    setSelectedDate(dateStr);
    setNewEventDate(dateStr);
  };

  const handleAddEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEventSummary.trim()) return;
    if (!accessToken) {
      showNotification('Sign in to create and save calendar events.', 'info');
      return;
    }

    const startDateTime = `${newEventDate}T${newEventTime}:00`;
    const payload = {
      title: newEventSummary.trim(),
      start_time: startDateTime,
      description: newEventDescription.trim() || undefined,
      category: newEventCategory,
      location: newEventLocation.trim() || undefined,
    };

    try {
      const res = await fetch(`${API_BASE}/calendar/events`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        await fetchEvents();
        showNotification(`Event "${payload.title}" scheduled successfully.`, 'success');
      } else {
        const err = await res.json().catch(() => ({}));
        showNotification(err.detail || 'Failed to create calendar event.', 'error');
      }
    } catch {
      showNotification('Network error while creating calendar event.', 'error');
    }

    setNewEventSummary('');
    setNewEventDescription('');
    setNewEventLocation('');
    setShowAddModal(false);
  };

  const handleDeleteEvent = async (id: string) => {
    if (!accessToken) {
      showNotification('Sign in to delete calendar events.', 'info');
      return;
    }
    const previous = [...events];
    setEvents((prev) => prev.filter((e) => e.id !== id));

    try {
      const res = await fetch(`${API_BASE}/calendar/events/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        setEvents(previous);
        showNotification('Failed to delete calendar event.', 'error');
      } else {
        showNotification('Event removed from calendar.', 'info');
      }
    } catch {
      setEvents(previous);
      showNotification('Network error while deleting event.', 'error');
    }
  };

  // AI Prompt Parsing
  const handleParseAi = async () => {
    if (!aiPrompt.trim()) return;
    if (!accessToken) {
      showNotification('Sign in to use AI natural language scheduling.', 'info');
      return;
    }
    setIsParsingAI(true);
    try {
      const res = await fetch(`${API_BASE}/calendar/parse-ai`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ prompt: aiPrompt }),
      });
      if (res.ok) {
        const data = await res.json();
        const d = data.draft_event;
        if (d) {
          setNewEventSummary(d.title || '');
          if (d.start_time) {
            const [dt, tm] = d.start_time.split('T');
            setNewEventDate(dt);
            if (tm) setNewEventTime(tm.slice(0, 5));
          }
          setNewEventCategory(d.category || 'meeting');
          setNewEventLocation(d.location || '');
          setNewEventDescription(d.description || '');
          setShowAddModal(true);
          setAiPrompt('');
          showNotification('AI parsed draft ready for confirmation.', 'success');
        }
      } else {
        showNotification('AI could not parse event details. Please try rephrasing.', 'error');
      }
    } catch {
      showNotification('Network error during AI scheduling parse.', 'error');
    } finally {
      setIsParsingAI(false);
    }
  };

  // Direct Voice Prompt Lifecycle with Confirmation
  const handleVoiceSchedulePrompt = async (spokenPrompt: string) => {
    if (!spokenPrompt.trim()) return;
    setAiPrompt(spokenPrompt);
    if (!accessToken) {
      showNotification('Sign in to use voice calendar scheduling.', 'info');
      return;
    }
    setIsParsingAI(true);
    try {
      const res = await fetch(`${API_BASE}/calendar/parse-ai`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ prompt: spokenPrompt }),
      });
      if (res.ok) {
        const data = await res.json();
        const d = data.draft_event;
        if (d) {
          let dt = selectedDate;
          let tm = '15:00';
          if (d.start_time) {
            const parts = d.start_time.split('T');
            dt = parts[0] || selectedDate;
            if (parts[1]) tm = parts[1].slice(0, 5);
          }
          setVoicePendingEvent({
            title: d.title || spokenPrompt,
            date: dt,
            time: tm,
            location: d.location || '',
            category: d.category || 'meeting',
            description: d.description || `Voice prompt: "${spokenPrompt}"`,
          });
        }
      } else {
        setVoicePendingEvent({
          title: spokenPrompt,
          date: selectedDate,
          time: '15:00',
          category: 'meeting',
          description: `Voice prompt: "${spokenPrompt}"`,
        });
      }
    } catch {
      setVoicePendingEvent({
        title: spokenPrompt,
        date: selectedDate,
        time: '15:00',
        category: 'meeting',
        description: `Voice prompt: "${spokenPrompt}"`,
      });
    } finally {
      setIsParsingAI(false);
    }
  };

  const handleConfirmVoiceEvent = async () => {
    if (!voicePendingEvent || !accessToken || isExecutingVoice) return;
    setIsExecutingVoice(true);
    try {
      const startIso = `${voicePendingEvent.date}T${voicePendingEvent.time}:00`;
      const endHour = Math.min(23, parseInt(voicePendingEvent.time.split(':')[0] || '15', 10) + 1);
      const endIso = `${voicePendingEvent.date}T${String(endHour).padStart(2, '0')}:${voicePendingEvent.time.split(':')[1] || '00'}:00`;

      const payload = {
        title: voicePendingEvent.title,
        start_time: startIso,
        end_time: endIso,
        category: voicePendingEvent.category || 'meeting',
        location: voicePendingEvent.location || undefined,
        description: voicePendingEvent.description || undefined,
      };

      const res = await fetch(`${API_BASE}/calendar/events`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        await fetchEvents();
        showNotification(`Event "${voicePendingEvent.title}" scheduled successfully.`, 'success');
        setVoicePendingEvent(null);
        setAiPrompt('');
      } else {
        const err = await res.json().catch(() => ({}));
        showNotification(err.detail || 'Failed to create calendar event.', 'error');
      }
    } catch {
      showNotification('Network error creating calendar event.', 'error');
    } finally {
      setIsExecutingVoice(false);
    }
  };

  // Export iCalendar (.ics)
  const handleExportIcs = async () => {
    if (!accessToken) {
      showNotification('Sign in to export calendar (.ics).', 'info');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/calendar/export/ics`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'roxy_calendar.ics';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showNotification('Calendar exported as roxy_calendar.ics', 'success');
      } else {
        showNotification('Failed to export calendar.', 'error');
      }
    } catch {
      showNotification('Network error exporting calendar.', 'error');
    }
  };

  // Import iCalendar (.ics)
  const handleImportIcs = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!accessToken) {
      showNotification('Sign in to import calendar (.ics).', 'info');
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/calendar/import/ics`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      });
      if (res.ok) {
        await fetchEvents();
        showNotification(`Imported "${file.name}" successfully.`, 'success');
      } else {
        showNotification('Failed to import .ics file.', 'error');
      }
    } catch {
      showNotification('Network error importing .ics file.', 'error');
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Events on the currently selected date
  const selectedDateEvents = useMemo(() => {
    return events.filter((e) => {
      const evtDate = e.start.split('T')[0];
      return evtDate === selectedDate;
    });
  }, [events, selectedDate]);

  // Map of date string -> count of events for dot indicators
  const eventsByDate = useMemo(() => {
    const map: Record<string, number> = {};
    for (const e of events) {
      const d = e.start.split('T')[0];
      map[d] = (map[d] || 0) + 1;
    }
    return map;
  }, [events]);

  const handleScheduleWithAI = (evt: CalendarEventItem) => {
    if (!onScheduleWithAI) return;
    const timeStr = evt.start.includes('T') ? evt.start.split('T')[1].slice(0, 5) : '';
    const dateStr = evt.start.split('T')[0];
    const prompt = `Schedule a reminder job for "${evt.summary}" on ${dateStr}${timeStr ? ` at ${timeStr}` : ''}.`;
    onScheduleWithAI(prompt);
  };

  return (
    <div className="calendar-view">
      {/* Top Header */}
      <header className="calendar-header">
        <div className="calendar-header__left">
          <button type="button" className="view-back-btn" onClick={onBack} aria-label="Back to chat">
            ← Back to Chat
          </button>
          <div className="calendar-header__info">
            <h2 className="calendar-title">
              <span>📅</span> Calendar &amp; Schedule
            </h2>
            <span className="calendar-badge">
              {loadingBackend ? 'Syncing…' : `${events.length} Events`}
            </span>
          </div>
        </div>

        <div className="calendar-header__actions">
          <button
            type="button"
            className="calendar-btn-today"
            onClick={handleExportIcs}
            title="Download iCalendar (.ics)"
          >
            📥 Export .ics
          </button>
          <label className="calendar-btn-today" style={{ cursor: 'pointer', margin: 0 }} title="Upload iCalendar (.ics)">
            📤 Import .ics
            <input
              ref={fileInputRef}
              type="file"
              accept=".ics,text/calendar"
              style={{ display: 'none' }}
              onChange={handleImportIcs}
            />
          </label>
          <VoiceInputControl
            size="sm"
            showLangPicker={true}
            showReadAloud={true}
            readAloudText={
              selectedDateEvents.length > 0
                ? `Events for ${selectedDate}: ${selectedDateEvents
                    .map(
                      (e) =>
                        `${e.summary} at ${
                          e.start.includes('T') ? e.start.split('T')[1].slice(0, 5) : 'all day'
                        }`
                    )
                    .join('. ')}`
                : `No events scheduled for ${selectedDate}.`
            }
            onTranscript={(spokenPrompt) => {
              void handleVoiceSchedulePrompt(spokenPrompt);
            }}
            label="Voice Calendar Assistant"
            toolId="calendar"
          />
          <button
            type="button"
            className="calendar-btn-today"
            onClick={handleToday}
          >
            Today
          </button>
          <button
            type="button"
            className="calendar-btn-add"
            onClick={() => {
              setNewEventDate(selectedDate);
              setShowAddModal(true);
            }}
          >
            + Add Event
          </button>
        </div>
      </header>

      {/* Voice Event Confirmation Card */}
      {voicePendingEvent && (
        <div
          className="calendar-view__voice-confirm"
          style={{
            margin: '0.75rem 1.25rem',
            padding: '0.85rem 1.25rem',
            background: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid rgba(56, 189, 248, 0.4)',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          }}
          role="alertdialog"
          aria-label="Confirm calendar event creation"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.4rem' }}>🎙️</span>
            <div>
              <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>
                Create meeting "{voicePendingEvent.title}" on {voicePendingEvent.date} at {voicePendingEvent.time}?
              </div>
              <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                Category: {voicePendingEvent.category} {voicePendingEvent.location ? `· Location: ${voicePendingEvent.location}` : ''}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={handleConfirmVoiceEvent}
              disabled={isExecutingVoice}
              style={{
                background: 'linear-gradient(135deg, #0d9488, #14b8a6)',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '0.45rem 1rem',
                fontWeight: 600,
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              {isExecutingVoice ? 'Scheduling...' : 'Confirm'}
            </button>
            <button
              type="button"
              onClick={() => setVoicePendingEvent(null)}
              disabled={isExecutingVoice}
              style={{
                background: 'transparent',
                color: '#94a3b8',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                padding: '0.45rem 0.85rem',
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Notification Toast */}
      {notification && (
        <div
          className={`calendar-view__notice calendar-view__notice--${notification.type}`}
          role="status"
        >
          <span>{notification.type === 'success' ? '✓' : notification.type === 'error' ? '⚠️' : 'ℹ️'}</span>
          <span>{notification.message}</span>
        </div>
      )}

      {/* Connection Error Banner */}
      {fetchError && (
        <div className="calendar-view__error-banner" role="alert">
          <div>
            <strong>Connection Error:</strong> {fetchError}
          </div>
          <button
            type="button"
            className="calendar-view__retry-btn"
            onClick={fetchEvents}
          >
            ↻ Retry Connection
          </button>
        </div>
      )}

      {/* Guest Mode Auth Notice */}
      {!accessToken && (
        <div className="calendar-view__auth-banner">
          <span>🔒</span>
          <span>
            You are currently in guest preview mode. Sign in to schedule, persist, and synchronize calendar events across devices.
          </span>
        </div>
      )}

      {/* AI Quick Scheduling Prompt Bar */}
      <div style={{
        display: 'flex',
        gap: '0.5rem',
        background: 'var(--color-surface, #1e1e2e)',
        padding: '0.65rem 0.85rem',
        borderRadius: '0.6rem',
        border: '1px solid var(--color-border, #313244)',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: '1.1rem' }}>⚡</span>
        <input
          type="text"
          placeholder='Schedule with AI: e.g. "Sprint sync with team tomorrow at 3pm for 45 minutes on Zoom"'
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleParseAi();
            }
          }}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: 'var(--color-text, #cdd6f4)',
            fontSize: '0.9rem',
          }}
        />
        <button
          type="button"
          onClick={handleParseAi}
          disabled={!aiPrompt.trim() || isParsingAI}
          style={{
            background: 'var(--color-accent, #89b4fa)',
            color: '#11111b',
            border: 'none',
            borderRadius: '0.4rem',
            padding: '0.35rem 0.75rem',
            fontWeight: 600,
            fontSize: '0.82rem',
            cursor: (!aiPrompt.trim() || isParsingAI) ? 'not-allowed' : 'pointer',
            opacity: (!aiPrompt.trim() || isParsingAI) ? 0.6 : 1,
          }}
        >
          {isParsingAI ? 'Analyzing…' : 'Plan Event'}
        </button>
      </div>

      {/* Main Layout: Left Calendar Grid, Right Agenda/Events Panel */}
      <div className="calendar-layout">
        {/* Left: Monthly Calendar Card */}
        <div className="calendar-card">
          {/* Month/Year Navigation */}
          <div className="calendar-nav">
            <h3 className="calendar-current-month">
              {MONTH_NAMES[currentMonth]} <span>{currentYear}</span>
            </h3>
            <div className="calendar-nav__buttons">
              <button
                type="button"
                className="calendar-nav-btn"
                onClick={handlePrevMonth}
                aria-label="Previous month"
              >
                ‹
              </button>
              <button
                type="button"
                className="calendar-nav-btn"
                onClick={handleNextMonth}
                aria-label="Next month"
              >
                ›
              </button>
            </div>
          </div>

          {/* Day of Week Headers */}
          <div className="calendar-weekdays">
            {DAY_NAMES.map((name) => (
              <div key={name} className="calendar-weekday">
                {name}
              </div>
            ))}
          </div>

          {/* Dates Grid */}
          <div className="calendar-grid">
            {/* Previous month filler days */}
            {Array.from({ length: firstDayIndex }).map((_, i) => {
              const dayNum = prevMonthDays - firstDayIndex + i + 1;
              return (
                <div key={`prev-${i}`} className="calendar-day calendar-day--muted">
                  <span className="calendar-day__number">{dayNum}</span>
                </div>
              );
            })}

            {/* Current month days */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const dayNum = i + 1;
              const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
              const isToday =
                today.getFullYear() === currentYear &&
                today.getMonth() === currentMonth &&
                today.getDate() === dayNum;
              const isSelected = selectedDate === dateStr;
              const count = eventsByDate[dateStr] || 0;

              return (
                <button
                  key={`cur-${dayNum}`}
                  type="button"
                  className={[
                    'calendar-day',
                    isToday ? 'calendar-day--today' : '',
                    isSelected ? 'calendar-day--selected' : '',
                    count > 0 ? 'calendar-day--has-events' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setSelectedDate(dateStr)}
                  aria-label={`${dateStr} with ${count} events`}
                >
                  <span className="calendar-day__number">{dayNum}</span>
                  {count > 0 && (
                    <span className="calendar-day__dots">
                      {Array.from({ length: Math.min(count, 3) }).map((__, dotIdx) => (
                        <span key={dotIdx} className="calendar-day__dot" />
                      ))}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Selected Date Agenda / Events */}
        <div className="calendar-agenda">
          <div className="calendar-agenda__header">
            <div>
              <h3 className="calendar-agenda__title">
                {new Date(`${selectedDate}T00:00:00`).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'short',
                  day: 'numeric',
                })}
              </h3>
              <p className="calendar-agenda__subtitle">
                {selectedDateEvents.length === 0
                  ? 'No events scheduled'
                  : `${selectedDateEvents.length} event${selectedDateEvents.length > 1 ? 's' : ''}`}
              </p>
            </div>
            <button
              type="button"
              className="calendar-agenda__add-btn"
              onClick={() => {
                setNewEventDate(selectedDate);
                setShowAddModal(true);
              }}
              title="Add event for this date"
            >
              + Add
            </button>
          </div>

          <div className="calendar-agenda__list">
            {selectedDateEvents.length === 0 ? (
              <div className="calendar-empty-day" style={{ padding: '2rem 1rem', textAlign: 'center' }}>
                <span className="calendar-empty-icon" style={{ fontSize: '2.5rem', display: 'block', marginBottom: '0.75rem' }}>🗓️</span>
                <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '0 0 0.5rem 0' }}>
                  No events on this day
                </p>
                <p style={{ fontSize: '0.85rem', color: 'var(--color-muted)', margin: '0 0 1rem 0' }}>
                  Use the quick AI scheduling prompt above or add an event manually.
                </p>
                <button
                  type="button"
                  className="calendar-btn-today"
                  onClick={() => {
                    setNewEventDate(selectedDate);
                    setShowAddModal(true);
                  }}
                >
                  Schedule Event
                </button>
              </div>
            ) : (
              selectedDateEvents.map((evt) => {
                const timeStr = evt.start.includes('T')
                  ? evt.start.split('T')[1].slice(0, 5)
                  : 'All day';
                const cat = evt.category || 'meeting';

                return (
                  <div key={evt.id} className={`calendar-event-card calendar-event-card--${cat}`}>
                    <div className="calendar-event-card__time">
                      <span className="calendar-event-time-badge">{timeStr}</span>
                      <span className={`calendar-event-cat-badge calendar-event-cat-badge--${cat}`}>
                        {cat}
                      </span>
                    </div>

                    <div className="calendar-event-card__body">
                      <h4 className="calendar-event-title">{evt.summary}</h4>
                      {evt.location && (
                        <p className="calendar-event-desc" style={{ color: 'var(--color-accent)' }}>
                          📍 {evt.location}
                        </p>
                      )}
                      {evt.description && (
                        <p className="calendar-event-desc">{evt.description}</p>
                      )}
                    </div>

                    <div className="calendar-event-card__actions">
                      {onScheduleWithAI && (
                        <button
                          type="button"
                          className="calendar-event-ai-btn"
                          onClick={() => handleScheduleWithAI(evt)}
                          title="Ask AI to automate reminders or tasks for this event"
                        >
                          ⚡ AI Reminder
                        </button>
                      )}
                      <button
                        type="button"
                        className="calendar-event-del-btn"
                        onClick={() => handleDeleteEvent(evt.id)}
                        title="Delete event"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Add Event Modal */}
      {showAddModal && (
        <div className="calendar-modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="calendar-modal" onClick={(e) => e.stopPropagation()}>
            <div className="calendar-modal__header">
              <h3 className="calendar-modal__title">New Calendar Event</h3>
              <button
                type="button"
                className="calendar-modal__close"
                onClick={() => setShowAddModal(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddEvent} className="calendar-form">
              <div className="calendar-form__group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <label htmlFor="evt-summary" className="calendar-form__label" style={{ margin: 0 }}>Event Title *</label>
                  <VoiceInputControl
                    size="sm"
                    showReadAloud={false}
                    onTranscript={(t) => setNewEventSummary(t)}
                    label="Speak event title"
                  />
                </div>
                <input
                  id="evt-summary"
                  type="text"
                  required
                  placeholder="e.g. AI Hackathon Project Review"
                  value={newEventSummary}
                  onChange={(e) => setNewEventSummary(e.target.value)}
                  className="calendar-form__input"
                  autoFocus
                />
              </div>

              <div className="calendar-form__row">
                <div className="calendar-form__group">
                  <label htmlFor="evt-date" className="calendar-form__label">Date</label>
                  <input
                    id="evt-date"
                    type="date"
                    required
                    value={newEventDate}
                    onChange={(e) => setNewEventDate(e.target.value)}
                    className="calendar-form__input"
                  />
                </div>

                <div className="calendar-form__group">
                  <label htmlFor="evt-time" className="calendar-form__label">Time</label>
                  <input
                    id="evt-time"
                    type="time"
                    required
                    value={newEventTime}
                    onChange={(e) => setNewEventTime(e.target.value)}
                    className="calendar-form__input"
                  />
                </div>
              </div>

              <div className="calendar-form__row">
                <div className="calendar-form__group">
                  <label htmlFor="evt-category" className="calendar-form__label">Category</label>
                  <select
                    id="evt-category"
                    value={newEventCategory}
                    onChange={(e) => setNewEventCategory(e.target.value as typeof newEventCategory)}
                    className="calendar-form__select"
                  >
                    <option value="meeting">🤝 Meeting</option>
                    <option value="hackathon">🚀 Hackathon</option>
                    <option value="deadline">🎯 Deadline</option>
                    <option value="reminder">⏰ Reminder</option>
                    <option value="personal">🌟 Personal</option>
                  </select>
                </div>

                <div className="calendar-form__group">
                  <label htmlFor="evt-loc" className="calendar-form__label">Location / Link</label>
                  <input
                    id="evt-loc"
                    type="text"
                    placeholder="e.g. Zoom, Google Meet, or Room 402"
                    value={newEventLocation}
                    onChange={(e) => setNewEventLocation(e.target.value)}
                    className="calendar-form__input"
                  />
                </div>
              </div>

              <div className="calendar-form__group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <label htmlFor="evt-desc" className="calendar-form__label" style={{ margin: 0 }}>Notes / Description</label>
                  <VoiceInputControl
                    size="sm"
                    showReadAloud={Boolean(newEventDescription)}
                    readAloudText={newEventDescription}
                    onTranscript={(t) => setNewEventDescription((prev) => prev ? `${prev} ${t}` : t)}
                    label="Dictate event description"
                  />
                </div>
                <textarea
                  id="evt-desc"
                  rows={3}
                  placeholder="Additional agenda or meeting details..."
                  value={newEventDescription}
                  onChange={(e) => setNewEventDescription(e.target.value)}
                  className="calendar-form__textarea"
                />
              </div>

              <div className="calendar-form__actions">
                <button
                  type="button"
                  className="calendar-btn-cancel"
                  onClick={() => setShowAddModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="calendar-btn-submit"
                >
                  Save Event
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
