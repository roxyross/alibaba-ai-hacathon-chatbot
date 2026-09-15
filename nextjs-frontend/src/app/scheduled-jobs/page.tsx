"use client";

import React, { useState } from "react";

interface ScheduledJob {
  id: string;
  name: string;
  description: string;
  schedule: string;
  timezone: string;
  status: "Active" | "Paused";
  nextRun: string;
}

export default function ScheduledJobsPage() {
  const [jobs, setJobs] = useState<ScheduledJob[]>([
    {
      id: "1",
      name: "Daily Market Briefing & Portfolio Valuation",
      description: "Aggregates morning equity indices, currency rates, and Raast transaction reconciliations into a summary report.",
      schedule: "Every day at 09:00 AM",
      timezone: "Asia/Karachi (PKT)",
      status: "Active",
      nextRun: "Tomorrow at 09:00 AM"
    },
    {
      id: "2",
      name: "Weekly Knowledge Vault Digest",
      description: "Indexes newly committed documents and sends a recap of key architectural takeaways to the primary channel.",
      schedule: "Every Monday at 08:00 AM",
      timezone: "UTC",
      status: "Active",
      nextRun: "Monday at 08:00 AM"
    },
    {
      id: "3",
      name: "Invoice & Stripe Account Settlement Check",
      description: "Polls active subscriptions, alerts on failed renewals or overdue invoices, and syncs credit balances.",
      schedule: "Every 1st of month",
      timezone: "America/New_York (EST)",
      status: "Paused",
      nextRun: "Paused"
    }
  ]);

  const [inputPrompt, setInputPrompt] = useState("");
  const [selectedTimezone, setSelectedTimezone] = useState("Asia/Karachi (PKT)");
  const [isListening, setIsListening] = useState(false);
  const [plusMenuOpen, setPlusMenuOpen] = useState(false);

  const toggleVoice = () => {
    const SpeechRec = (typeof window !== "undefined" && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));

    if (!SpeechRec) {
      alert("Speech recognition is not supported in this browser.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRec();
      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (e: any) => {
        const text = e.results[0][0].transcript;
        setInputPrompt(prev => prev ? `${prev} ${text}` : text);
      };
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleCreateJob = () => {
    if (!inputPrompt.trim()) return;

    const newJob: ScheduledJob = {
      id: Date.now().toString(),
      name: inputPrompt.slice(0, 45) + (inputPrompt.length > 45 ? "..." : ""),
      description: inputPrompt,
      schedule: "Custom automated trigger",
      timezone: selectedTimezone,
      status: "Active",
      nextRun: "Calculated in background"
    };

    setJobs(prev => [newJob, ...prev]);
    setInputPrompt("");
  };

  const toggleStatus = (id: string) => {
    setJobs(prev =>
      prev.map(j => {
        if (j.id === id) {
          const next = j.status === "Active" ? "Paused" : "Active";
          return { ...j, status: next, nextRun: next === "Active" ? "Upcoming" : "Paused" };
        }
        return j;
      })
    );
  };

  const deleteJob = (id: string) => {
    setJobs(prev => prev.filter(j => j.id !== id));
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold text-[#1e292b]">Scheduled</h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
              Active
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Automate recurring reasoning tasks, data syncs, and alert webhooks in any timezone using voice or text prompts.
          </p>
        </div>

        {/* Timezone selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-medium">Timezone:</span>
          <select
            value={selectedTimezone}
            onChange={(e) => setSelectedTimezone(e.target.value)}
            className="bg-white border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:border-[#0d9488]"
          >
            <option value="Asia/Karachi (PKT)">Asia/Karachi (PKT, UTC+5)</option>
            <option value="UTC">Universal (UTC)</option>
            <option value="America/New_York (EST)">America/New_York (EST)</option>
            <option value="Europe/London (GMT)">Europe/London (GMT)</option>
            <option value="Asia/Dubai (GST)">Asia/Dubai (GST, UTC+4)</option>
          </select>
        </div>
      </div>

      {/* Natural Language Creation Input Bar */}
      <div className="bg-white rounded-2xl border border-slate-200 p-3 shadow-sm space-y-2">
        <div className="relative flex items-center bg-slate-50 border border-slate-200 rounded-xl focus-within:border-[#0d9488] focus-within:bg-white transition-all">
          {/* Plus Menu */}
          <div className="relative pl-2">
            <button
              type="button"
              onClick={() => setPlusMenuOpen(!plusMenuOpen)}
              className="w-8 h-8 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 flex items-center justify-center text-lg transition-colors"
            >
              +
            </button>
            {plusMenuOpen && (
              <div className="absolute bottom-11 left-0 w-60 bg-white rounded-xl shadow-xl border border-slate-200 p-2 z-50">
                <button
                  onClick={() => {
                    setPlusMenuOpen(false);
                    setInputPrompt("Send me daily morning market news and forex rates at 8:30 AM");
                  }}
                  className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg"
                >
                  📅 Preset: Morning Forex & News
                </button>
                <button
                  onClick={() => {
                    setPlusMenuOpen(false);
                    setInputPrompt("Reconcile Raast PISP and Plaid balance changes every 6 hours");
                  }}
                  className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg"
                >
                  💳 Preset: Finance Reconciliation
                </button>
              </div>
            )}
          </div>

          <input
            type="text"
            placeholder="Schedule via voice or prompt (e.g. 'Summarize top issues every Friday at 5 PM')..."
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleCreateJob();
              }
            }}
            className="flex-1 py-3 px-3 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:outline-none bg-transparent"
          />

          <div className="flex items-center gap-1.5 pr-2.5">
            <button
              type="button"
              onClick={toggleVoice}
              className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm transition-colors ${
                isListening
                  ? "bg-rose-50 text-rose-600 animate-pulse"
                  : "text-slate-400 hover:text-slate-700 hover:bg-slate-200/60"
              }`}
              title="Voice scheduling"
            >
              🎙️
            </button>
            <button
              type="button"
              onClick={handleCreateJob}
              disabled={!inputPrompt.trim()}
              className="w-8 h-8 rounded-full bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-40 text-white flex items-center justify-center text-sm shadow-sm transition-all"
            >
              ↑
            </button>
          </div>
        </div>
      </div>

      {/* Horizontal Job Rows */}
      <div className="space-y-3">
        {jobs.map((job) => (
          <div
            key={job.id}
            className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4"
          >
            {/* Left Details */}
            <div className="space-y-1 sm:max-w-xl">
              <div className="flex items-center gap-2">
                <span className="text-base">⏰</span>
                <h3 className="text-sm font-bold text-[#1e292b]">{job.name}</h3>
                <span
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${
                    job.status === "Active"
                      ? "bg-teal-50 text-[#0d9488] border-teal-200"
                      : "bg-slate-100 text-slate-500 border-slate-200"
                  }`}
                >
                  {job.status}
                </span>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">{job.description}</p>
              <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] text-slate-400">
                <span>🗓️ {job.schedule}</span>
                <span>·</span>
                <span>🌐 {job.timezone}</span>
                <span>·</span>
                <span>⏳ Next: {job.nextRun}</span>
              </div>
            </div>

            {/* Action Buttons: Active | Pause | Delete */}
            <div className="flex items-center gap-2 self-end sm:self-center">
              <button
                onClick={() => toggleStatus(job.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
                  job.status === "Active"
                    ? "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"
                    : "bg-teal-50 text-[#0d9488] border-teal-200 hover:bg-teal-100"
                }`}
              >
                {job.status === "Active" ? "Pause" : "Resume"}
              </button>
              <button
                onClick={() => deleteJob(job.id)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-600 bg-rose-50 border border-rose-200 hover:bg-rose-100 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
