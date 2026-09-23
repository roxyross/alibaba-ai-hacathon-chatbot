"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";

interface VoiceRecordingItem {
  id: string;
  user_id?: string;
  title: string;
  transcript: string;
  summary?: string | null;
  language?: string | null;
  audio_url?: string | null;
  duration_seconds?: number | null;
  voice_model?: string | null;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

interface TranscriptEntry {
  role: "user" | "assistant";
  text: string;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function VoicePage() {
  const [activeTab, setActiveTab] = useState<"live" | "library">("live");
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Live voice state
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([
    { role: "assistant", text: "Hello! I am ROXY. Tap the microphone or speak anytime to start our voice session." }
  ]);
  const [liveCaption, setLiveCaption] = useState("");
  const [voiceModel, setVoiceModel] = useState("gemini-3.8-flash");
  const [voiceModulation, setVoiceModulation] = useState("normal");
  const [audioLevels, setAudioLevels] = useState<number[]>([14, 22, 35, 18, 12]);

  // Voice notes library state
  const [recordings, setRecordings] = useState<VoiceRecordingItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Status feedback
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const animIntervalRef = useRef<any>(null);

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

  const fetchRecordings = useCallback(async (query?: string) => {
    if (!accessToken) return;
    setLoadingList(true);
    setErrorBanner(null);
    try {
      const q = query ? `?search=${encodeURIComponent(query)}` : "";
      const res = await fetch(`${API_BASE}/voice/recordings${q}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRecordings(data.recordings || []);
      } else {
        setErrorBanner("Could not sync voice recordings from the server.");
      }
    } catch {
      setErrorBanner("Unable to connect to the voice service. Check backend connection.");
    } finally {
      setLoadingList(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (accessToken && activeTab === "library") {
      void fetchRecordings(searchQuery);
    }
  }, [accessToken, activeTab, searchQuery, fetchRecordings]);

  // Simulated animated audio levels while recording
  useEffect(() => {
    if (isRecording) {
      animIntervalRef.current = setInterval(() => {
        setAudioLevels([
          Math.floor(Math.random() * 28) + 10,
          Math.floor(Math.random() * 38) + 12,
          Math.floor(Math.random() * 45) + 15,
          Math.floor(Math.random() * 32) + 10,
          Math.floor(Math.random() * 24) + 8,
        ]);
      }, 120);
    } else {
      if (animIntervalRef.current) clearInterval(animIntervalRef.current);
      setAudioLevels([14, 22, 35, 18, 12]);
    }
    return () => {
      if (animIntervalRef.current) clearInterval(animIntervalRef.current);
    };
  }, [isRecording]);

  // Toggle Live Speech Recording
  const toggleRecording = () => {
    if (isRecording) {
      // Finish recording turn
      setIsRecording(false);
      setIsProcessing(true);
      const userSpoken = liveCaption.trim() || "What are my upcoming priorities and schedule?";
      setTranscripts((prev) => [...prev, { role: "user", text: userSpoken }]);
      setLiveCaption("");

      // Simulate AI Assistant response
      setTimeout(() => {
        setIsProcessing(false);
        const aiResponse = `I have updated your agenda and synchronized your communications in ${voiceModulation} tone. Everything is on track!`;
        setTranscripts((prev) => [...prev, { role: "assistant", text: aiResponse }]);
        showNotice("Response received from ROXY AI.");
      }, 1100);
    } else {
      setIsRecording(true);
      setLiveCaption("Listening... (tap again to finish speaking)");
    }
  };

  // Save current transcripts as a Voice Note
  const handleSaveAsNote = async () => {
    if (transcripts.length === 0) return;
    if (!accessToken) {
      showNotice("Please sign in to save voice notes.");
      return;
    }

    try {
      const fullTranscript = transcripts
        .map((t) => `${t.role === "user" ? "User" : "ROXY"}: ${t.text}`)
        .join("\n\n");
      const firstUserTurn = transcripts.find((t) => t.role === "user")?.text || "Live Voice Session";
      const title = firstUserTurn.length > 50 ? `${firstUserTurn.slice(0, 50)}...` : firstUserTurn;

      const res = await fetch(`${API_BASE}/voice/recordings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          title,
          transcript: fullTranscript,
          language: "en",
          voice_model: voiceModel,
        }),
      });

      if (res.ok) {
        const d = await res.json();
        setRecordings((prev) => [d.recording, ...prev]);
        showNotice("✅ Saved session to Voice Notes Library!");
      } else {
        throw new Error("Failed to save note");
      }
    } catch {
      showNotice("Failed to save voice note.");
    }
  };

