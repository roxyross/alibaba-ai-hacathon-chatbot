import React, { useState, useEffect, useMemo } from 'react';
import { VoiceInputControl } from '../common/VoiceInputControl';
import './CalendarView.css';


interface CalendarEventItem {
  id: string;
  summary: string;
  start: string; // ISO or YYYY-MM-DDTHH:mm
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

const API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

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

  const [events, setEvents] = useState<CalendarEventItem[]>(() => {
    try {
      const saved = localStorage.getItem('roxy_calendar_events');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [deletedIds, setDeletedIds] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('roxy_deleted_calendar_event_ids');
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch {
      return new Set();
    }
  });

  const [loadingBackend, setLoadingBackend] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newEventSummary, setNewEventSummary] = useState('');
  const [newEventDate, setNewEventDate] = useState(selectedDate);
  const [newEventTime, setNewEventTime] = useState('10:00');
  const [newEventCategory, setNewEventCategory] = useState<'meeting' | 'hackathon' | 'deadline' | 'personal' | 'reminder'>('meeting');
  const [newEventDescription, setNewEventDescription] = useState('');

  // Persist user events to local storage
  useEffect(() => {
    try {
      localStorage.setItem('roxy_calendar_events', JSON.stringify(events));
    } catch {
      // ignore
    }
  }, [events]);

  // Load demo & backend events from /api/v1/skills/calendar_read
  useEffect(() => {
    const fetchBackendEvents = async () => {
      setLoadingBackend(true);
      try {
        const res = await fetch(`${API_BASE}/skills/calendar_read`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify({
            start_date: `${currentYear}-01-01`,
            end_date: `${currentYear}-12-31`,
          }),
        });

        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.events) && data.events.length > 0) {
            const mapped: CalendarEventItem[] = data.events.map((e: {
              uid?: string;
              summary?: string;
              start?: string;
              end?: string;
              description?: string;
              location?: string;
            }, idx: number) => ({
              id: e.uid || `backend-evt-${idx}`,
              summary: e.summary || 'Scheduled Event',
              start: e.start || `${currentYear}-09-09T14:00:00`,
              end: e.end,
              description: e.description,
              location: e.location,
              category: (e.summary?.toLowerCase().includes('hackathon') ? 'hackathon' : 'meeting'),
            }));

            setEvents((prev) => {
              const existingIds = new Set(prev.map((item) => item.id));
              const newItems = mapped.filter((item) => !existingIds.has(item.id) && !deletedIds.has(item.id));
              return [...prev, ...newItems];
            });
          }
        }
      } catch {
        // Backend calendar read optional fallback
      } finally {
        setLoadingBackend(false);
      }
    };

    fetchBackendEvents();
  }, [currentYear, accessToken]);

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

  const handleAddEvent = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEventSummary.trim()) return;

    const startDateTime = `${newEventDate}T${newEventTime}:00`;
    const newEvt: CalendarEventItem = {
      id: `custom-${Date.now()}`,
      summary: newEventSummary.trim(),
      start: startDateTime,
      description: newEventDescription.trim() || undefined,
      category: newEventCategory,
    };

    setEvents((prev) => [newEvt, ...prev]);
    setNewEventSummary('');
    setNewEventDescription('');
    setShowAddModal(false);
  };

  const handleDeleteEvent = (id: string) => {
    setEvents((prev) => prev.filter((e) => e.id !== id));
    setDeletedIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      try {
        localStorage.setItem('roxy_deleted_calendar_event_ids', JSON.stringify(Array.from(next)));
      } catch {
        // ignore
      }
      return next;
    });
  };

  // Events on the currently selected date
  const selectedDateEvents = useMemo(() => {
    return events.filter((e) => {
      const evtDate = e.start.split('T')[0];
      return evtDate === selectedDate;
    });
  }, [events, selectedDate]);

  // Map of date string -> count of events for quick dot indicators
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
              {loadingBackend ? 'Syncing…' : 'Sync Active'}
            </span>
          </div>
        </div>

        <div className="calendar-header__actions">
          <VoiceInputControl
            size="sm"
            showLangPicker={true}
            showReadAloud={selectedDateEvents.length > 0}
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
              if (onScheduleWithAI) {
                onScheduleWithAI(spokenPrompt);
              } else {
                setNewEventSummary(spokenPrompt);
                setNewEventDate(selectedDate);
                setShowAddModal(true);
              }
            }}
            label="Voice Calendar Assistant"
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
              const eventCount = eventsByDate[dateStr] || 0;

              return (
                <button
                  type="button"
                  key={`day-${dayNum}`}
                  className={`calendar-day${isToday ? ' calendar-day--today' : ''}${isSelected ? ' calendar-day--selected' : ''}`}
                  onClick={() => {
                    setSelectedDate(dateStr);
                    setNewEventDate(dateStr);
                  }}
                >
                  <span className="calendar-day__number">{dayNum}</span>
                  {eventCount > 0 && (
                    <div className="calendar-day__dots" aria-label={`${eventCount} events`}>
                      <span className="calendar-dot" />
                      {eventCount > 1 && <span className="calendar-dot" />}
                      {eventCount > 2 && <span className="calendar-dot" />}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Selected Date Agenda */}
        <div className="calendar-agenda-card">
          <div className="calendar-agenda-header">
            <div>
              <h3 className="calendar-agenda-title">
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </h3>
              <span className="calendar-agenda-subtitle">
                {selectedDateEvents.length} {selectedDateEvents.length === 1 ? 'event' : 'events'} scheduled
              </span>
            </div>
            <button
              type="button"
              className="calendar-agenda-quick-add"
              onClick={() => {
                setNewEventDate(selectedDate);
                setShowAddModal(true);
              }}
              title="Add event for this date"
            >
              + Add
            </button>
          </div>

          <div className="calendar-events-list">
            {selectedDateEvents.length === 0 ? (
              <div className="calendar-events-empty">
                <span className="calendar-empty-icon">🏖️</span>
                <p>No events scheduled for this day</p>
                <button
                  type="button"
                  className="calendar-btn-empty-add"
                  onClick={() => {
                    setNewEventDate(selectedDate);
                    setShowAddModal(true);
                  }}
                >
                  Schedule an Event
                </button>
              </div>
            ) : (
              selectedDateEvents.map((evt) => {
                const time = evt.start.includes('T')
                  ? evt.start.split('T')[1].slice(0, 5)
                  : 'All day';

                return (
                  <div key={evt.id} className={`calendar-event-card calendar-event-card--${evt.category || 'meeting'}`}>
                    <div className="calendar-event-card__top">
                      <span className="calendar-event-time">⏰ {time}</span>
                      <span className={`calendar-event-badge calendar-event-badge--${evt.category || 'meeting'}`}>
                        {evt.category || 'meeting'}
                      </span>
                    </div>

                    <h4 className="calendar-event-summary">{evt.summary}</h4>

                    {evt.description && (
                      <p className="calendar-event-desc">{evt.description}</p>
                    )}

                    {evt.location && (
                      <div className="calendar-event-location">
                        📍 {evt.location}
                      </div>
                    )}

                    <div className="calendar-event-actions">
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
