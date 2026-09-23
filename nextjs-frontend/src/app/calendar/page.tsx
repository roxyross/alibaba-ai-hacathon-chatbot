"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";

interface CalendarEventItem {
  id: string;
  title: string;
  start_time: string;
  end_time?: string;
  description?: string;
  location?: string;
  category?: "meeting" | "hackathon" | "deadline" | "personal" | "reminder";
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function CalendarPage() {
  const today = useMemo(() => new Date(), []);
  const [currentYear, setCurrentYear] = useState(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState<string>(
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`
  );

  const [events, setEvents] = useState<CalendarEventItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // New Event Modal State
  const [showModal, setShowModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDate, setNewDate] = useState(selectedDate);
  const [newTime, setNewTime] = useState("10:00");
  const [newCategory, setNewCategory] = useState<CalendarEventItem["category"]>("meeting");
  const [newLocation, setNewLocation] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const showNotice = (msg: string) => {
    setNotice(msg);
    setTimeout(() => setNotice((curr) => (curr === msg ? null : curr)), 4000);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const tok = localStorage.getItem("roxy_access_token") || localStorage.getItem("access_token");
      setAccessToken(tok);
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setErrorBanner(null);
    try {
      const res = await fetch(`${API_BASE}/calendar/events`, {
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (res.ok) {
        const data = await res.json();
        setEvents(data.events || []);
      } else {
        setErrorBanner("Failed to retrieve calendar schedule from the server.");
      }
    } catch {
      setErrorBanner("Could not connect to the Calendar service.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (accessToken) {
      fetchEvents();
    }
  }, [accessToken, fetchEvents]);

  // Month grid calculations
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
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    setSelectedDate(dateStr);
    setNewDate(dateStr);
  };

  const selectedDateEvents = useMemo(() => {
    return events.filter((e) => e.start_time.startsWith(selectedDate));
  }, [events, selectedDate]);

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    if (!accessToken) {
      showNotice("Please sign in to schedule events.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/calendar/events`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          title: newTitle.trim(),
          start_time: `${newDate}T${newTime}:00`,
          category: newCategory,
          location: newLocation.trim() || undefined,
          description: newDesc.trim() || undefined,
        }),
      });

      if (res.ok) {
        await fetchEvents();
        setShowModal(false);
        setNewTitle("");
        setNewLocation("");
        setNewDesc("");
        showNotice(`Event "${newTitle}" created successfully.`);
      } else {
        const err = await res.json().catch(() => ({}));
        showNotice(err.detail || "Failed to create event.");
      }
    } catch {
      showNotice("Network error creating event.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteEvent = async (id: string) => {
    if (!accessToken) return;
    const prev = [...events];
    setEvents((curr) => curr.filter((e) => e.id !== id));

    try {
      const res = await fetch(`${API_BASE}/calendar/events/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        setEvents(prev);
        showNotice("Failed to delete event.");
      } else {
        showNotice("Event deleted.");
      }
    } catch {
      setEvents(prev);
      showNotice("Network error deleting event.");
    }
  };

  const handleExportIcs = async () => {
    if (!accessToken) {
      showNotice("Please sign in to export calendar (.ics).");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/calendar/export/ics`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "roxy_calendar.ics";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showNotice("Calendar exported as roxy_calendar.ics");
      }
    } catch {
      showNotice("Error exporting .ics file.");
    }
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-[#f8faf9]">
      {/* Top Header */}
      <header className="px-6 py-4 bg-white border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 text-lg font-bold">
            📅
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Calendar &amp; Schedule</h1>
            <p className="text-xs text-slate-500">
              {loading ? "Syncing schedule..." : `${events.length} total events scheduled`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleExportIcs}
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 transition-all"
          >
            📥 Export .ics
          </button>
          <button
            onClick={handleToday}
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 transition-all"
          >
            Today
          </button>
          <button
            onClick={() => {
              setNewDate(selectedDate);
              setShowModal(true);
            }}
            className="px-3.5 py-1.5 rounded-lg bg-[#0d9488] hover:bg-[#0f766e] text-white text-xs font-semibold shadow-sm transition-all"
          >
            + Add Event
          </button>
        </div>
      </header>

      {/* Main Body */}
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Notice Toast */}
        {notice && (
          <div className="p-3 bg-teal-50 border border-teal-200 text-teal-800 rounded-xl text-xs flex items-center justify-between">
            <span>✨ {notice}</span>
            <button onClick={() => setNotice(null)} className="text-teal-600 font-bold hover:text-teal-900">✕</button>
          </div>
        )}

        {/* Error Banner */}
        {errorBanner && (
          <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center justify-between">
            <span>⚠️ {errorBanner}</span>
            <button
              onClick={fetchEvents}
              className="px-2 py-1 bg-rose-600 text-white rounded text-[11px] font-semibold hover:bg-rose-700"
            >
              Retry
            </button>
          </div>
        )}

        {/* Guest Banner */}
        {!accessToken && (
          <div className="p-3 bg-slate-100 border border-slate-200 text-slate-700 rounded-xl text-xs flex items-center gap-2">
            <span>🔒</span>
            <span>You are in guest preview mode. Sign in to schedule and persist calendar events across devices.</span>
          </div>
        )}

        {/* 2-Column Calendar Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Cols: Monthly Calendar Grid */}
          <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
            {/* Month Navigation */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h2 className="text-base font-bold text-slate-800">
                {MONTH_NAMES[currentMonth]} {currentYear}
              </h2>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handlePrevMonth}
                  className="w-7 h-7 rounded-lg border border-slate-200 flex items-center justify-center text-xs text-slate-600 hover:bg-slate-50 font-bold"
                >
                  ‹
                </button>
                <button
                  onClick={handleNextMonth}
                  className="w-7 h-7 rounded-lg border border-slate-200 flex items-center justify-center text-xs text-slate-600 hover:bg-slate-50 font-bold"
                >
                  ›
                </button>
              </div>
            </div>

            {/* Days of Week Header */}
            <div className="grid grid-cols-7 gap-1 text-center">
              {DAY_NAMES.map((d) => (
                <div key={d} className="text-[11px] font-bold text-slate-400 py-1">
                  {d}
                </div>
              ))}
            </div>

            {/* Month Days Grid */}
            <div className="grid grid-cols-7 gap-1.5">
              {/* Previous month filler days */}
              {Array.from({ length: firstDayIndex }).map((_, i) => {
                const dayNum = prevMonthDays - firstDayIndex + i + 1;
                return (
                  <div
                    key={`prev-${i}`}
                    className="h-16 rounded-xl border border-dashed border-slate-100 p-1.5 text-slate-300 text-xs opacity-50"
                  >
                    <span>{dayNum}</span>
                  </div>
                );
              })}

              {/* Current month days */}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const dayNum = i + 1;
                const dateKey = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`;
                const isSelected = selectedDate === dateKey;
                const isToday =
                  today.getFullYear() === currentYear &&
                  today.getMonth() === currentMonth &&
                  today.getDate() === dayNum;
                const dayEvents = events.filter((e) => e.start_time.startsWith(dateKey));

                return (
                  <div
                    key={`day-${dayNum}`}
                    onClick={() => setSelectedDate(dateKey)}
                    className={`h-16 rounded-xl border p-1.5 text-xs transition-all cursor-pointer flex flex-col justify-between ${
                      isSelected
                        ? "border-[#0d9488] bg-teal-50/40 shadow-sm ring-1 ring-[#0d9488]"
                        : isToday
                        ? "border-teal-300 bg-white"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`font-semibold ${isSelected ? "text-[#0d9488]" : isToday ? "text-[#0d9488] font-bold" : "text-slate-700"}`}>
                        {dayNum}
                      </span>
                      {isToday && (
                        <span className="w-1.5 h-1.5 rounded-full bg-[#0d9488]" />
                      )}
                    </div>
                    {dayEvents.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-teal-100 text-teal-800">
                          {dayEvents.length} {dayEvents.length === 1 ? "event" : "events"}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Selected Date Agenda */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-800">Agenda</h3>
                <p className="text-xs text-slate-400 mt-0.5">{selectedDate}</p>
              </div>
              <button
                onClick={() => {
                  setNewDate(selectedDate);
                  setShowModal(true);
                }}
                className="text-xs text-[#0d9488] font-semibold hover:underline"
              >
                + Add
              </button>
            </div>

            <div className="flex-1 overflow-y-auto pt-3 space-y-2.5">
              {selectedDateEvents.length === 0 ? (
                <div className="text-center py-14">
                  <div className="text-3xl mb-2">☕</div>
                  <p className="text-xs font-semibold text-slate-700">No events on this day</p>
                  <p className="text-[11px] text-slate-400 mt-1">Enjoy free focus time or add an agenda item</p>
                </div>
              ) : (
                selectedDateEvents.map((evt) => (
                  <div
                    key={evt.id}
                    className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-slate-50 transition-all space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800">{evt.title}</span>
                      <button
                        onClick={() => handleDeleteEvent(evt.id)}
                        className="text-slate-400 hover:text-rose-600 text-xs"
                        title="Delete event"
                      >
                        🗑️
                      </button>
                    </div>
                    {evt.description && (
                      <p className="text-[11px] text-slate-500 leading-relaxed">{evt.description}</p>
                    )}
                    <div className="flex items-center gap-2 pt-1 text-[10px] text-slate-400">
                      <span>⏰ {evt.start_time.split("T")[1]?.slice(0, 5) || "All day"}</span>
                      {evt.location && <span>📍 {evt.location}</span>}
                      {evt.category && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 font-semibold uppercase tracking-wider">
                          {evt.category}
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </main>

      {/* New Event Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900">Schedule New Event</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700 text-sm font-bold">
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateEvent} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Event Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Sprint Sync with Engineering"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Date</label>
                  <input
                    type="date"
                    value={newDate}
                    onChange={(e) => setNewDate(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Time</label>
                  <input
                    type="time"
                    value={newTime}
                    onChange={(e) => setNewTime(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value as any)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                  >
                    <option value="meeting">Meeting</option>
                    <option value="hackathon">Hackathon</option>
                    <option value="deadline">Deadline</option>
                    <option value="personal">Personal</option>
                    <option value="reminder">Reminder</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Location / Link</label>
                  <input
                    type="text"
                    placeholder="e.g. Zoom or Office"
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  rows={3}
                  placeholder="Optional agenda notes or details..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488]"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !newTitle.trim()}
                  className="px-4 py-1.5 rounded-lg bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-40 text-white text-xs font-semibold shadow-sm transition-all"
                >
                  {isSubmitting ? "Creating..." : "Save Event"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