  // Delete recording with optimistic rollback
  const handleDeleteRecording = async (id: string) => {
    if (!accessToken) return;
    const prev = [...recordings];
    setRecordings((curr) => curr.filter((r) => r.id !== id));

    try {
      const res = await fetch(`${API_BASE}/voice/recordings/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error("Server error deleting recording");
      showNotice("🗑️ Voice note removed.");
    } catch {
      setRecordings(prev);
      showNotice("Failed to delete voice note. Changes rolled back.");
    }
  };

  // Speak text using Web Speech API or voice synthesis
  const handleSpeakText = (text: string) => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
      showNotice("🔊 Playing voice note audio...");
    }
  };

  const handleCopyTranscript = (text: string) => {
    if (typeof navigator !== "undefined") {
      navigator.clipboard.writeText(text);
      showNotice("📋 Transcript copied to clipboard.");
    }
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-[#f8faf9]">
      {/* Top Header */}
      <header className="px-6 py-4 bg-white border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700 text-lg font-bold">
            🎙️
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Voice &amp; Audio Intelligence Hub</h1>
            <p className="text-xs text-slate-500">
              {isRecording
                ? "Recording in progress..."
                : `${recordings.length} saved notes · Model: ${voiceModel}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {activeTab === "live" && (
            <button
              onClick={handleSaveAsNote}
              disabled={transcripts.length === 0}
              className="px-3.5 py-1.5 rounded-lg border border-teal-200 bg-teal-50 hover:bg-teal-100 text-teal-800 text-xs font-semibold shadow-sm transition-all disabled:opacity-50"
            >
              💾 Save as Voice Note
            </button>
          )}
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
              onClick={() => void fetchRecordings(searchQuery)}
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
            <span>You are in guest preview mode. Sign in to persist voice notes, extract audio intelligence summaries, and sync memos across devices.</span>
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-200 pb-3">
          <button
            onClick={() => setActiveTab("live")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "live"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            🎙️ Live Voice Session
          </button>
          <button
            onClick={() => {
              setActiveTab("library");
              void fetchRecordings(searchQuery);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "library"
                ? "bg-[#0d9488] text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <span>📁 Voice Notes Library</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200/80 text-slate-700">
              {recordings.length}
            </span>
          </button>
        </div>

        {/* TAB 1: LIVE VOICE SESSION */}
        {activeTab === "live" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Cols: Transcript Dialogue */}
            <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col h-[520px]">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <span className="text-xs font-bold text-slate-800">Session Dialogue</span>
                <button
                  onClick={() => setTranscripts([])}
                  className="text-[11px] text-slate-400 hover:text-slate-600"
                >
                  Clear Dialogue
                </button>
              </div>

              {/* Message scroll list */}
              <div className="flex-1 overflow-y-auto py-3 space-y-3">
                {transcripts.map((entry, idx) => (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-xl text-xs max-w-[85%] ${
                      entry.role === "user"
                        ? "ml-auto bg-teal-50 border border-teal-200 text-teal-900"
                        : "mr-auto bg-slate-50 border border-slate-200 text-slate-800"
                    }`}
                  >
                    <div className="font-bold text-[10px] mb-1 opacity-70">
                      {entry.role === "user" ? "🗣️ You" : "🤖 ROXY AI"}
                    </div>
                    <p className="leading-relaxed whitespace-pre-wrap">{entry.text}</p>
                  </div>
                ))}

                {isProcessing && (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-500 flex items-center gap-2 mr-auto">
                    <span className="w-2 h-2 rounded-full bg-[#0d9488] animate-ping" />
                    <span>Processing audio with multimodal model...</span>
                  </div>
                )}
              </div>

              {/* Spoken preview bar */}
              {isRecording && (
                <div className="pt-2 border-t border-slate-100 flex items-center gap-2 text-xs text-teal-700">
                  <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                  <span className="font-semibold italic">{liveCaption || "Listening..."}</span>
                </div>
              )}
            </div>

            {/* Right Column: Audio Controls & Visualizer */}
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col justify-between space-y-4">
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-slate-900">Audio Configuration</h3>

                {/* Multimodal Model Selector */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">AI Voice Model</label>
                  <select
                    value={voiceModel}
                    onChange={(e) => setVoiceModel(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488] bg-white text-slate-800"
                  >
                    <option value="gemini-3.8-flash">✨ Gemini 3.8 Flash (Multimodal Audio)</option>
                    <option value="gemini-3.7-flash">⚡ Gemini 3.7 Flash</option>
                    <option value="gemini-3.1-flash">⚡ Gemini 3.1 Flash</option>
                    <option value="openai">OpenAI TTS</option>
                  </select>
                </div>

                {/* Steerable Voice Tone Modulation */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Tone &amp; Modulation</label>
                  <select
                    value={voiceModulation}
                    onChange={(e) => setVoiceModulation(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0d9488] bg-white text-slate-800"
                  >
                    <option value="normal">🗣️ Normal Tone</option>
                    <option value="whispering">🤫 Whispering</option>
                    <option value="excited">🤩 Excited</option>
                    <option value="dramatic">🎭 Dramatic</option>
                    <option value="calm">🧘 Calm</option>
                  </select>
                </div>

                {/* Waveform Visualizer */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center space-y-2">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                    Audio Energy
                  </span>
                  <div className="flex items-center justify-center gap-1.5 h-12">
                    {audioLevels.map((lvl, i) => (
                      <span
                        key={i}
                        className={`w-2.5 rounded-full transition-all duration-100 ${
                          isRecording ? "bg-[#0d9488]" : "bg-slate-300"
                        }`}
                        style={{ height: `${lvl}px` }}
                      />
                    ))}
                  </div>
                </div>
              </div>

              {/* Push-to-Talk Action */}
              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={toggleRecording}
                  disabled={isProcessing}
                  className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl mx-auto shadow-md transition-all ${
                    isRecording
                      ? "bg-rose-500 text-white animate-pulse"
                      : "bg-[#0d9488] hover:bg-[#0f766e] text-white"
                  }`}
                  title={isRecording ? "Tap to finish speaking" : "Tap to speak"}
                >
                  {isRecording ? "⏹" : "🎤"}
                </button>
                <p className="text-xs font-semibold text-slate-700 mt-2">
                  {isRecording ? "Tap to send speech" : "Tap microphone to speak"}
                </p>
                <p className="text-[10px] text-slate-400">Push-to-talk voice intelligence active</p>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: VOICE NOTES LIBRARY */}
        {activeTab === "library" && (
          <div className="max-w-4xl space-y-4">
            {/* Search Bar */}
            <div className="flex items-center gap-2">
              <input
                type="search"
                placeholder="Search voice notes by keyword, title, or transcript..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 text-xs px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl focus:outline-none focus:border-[#0d9488] shadow-sm"
              />
              <button
                onClick={() => void fetchRecordings(searchQuery)}
                className="px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-sm"
              >
                🔄 Refresh
              </button>
            </div>

            {loadingList ? (
              <p className="text-xs text-slate-500">Loading voice notes...</p>
            ) : recordings.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
                <div className="text-4xl mb-2">🎙️</div>
                <h3 className="text-sm font-bold text-slate-800">
                  {searchQuery ? "No matching voice notes found" : "No Voice Recordings Yet"}
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  {searchQuery
                    ? `No notes matched "${searchQuery}". Try a different keyword.`
                    : "Your voice library is clean. Record memos in a Live Voice Session or save meetings."}
                </p>
                {!searchQuery && (
                  <button
                    onClick={() => setActiveTab("live")}
                    className="mt-3.5 px-4 py-2 bg-[#0d9488] text-white rounded-lg text-xs font-semibold hover:bg-[#0f766e]"
                  >
                    🎙️ Start Live Voice Session
                  </button>
                )}
              </div>
            ) : (
              <div className="grid gap-3.5">
                {recordings.map((rec) => {
                  const isExpanded = expandedId === rec.id;
                  return (
                    <div
                      key={rec.id}
                      className="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h4 className="text-xs font-bold text-slate-900">{rec.title}</h4>
                          <div className="flex flex-wrap gap-1.5 mt-1.5">
                            {rec.created_at && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600">
                                📅 {new Date(rec.created_at).toLocaleDateString()}
                              </span>
                            )}
                            {rec.duration_seconds && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600">
                                ⏱️ {Math.round(rec.duration_seconds)}s
                              </span>
                            )}
                            {rec.voice_model && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-teal-50 text-teal-700 border border-teal-200">
                                ⚡ {rec.voice_model}
                              </span>
                            )}
                            {rec.tags?.map((t) => (
                              <span key={t} className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700">
                                🏷️ {t}
                              </span>
                            ))}
                          </div>
                        </div>

                        <button
                          onClick={() => void handleDeleteRecording(rec.id)}
                          className="text-xs text-rose-500 hover:text-rose-700 font-semibold"
                          title="Delete voice note"
                        >
                          🗑️
                        </button>
                      </div>

                      {rec.summary && (
                        <div className="p-2.5 bg-teal-50/60 border border-teal-200 rounded-xl text-[11px] text-teal-900">
                          <strong>AI Summary:</strong> {rec.summary}
                        </div>
                      )}

                      <div className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
                        {isExpanded
                          ? rec.transcript
                          : rec.transcript.length > 200
                          ? `${rec.transcript.slice(0, 200)}...`
                          : rec.transcript}
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
                        {rec.transcript.length > 200 ? (
                          <button
                            onClick={() => setExpandedId(isExpanded ? null : rec.id)}
                            className="text-teal-700 font-semibold hover:underline text-[11px]"
                          >
                            {isExpanded ? "Show Less ▲" : "Read Full Transcript ▼"}
                          </button>
                        ) : <div />}

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleCopyTranscript(rec.transcript)}
                            className="px-2.5 py-1 rounded border border-slate-200 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                          >
                            📋 Copy
                          </button>
                          <button
                            onClick={() => handleSpeakText(rec.summary || rec.transcript)}
                            className="px-2.5 py-1 rounded bg-[#0d9488] text-white text-[11px] font-semibold hover:bg-[#0f766e]"
                          >
                            🔊 Read Aloud
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
