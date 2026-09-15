import React, { useState, useRef } from 'react';
import './ScheduledJobsView.css';

interface ScheduledJobItem {
  id: string;
  name: string;
  description: string;
  schedule: string;
  timezone: string;
  status: 'Active' | 'Pause';
}

interface ScheduledJobsViewProps {
  accessToken: string | null;
  onBack: () => void;
  onNavigateView?: (view: string) => void;
}

export const ScheduledJobsView: React.FC<ScheduledJobsViewProps> = ({
  accessToken: _accessToken,
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

  const [jobs, setJobs] = useState<ScheduledJobItem[]>([
    {
      id: 'job-1',
      name: 'Daily Market & Portfolio Summary',
      description: 'Scrapes market closing indices, summarizes portfolio shifts, and delivers briefing at 09:00 AM.',
      schedule: 'Every day at 09:00 AM',
      timezone: 'Asia/Karachi (PKT, UTC+5)',
      status: 'Active',
    },
    {
      id: 'job-2',
      name: 'Weekly Cloud & Subscription Expense Audit',
      description: 'Queries Plaid and Raast accounts for recurring billing anomalies and posts audit alert.',
      schedule: 'Every Monday at 10:00 AM',
      timezone: 'UTC',
      status: 'Active',
    },
    {
      id: 'job-3',
      name: 'Nightly Git Repo Sync & Backup',
      description: 'Automated snapshot of active repositories to private backup storage.',
      schedule: 'Every day at 02:00 AM',
      timezone: 'America/New_York (EST, UTC-5)',
      status: 'Pause',
    },
  ]);

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

  const handleSend = () => {
    if (!promptText.trim()) return;
    const userPrompt = promptText.trim();
    setChatMessages((prev) => [...prev, { sender: 'user', text: userPrompt }]);
    setPromptText('');

    setTimeout(() => {
      const newJob: ScheduledJobItem = {
        id: `job-${Date.now()}`,
        name: userPrompt.length > 35 ? `${userPrompt.slice(0, 35)}...` : userPrompt,
        description: `Automated scheduled action configured via prompt: "${userPrompt}". Model: ${selectedModel}`,
        schedule: 'Every day at 08:00 AM',
        timezone: selectedTimezone,
        status: 'Active',
      };
      setJobs((prev) => [newJob, ...prev]);

      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: `✅ Scheduled task created: **"${newJob.name}"** running on schedule (${selectedTimezone}). Added to your active jobs below.`,
        },
      ]);
    }, 700);
  };

  const toggleJobStatus = (id: string) => {
    setJobs((prev) =>
      prev.map((j) => (j.id === id ? { ...j, status: j.status === 'Active' ? 'Pause' : 'Active' } : j))
    );
  };

  const deleteJob = (id: string) => {
    if (confirm('Are you sure you want to delete this scheduled job?')) {
      setJobs((prev) => prev.filter((j) => j.id !== id));
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
          {/* Top left title */}
          <h1 className="sched-view__title">Scheduled</h1>
        </div>
        {/* Top right status badge: Active (soft teal pill) */}
        <span className="sched-view__status-pill">Active</span>
      </header>

      <div className="sched-view__body">
        {/* Description */}
        <p className="sched-view__desc">
          Ask Roxy-AI to schedule tasks, set reminders, or monitor for updates.
        </p>

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
              placeholder="Schedule a task"
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
                    <span>🕒 {job.schedule}</span>
                    <span>•</span>
                    <span>🌐 {job.timezone}</span>
                  </div>
                </div>

                {/* Buttons: Active | Pause | Delete */}
                <div className="sched-job-row__actions">
                  <button
                    type="button"
                    className={`job-btn ${job.status === 'Active' ? 'job-btn--active' : 'job-btn--pause'}`}
                    onClick={() => toggleJobStatus(job.id)}
                  >
                    {job.status === 'Active' ? 'Active' : 'Pause'}
                  </button>
                  <button
                    type="button"
                    className="job-btn job-btn--toggle"
                    onClick={() => toggleJobStatus(job.id)}
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
        </div>
      </div>
    </div>
  );
};
