"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

interface MediaItem {
  id: string;
  url: string;
  prompt: string;
  aspectRatio: string;
  type: "image" | "video";
  timestamp: string;
  is_favorite?: boolean;
  style_preset?: string;
  vault_document_id?: string;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function ImageStudioPage() {
  const [sidebarTab, setSidebarTab] = useState<"generations" | "uploads">("generations");
  const [mediaType, setMediaType] = useState<"image" | "video">("image");
  const [prompt, setPrompt] = useState("");
  const [speedQuality, setSpeedQuality] = useState("Balanced");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [plusMenuOpen, setPlusMenuOpen] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [generations, setGenerations] = useState<MediaItem[]>([]);
  const [uploads, setUploads] = useState<MediaItem[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const fetchGenerations = useCallback(async () => {
    if (!accessToken) return;
    try {
      setErrorBanner(null);
      const res = await fetch(`${API_BASE}/images/generations`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const mapped: MediaItem[] = (data.generations || []).map((g: any) => ({
          id: g.id,
          url: g.media_url,
          prompt: g.prompt,
          aspectRatio: g.aspect_ratio || "1:1",
          type: g.media_type || "image",
          timestamp: g.created_at ? new Date(g.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recently",
          is_favorite: Boolean(g.is_favorite),
          style_preset: g.style_preset,
          vault_document_id: g.vault_document_id,
        }));
        setGenerations(mapped);
      } else {
        setErrorBanner("Failed to retrieve image gallery from the server.");
      }
    } catch {
      setErrorBanner("Could not connect to Image Studio server.");
    }
  }, [accessToken]);

  const fetchUploads = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/images/uploads`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const mapped: MediaItem[] = (data.uploads || []).map((u: any) => ({
          id: u.id,
          url: u.media_url,
          prompt: u.filename,
          aspectRatio: "Original",
          type: u.media_type || "image",
          timestamp: u.created_at ? new Date(u.created_at).toLocaleDateString() : "Recently",
        }));
        setUploads(mapped);
      }
    } catch {
      // offline error handled gracefully
    }
  }, [accessToken]);

  useEffect(() => {
    if (accessToken) {
      fetchGenerations();
      fetchUploads();
    }
  }, [accessToken, fetchGenerations, fetchUploads]);

  const handleGenerate = async () => {
    if (!prompt.trim() || isGenerating) return;
    if (!accessToken) {
      showNotice("Please sign in to generate and save artwork.");
      return;
    }
    setIsGenerating(true);
    setErrorBanner(null);

    try {
      const res = await fetch(`${API_BASE}/images/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          prompt: prompt.trim(),
          media_type: mediaType,
          aspect_ratio: aspectRatio,
          speed: speedQuality,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const g = data.generation;
        const newItem: MediaItem = {
          id: g.id,
          url: g.media_url,
          prompt: g.prompt,
          aspectRatio: g.aspect_ratio || aspectRatio,
          type: g.media_type || mediaType,
          timestamp: "Just now",
          is_favorite: false,
          style_preset: g.style_preset,
        };
        setGenerations((prev) => [newItem, ...prev]);
        setPrompt("");
        showNotice("Artwork synthesized successfully!");
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorBanner(err.detail || "Image generation failed. Please try again.");
      }
    } catch {
      setErrorBanner("Network error during image synthesis.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!accessToken) {
      showNotice("Please sign in to upload reference assets.");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/images/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      });

      if (res.ok) {
        await fetchUploads();
        setSidebarTab("uploads");
        showNotice(`Uploaded "${file.name}" successfully.`);
      } else {
        showNotice("Failed to upload reference media.");
      }
    } catch {
      showNotice("Network error during upload.");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const toggleVoiceInput = () => {
    const SpeechRec = (typeof window !== "undefined" && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));

    if (!SpeechRec) {
      showNotice("Speech recognition is not supported in this browser.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRec();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (e: any) => {
        const text = e.results[0][0].transcript;
        setPrompt((prev) => (prev ? `${prev} ${text}` : text));
      };
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  return (
    <div className="flex-1 flex h-[calc(100vh-4rem)] overflow-hidden bg-[#f8faf9]">
      {/* Left Sidebar */}
      <aside className="w-64 border-r border-slate-200 bg-white/70 backdrop-blur-sm flex flex-col">
        <div className="p-3 border-b border-slate-100 flex items-center justify-between">
          <div className="flex bg-slate-100 p-1 rounded-lg w-full">
            <button
              onClick={() => setSidebarTab("generations")}
              className={`flex-1 py-1 text-xs font-semibold rounded-md transition-all ${
                sidebarTab === "generations"
                  ? "bg-white text-[#1e292b] shadow-sm"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              Generations ({generations.length})
            </button>
            <button
              onClick={() => setSidebarTab("uploads")}
              className={`flex-1 py-1 text-xs font-semibold rounded-md transition-all ${
                sidebarTab === "uploads"
                  ? "bg-white text-[#1e292b] shadow-sm"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              Uploads ({uploads.length})
            </button>
          </div>
        </div>

        {/* Action Button in sidebar */}
        <div className="p-3 border-b border-slate-100">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="w-full py-2 px-3 rounded-lg text-xs font-semibold bg-black text-white hover:bg-slate-800 flex items-center justify-center gap-1.5 shadow-sm transition-all"
          >
            <span>+</span>
            <span>Upload Reference</span>
          </button>
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: "none" }}
            accept="image/*,video/*"
            onChange={handleFileUpload}
          />
        </div>

        {/* List of generated or uploaded thumbnails */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
          {sidebarTab === "generations" ? (
            generations.length === 0 ? (
              <div className="text-center py-10 px-4">
                <div className="text-3xl mb-2 text-slate-300">🎨</div>
                <p className="text-xs font-semibold text-slate-700">No artwork yet</p>
                <p className="text-[11px] text-slate-400 mt-1">Synthesize an image below to populate your gallery</p>
              </div>
            ) : (
              generations.map((item) => (
                <div
                  key={item.id}
                  className="group relative rounded-lg overflow-hidden border border-slate-200 bg-white hover:border-[#0d9488] transition-all cursor-pointer"
                >
                  <img src={item.url} alt={item.prompt} className="w-full h-24 object-cover" />
                  <div className="p-2">
                    <p className="text-[11px] font-medium text-slate-700 truncate">{item.prompt}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{item.aspectRatio} · {item.timestamp}</p>
                  </div>
                </div>
              ))
            )
          ) : uploads.length === 0 ? (
            <div className="text-center py-10 px-4">
              <div className="text-3xl mb-2 text-slate-300">📁</div>
              <p className="text-xs font-semibold text-slate-700">No media uploaded</p>
              <p className="text-[11px] text-slate-400 mt-1">Upload reference images to augment your prompts</p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="mt-3 text-xs text-[#0d9488] font-semibold hover:underline"
              >
                Upload now
              </button>
            </div>
          ) : (
            uploads.map((item) => (
              <div
                key={item.id}
                className="group relative rounded-lg overflow-hidden border border-slate-200 bg-white hover:border-[#0d9488] transition-all"
              >
                <img src={item.url} alt={item.prompt} className="w-full h-24 object-cover" />
                <div className="p-2">
                  <p className="text-[11px] font-medium text-slate-700 truncate">{item.prompt}</p>
                  <p className="text-[10px] text-slate-400">{item.timestamp}</p>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main Studio Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Gallery / Workspace */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8">
          <div className="max-w-5xl mx-auto space-y-6">
            {/* Notification Toast */}
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
                  onClick={() => {
                    fetchGenerations();
                    fetchUploads();
                  }}
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
                <span>You are in guest preview mode. Sign in to synthesize and save artwork permanently to your gallery.</span>
              </div>
            )}

            <div className="text-center sm:text-left">
              <h1 className="text-2xl sm:text-3xl font-bold text-[#1e292b] tracking-tight">
                What should we imagine?
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1">
                Generate hyper-detailed visuals or cinematic motion clips with Gemini Omni & FLUX.
              </p>
            </div>

            {/* Generated Items Grid */}
            {generations.length === 0 ? (
              <div className="text-center py-20 bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
                <div className="text-4xl mb-3">🎨</div>
                <h3 className="text-base font-semibold text-slate-800">Your neural gallery is empty</h3>
                <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                  Describe any scene or creative concept in the prompt bar below to synthesize high-resolution artwork.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4">
                {generations.map((item) => (
                  <div
                    key={item.id}
                    className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col group"
                  >
                    <div className="relative aspect-video bg-slate-100 overflow-hidden">
                      <img
                        src={item.url}
                        alt={item.prompt}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                      <div className="absolute top-2.5 right-2.5 bg-black/60 backdrop-blur-md px-2 py-0.5 rounded text-[10px] text-white font-medium">
                        {item.aspectRatio}
                      </div>
                    </div>
                    <div className="p-4 flex-1 flex flex-col justify-between">
                      <div>
                        <p className="text-xs text-slate-800 leading-relaxed font-medium">
                          &quot;{item.prompt}&quot;
                        </p>
                      </div>
                      <div className="flex items-center justify-between pt-3 mt-3 border-t border-slate-100 text-[11px] text-slate-400">
                        <span>{item.timestamp}</span>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[#0d9488] font-semibold hover:underline flex items-center gap-1"
                        >
                          <span>High-Res</span>
                          <span>↗</span>
                        </a>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Prompt Input Section */}
        <div className="border-t border-slate-200 bg-white/90 backdrop-blur-md p-4">
          <div className="max-w-4xl mx-auto space-y-3">
            {/* Control Bar: Media Type, Aspect Ratio, Speed/Quality */}
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2">
                {/* Image / Video toggle */}
                <div className="inline-flex p-0.5 bg-slate-100 rounded-lg border border-slate-200">
                  <button
                    type="button"
                    onClick={() => setMediaType("image")}
                    className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                      mediaType === "image"
                        ? "bg-white text-[#1e292b] shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    Image
                  </button>
                  <button
                    type="button"
                    onClick={() => setMediaType("video")}
                    className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                      mediaType === "video"
                        ? "bg-white text-[#1e292b] shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    Video
                  </button>
                </div>

                {/* Aspect Ratio Selector */}
                <select
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs text-slate-800 focus:outline-none focus:border-[#0d9488]"
                >
                  <option value="16:9">16:9 Landscape</option>
                  <option value="1:1">1:1 Square</option>
                  <option value="9:16">9:16 Portrait</option>
                  <option value="4:3">4:3 Standard</option>
                </select>

                {/* Speed / Quality */}
                <select
                  value={speedQuality}
                  onChange={(e) => setSpeedQuality(e.target.value)}
                  className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs text-slate-800 focus:outline-none focus:border-[#0d9488]"
                >
                  <option value="Turbo">Turbo (Fastest)</option>
                  <option value="Balanced">Balanced</option>
                  <option value="Ultra-HQ">Ultra-HQ (High Quality)</option>
                </select>
              </div>

              <span className="text-[11px] text-slate-400">
                1 Credit per render · High-res neural synthesis
              </span>
            </div>

            {/* Input Bar */}
            <div className="relative flex items-center bg-white border border-slate-200 rounded-xl shadow-sm focus-within:border-[#0d9488] focus-within:ring-1 focus-within:ring-[#0d9488] transition-all">
              {/* Plus Menu */}
              <div className="relative pl-2">
                <button
                  type="button"
                  onClick={() => setPlusMenuOpen(!plusMenuOpen)}
                  className="w-8 h-8 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 flex items-center justify-center text-lg transition-colors"
                >
                  +
                </button>
                {plusMenuOpen && (
                  <div className="absolute bottom-11 left-0 w-52 bg-white rounded-xl shadow-xl border border-slate-200 p-2 z-50">
                    <button
                      onClick={() => {
                        setPlusMenuOpen(false);
                        fileInputRef.current?.click();
                      }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2"
                    >
                      <span>📎</span>
                      <span>Attach Reference</span>
                    </button>
                    <button
                      onClick={() => {
                        setPlusMenuOpen(false);
                        setPrompt("Architectural photo of modernist glass villa cantilevered over ocean cliff, sunset lighting, realistic details");
                      }}
                      className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2"
                    >
                      <span>💡</span>
                      <span>Insert Preset Prompt</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Input text */}
              <input
                type="text"
                placeholder="Describe your scene, lighting, style, composition..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleGenerate();
                  }
                }}
                className="flex-1 py-3 px-3 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:outline-none bg-transparent"
              />

              {/* Mic & Circular Soft Teal Send Button */}
              <div className="flex items-center gap-1.5 pr-2.5">
                <button
                  type="button"
                  onClick={toggleVoiceInput}
                  className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm transition-colors ${
                    isListening
                      ? "bg-rose-50 text-rose-600 animate-pulse"
                      : "text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                  }`}
                  title="Voice input"
                >
                  🎙️
                </button>
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={!prompt.trim() || isGenerating}
                  className="w-8 h-8 rounded-full bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-40 disabled:hover:bg-[#0d9488] text-white flex items-center justify-center text-sm shadow-sm transition-all"
                >
                  {isGenerating ? "⏳" : "↑"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
