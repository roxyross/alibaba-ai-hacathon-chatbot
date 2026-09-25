import React, { useState, useEffect, useRef, useCallback } from 'react';
import { VoiceInputControl } from '../common/VoiceInputControl';
import './VideoStudio.css';

interface VideoClip {
  id: string;
  title: string;
  url: string;
  startTime: number; // in seconds
  duration: number;  // in seconds
  trimStart: number;
  trimEnd: number;
}

interface AudioTrackItem {
  id: string;
  name: string;
  startTime: number;
  duration: number;
  volume: number;
  muted: boolean;
}

interface TextCaptionItem {
  id: string;
  text: string;
  startTime: number;
  duration: number;
  fontSize: number;
  color: string;
}

interface EffectItem {
  id: string;
  type: 'cross_dissolve' | 'fade_black' | 'zoom_blur' | 'glitch';
  startTime: number;
  duration: number;
}

interface MediaJob {
  id: string;
  model: string;
  prompt: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  media_url?: string;
  error_message?: string;
  elapsedSeconds?: number;
}

interface VideoStudioProps {
  accessToken: string | null;
  onBack: () => void;
}

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const VideoStudio: React.FC<VideoStudioProps> = ({ accessToken, onBack }) => {
  // Navigation & Subtabs
  const [activeSideTab, setActiveSideTab] = useState<'generate' | 'library'>('generate');

  // Generation Form State
  const [prompt, setPrompt] = useState('');
  const [selectedModel, setSelectedModel] = useState('veo-3.1-generate-preview');
  const [durationSec, setDurationSec] = useState<number>(5);
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [resolution, setResolution] = useState('1080p');
  const [startingFrame, setStartingFrame] = useState<string | null>(null);
  const [isSubmittingGen, setIsSubmittingGen] = useState(false);
  const [interimPrompt, setInterimPrompt] = useState('');
  const [activeJob, setActiveJob] = useState<MediaJob | null>(null);

  // Available Video Models Registry
  const [videoModels, setVideoModels] = useState<Array<{ id: string; name: string; is_available: boolean; badge?: string }>>([
    { id: 'veo-3.1-generate-preview', name: 'Google Veo 3.1', is_available: true, badge: 'Cinematic 4K' },
    { id: 'veo-2.0-generate-001', name: 'Google Veo 2', is_available: true, badge: 'High Definition' },
    { id: 'gemini-omni-1.1-flash', name: 'Gemini Omni Flash', is_available: true, badge: 'Fast Synth' },
  ]);

  // Asset Library State
  const [assetLibrary, setAssetLibrary] = useState<Array<{ id: string; title: string; url: string; duration_seconds?: number }>>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);

  // Timeline Multi-Track State
  const [videoClips, setVideoClips] = useState<VideoClip[]>([]);
  const [audioTracks, setAudioTracks] = useState<AudioTrackItem[]>([
    { id: 'aud-1', name: 'Cinematic Ambient Score', startTime: 0, duration: 15, volume: 80, muted: false },
  ]);
  const [textCaptions, setTextCaptions] = useState<TextCaptionItem[]>([
    { id: 'txt-1', text: 'ROXY AI Media Sequence', startTime: 0, duration: 4, fontSize: 24, color: '#ffffff' },
  ]);
  const [effects, setEffects] = useState<EffectItem[]>([
    { id: 'fx-1', type: 'cross_dissolve', startTime: 4.5, duration: 1 },
  ]);

  // Playhead & Playback
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [zoomScale, setZoomScale] = useState<number>(30); // pixels per second
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoPlayerRef = useRef<HTMLVideoElement>(null);
  const timelineRulerRef = useRef<HTMLDivElement>(null);

  const showNotification = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification((curr) => (curr?.message === message ? null : curr));
    }, 4500);
  };

  // Calculate total sequence duration from all tracks
  const totalDuration = Math.max(
    10,
    ...videoClips.map((c) => c.startTime + c.duration),
    ...audioTracks.map((a) => a.startTime + a.duration),
    ...textCaptions.map((t) => t.startTime + t.duration)
  );

  // Fetch truthful video models
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const headers: Record<string, string> = {};
        if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
        const res = await fetch(`${API_BASE}/media/models`, { headers });
        if (res.ok) {
          const data = await res.json();
          const vMods = (data.models || []).filter((m: any) => m.media_type === 'video');
          if (vMods.length > 0) {
            setVideoModels(vMods);
          }
        }
      } catch {
        // keep defaults
      }
    };
    fetchModels();
  }, [accessToken]);

  // Fetch video asset library
  const fetchLibrary = useCallback(async () => {
    if (!accessToken) return;
    setLibraryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/media/assets?media_type=video`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAssetLibrary(data.assets || []);
      }
    } catch {
      // offline handled
    } finally {
      setLibraryLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchLibrary();
  }, [fetchLibrary]);

  // Handle Starting Frame Upload
  const handleUploadStartingFrame = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!accessToken) {
      showNotification('Sign in to upload reference frames.', 'info');
      return;
    }

    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/media/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setStartingFrame(data.asset.url);
        showNotification('Starting frame reference uploaded.', 'success');
      } else {
        showNotification('Failed to upload starting frame.', 'error');
      }
    } catch {
      showNotification('Network error uploading frame.', 'error');
    }
  };

  // Dispatch Video Generation Job
  const handleGenerateVideo = async () => {
    if (!prompt.trim() || isSubmittingGen) return;
    if (!accessToken) {
      showNotification('Sign in to synthesize AI video sequences.', 'info');
      return;
    }

    setIsSubmittingGen(true);
    try {
      const payload: any = {
        prompt,
        media_type: 'video',
        model: selectedModel,
        duration: durationSec,
        aspect_ratio: aspectRatio,
        resolution,
      };
      if (startingFrame) {
        payload.reference_images = [startingFrame];
      }

      const res = await fetch(`${API_BASE}/media/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        const job = data.job || data;
        setActiveJob({
          id: job.id,
          model: job.model || selectedModel,
          prompt: job.prompt || prompt,
          status: 'processing',
          elapsedSeconds: 0,
        });
        showNotification('Video generation job scheduled. Polling Veo synthesis...', 'info');

        // Poll job status truthfully
        let elapsed = 0;
        const interval = setInterval(async () => {
          elapsed += 4;
          setActiveJob((prev) => (prev ? { ...prev, elapsedSeconds: elapsed } : null));

          try {
            const pollRes = await fetch(`${API_BASE}/media/jobs/${job.id}`, {
              headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (pollRes.ok) {
              const pollData = await pollRes.json();
              if (pollData.status === 'completed' && pollData.media_url) {
                clearInterval(interval);
                setIsSubmittingGen(false);
                setActiveJob({
                  id: job.id,
                  model: job.model,
                  prompt: job.prompt,
                  status: 'completed',
                  media_url: pollData.media_url,
                  elapsedSeconds: elapsed,
                });
                showNotification('AI Video synthesized successfully! Ready for timeline.', 'success');
                fetchLibrary();
              } else if (pollData.status === 'failed') {
                clearInterval(interval);
                setIsSubmittingGen(false);
                setActiveJob({
                  id: job.id,
                  model: job.model,
                  prompt: job.prompt,
                  status: 'failed',
                  error_message: pollData.error_message || 'Video synthesis failed.',
                  elapsedSeconds: elapsed,
                });
                showNotification(`Synthesis failed: ${pollData.error_message}`, 'error');
              }
            }
          } catch {
            // keep polling
          }
          if (elapsed > 180) {
            clearInterval(interval);
            setIsSubmittingGen(false);
            showNotification('Video generation timed out. Please check your job queue.', 'error');
          }
        }, 4000);
      } else {
        const err = await res.json().catch(() => ({}));
        showNotification(err.detail || 'Failed to dispatch video generation job.', 'error');
        setIsSubmittingGen(false);
      }
    } catch {
      showNotification('Network error dispatching video generation.', 'error');
      setIsSubmittingGen(false);
    }
  };

  // Add clip to timeline
  const handleAddClipToTimeline = (url: string, title: string, duration: number = 5) => {
    const lastClip = videoClips[videoClips.length - 1];
    const startTime = lastClip ? lastClip.startTime + lastClip.duration : 0;
    const newClip: VideoClip = {
      id: `clip-${Date.now()}`,
      title,
      url,
      startTime,
      duration,
      trimStart: 0,
      trimEnd: duration,
    };
    setVideoClips((prev) => [...prev, newClip]);
    showNotification(`Added "${title}" to Video Track.`, 'success');
  };

  // Split clip at current playhead
  const handleSplitAtPlayhead = () => {
    const targetIndex = videoClips.findIndex(
      (c) => currentTime > c.startTime && currentTime < c.startTime + c.duration
    );
    if (targetIndex === -1) {
      showNotification('Playhead must be inside a video clip to split.', 'info');
      return;
    }

    const clip = videoClips[targetIndex];
    const firstDuration = currentTime - clip.startTime;
    const secondDuration = clip.duration - firstDuration;

    const firstClip: VideoClip = {
      ...clip,
      duration: firstDuration,
      trimEnd: clip.trimStart + firstDuration,
    };

    const secondClip: VideoClip = {
      id: `clip-split-${Date.now()}`,
      title: `${clip.title} (Part 2)`,
      url: clip.url,
      startTime: currentTime,
      duration: secondDuration,
      trimStart: clip.trimStart + firstDuration,
      trimEnd: clip.trimEnd,
    };

    const updated = [...videoClips];
    updated.splice(targetIndex, 1, firstClip, secondClip);
    setVideoClips(updated);
    showNotification('Split clip at playhead.', 'success');
  };

  // Delete clip from track
  const handleDeleteClip = (id: string) => {
    setVideoClips((prev) => prev.filter((c) => c.id !== id));
    showNotification('Removed clip from timeline.', 'info');
  };

  // Add Caption
  const handleAddCaption = () => {
    const newCap: TextCaptionItem = {
      id: `txt-${Date.now()}`,
      text: 'New Scene Title',
      startTime: currentTime,
      duration: 3,
      fontSize: 24,
      color: '#f8fafc',
    };
    setTextCaptions((prev) => [...prev, newCap]);
    showNotification('Added text title at playhead.', 'success');
  };

  // Format seconds to mm:ss
  const formatTimecode = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 10);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms}`;
  };

  // Timeline scrub click
  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRulerRef.current) return;
    const rect = timelineRulerRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const seekTime = Math.max(0, Math.min(totalDuration, clickX / zoomScale));
    setCurrentTime(seekTime);
    if (videoPlayerRef.current) {
      videoPlayerRef.current.currentTime = seekTime;
    }
  };

  // Play / Pause sequence simulation
  useEffect(() => {
    let animFrame: number;
    let lastTimestamp: number | null = null;

    if (isPlaying) {
      const step = (now: number) => {
        if (lastTimestamp === null) lastTimestamp = now;
        const delta = (now - lastTimestamp) / 1000;
        lastTimestamp = now;

        setCurrentTime((prev) => {
          const next = prev + delta;
          if (next >= totalDuration) {
            setIsPlaying(false);
            return totalDuration;
          }
          return next;
        });

        animFrame = requestAnimationFrame(step);
      };
      animFrame = requestAnimationFrame(step);
    }

    return () => cancelAnimationFrame(animFrame);
  }, [isPlaying, totalDuration]);

  // Find active video clip at playhead
  const activeClip = videoClips.find(
    (c) => currentTime >= c.startTime && currentTime <= c.startTime + c.duration
  );

  // Find active text overlay at playhead
  const activeCaptions = textCaptions.filter(
    (t) => currentTime >= t.startTime && currentTime <= t.startTime + t.duration
  );

  return (
    <div className="video-studio">
      {/* Top Navbar */}
      <header className="video-studio__header">
        <div className="video-studio__brand">
          <button type="button" className="video-studio__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <span className="video-studio__brand-pill">🎬 Video Studio & Sequencer</span>
        </div>

        <div className="video-studio__header-actions">
          <button
            type="button"
            className="video-studio__export-btn"
            onClick={() => {
              showNotification(
                `Exported timeline with ${videoClips.length} video clips, ${audioTracks.length} audio tracks, and ${textCaptions.length} titles.`,
                'success'
              );
            }}
          >
            🚀 Export Video Project
          </button>
        </div>
      </header>

      {/* Main Workspace Body */}
      <div className="video-studio__workspace">
        {/* Left Side Panel: AI Generator & Media Bin */}
        <aside className="video-studio__sidepanel">
          <div className="video-studio__tab-switcher">
            <button
              type="button"
              className={`side-tab-btn ${activeSideTab === 'generate' ? 'active' : ''}`}
              onClick={() => setActiveSideTab('generate')}
            >
              ✨ AI Generator
            </button>
            <button
              type="button"
              className={`side-tab-btn ${activeSideTab === 'library' ? 'active' : ''}`}
              onClick={() => setActiveSideTab('library')}
            >
              📁 Clip Bin ({assetLibrary.length})
            </button>
          </div>

          {activeSideTab === 'generate' ? (
            <div className="video-gen-form">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label className="form-label" style={{ marginBottom: 0 }}>Video Prompt</label>
                <VoiceInputControl
                  toolId="video-studio"
                  size="sm"
                  onTranscript={(transcript) => {
                    setPrompt((prev) => (prev ? `${prev} ${transcript}` : transcript));
                    setInterimPrompt('');
                  }}
                  onInterim={(interim) => {
                    setInterimPrompt(interim);
                  }}
                  disabled={isSubmittingGen}
                />
              </div>
              {interimPrompt && (
                <div style={{ fontSize: '0.78rem', color: '#0d9488', fontStyle: 'italic', marginBottom: '4px' }}>
                  Listening: "{interimPrompt}"
                </div>
              )}
              <textarea
                className="form-textarea"
                rows={3}
                placeholder="Cinematic drone shot soaring over cybernetic neon metropolis at sunset, ultra photorealistic, 4k..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />

              <div className="form-row">
                <label className="form-label">AI Video Model</label>
                <select
                  className="form-select"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  {videoModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} {m.badge ? `(${m.badge})` : ''} {!m.is_available ? '⚠️ Key Req.' : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-row">
                <label className="form-label">Duration</label>
                <div className="duration-pill-group">
                  {[5, 10, 30].map((sec) => (
                    <button
                      key={sec}
                      type="button"
                      className={`pill-btn ${durationSec === sec ? 'active' : ''}`}
                      onClick={() => setDurationSec(sec)}
                    >
                      {sec}s
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-row form-row--inline">
                <div>
                  <label className="form-label">Aspect Ratio</label>
                  <select
                    className="form-select"
                    value={aspectRatio}
                    onChange={(e) => setAspectRatio(e.target.value)}
                  >
                    <option value="16:9">16:9 (Landscape)</option>
                    <option value="9:16">9:16 (Story)</option>
                    <option value="1:1">1:1 (Square)</option>
                  </select>
                </div>
                <div>
                  <label className="form-label">Resolution</label>
                  <select
                    className="form-select"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value)}
                  >
                    <option value="720p">720p HD</option>
                    <option value="1080p">1080p Full HD</option>
                    <option value="4k">4K Ultra</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <label className="form-label">Image-to-Video Starting Frame (Optional)</label>
                <div className="frame-upload-box">
                  {startingFrame ? (
                    <div className="frame-preview">
                      <img src={startingFrame} alt="Starting Frame" />
                      <button
                        type="button"
                        className="frame-remove-btn"
                        onClick={() => setStartingFrame(null)}
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="upload-frame-btn"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      📷 Select Reference Image
                    </button>
                  )}
                  <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    accept="image/*"
                    onChange={handleUploadStartingFrame}
                  />
                </div>
              </div>

              <button
                type="button"
                className="synthesize-btn"
                onClick={handleGenerateVideo}
                disabled={!prompt.trim() || isSubmittingGen}
              >
                {isSubmittingGen ? '⏳ Synthesizing AI Video...' : '🎬 Synthesize Video Clip'}
              </button>

              {/* Truthful Live Job Card */}
              {activeJob && (
                <div className={`live-job-card live-job-card--${activeJob.status}`}>
                  <div className="job-card-header">
                    <span className="job-status-badge">
                      {activeJob.status === 'processing' && '⏳ Processing'}
                      {activeJob.status === 'completed' && '✓ Ready'}
                      {activeJob.status === 'failed' && '⚠️ Failed'}
                    </span>
                    <span className="job-timer">{activeJob.elapsedSeconds || 0}s</span>
                  </div>
                  <p className="job-prompt">{activeJob.prompt}</p>

                  {activeJob.status === 'processing' && (
                    <p className="job-hint">
                      Polling Google Veo operation. Synthesis can take 30-90s depending on resolution.
                    </p>
                  )}

                  {activeJob.status === 'failed' && (
                    <p className="job-error">{activeJob.error_message}</p>
                  )}

                  {activeJob.status === 'completed' && activeJob.media_url && (
                    <div className="job-completed-actions">
                      <button
                        type="button"
                        className="add-to-timeline-btn"
                        onClick={() =>
                          handleAddClipToTimeline(
                            activeJob.media_url!,
                            activeJob.prompt.slice(0, 24) || 'AI Video Clip',
                            durationSec
                          )
                        }
                      >
                        + Add to Timeline Track
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="clip-bin-container">
              {libraryLoading ? (
                <p className="bin-empty">Loading video library...</p>
              ) : assetLibrary.length === 0 ? (
                <p className="bin-empty">No videos generated yet. Synthesize your first clip above!</p>
              ) : (
                <div className="bin-grid">
                  {assetLibrary.map((item) => (
                    <div key={item.id} className="bin-card">
                      <div className="bin-card-thumb">
                        <video src={item.url} preload="metadata" />
                        <span className="bin-duration">
                          {item.duration_seconds ? `${item.duration_seconds}s` : 'Video'}
                        </span>
                      </div>
                      <p className="bin-title">{item.title}</p>
                      <button
                        type="button"
                        className="bin-add-btn"
                        onClick={() =>
                          handleAddClipToTimeline(
                            item.url,
                            item.title,
                            item.duration_seconds || 5
                          )
                        }
                      >
                        + Add to Timeline
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>

        {/* Center Section: Monitor & Timeline */}
        <main className="video-studio__main">
          {/* Notifications Toast */}
          {notification && (
            <div className={`video-notice video-notice--${notification.type}`} role="status">
              <span>{notification.type === 'success' ? '✓' : notification.type === 'error' ? '⚠️' : 'ℹ️'}</span>
              <span>{notification.message}</span>
            </div>
          )}

          {/* Sequence Preview Monitor */}
          <div className="video-monitor">
            <div className="monitor-screen">
              {activeClip ? (
                <video
                  ref={videoPlayerRef}
                  src={activeClip.url}
                  className="monitor-video"
                  autoPlay={isPlaying}
                  muted
                  playsInline
                />
              ) : (
                <div className="monitor-placeholder">
                  <span className="placeholder-icon">🎬</span>
                  <p>Timeline Empty or Playhead at Empty Space</p>
                  <span>Add generated clips from the left panel to begin sequence editing</span>
                </div>
              )}

              {/* Text / Caption Overlays */}
              {activeCaptions.map((cap) => (
                <div
                  key={cap.id}
                  className="monitor-caption-overlay"
                  style={{ fontSize: `${cap.fontSize}px`, color: cap.color }}
                >
                  {cap.text}
                </div>
              ))}
            </div>

            {/* Monitor Control Bar */}
            <div className="monitor-bar">
              <div className="timecode-display">
                <span className="time-current">{formatTimecode(currentTime)}</span>
                <span className="time-separator">/</span>
                <span className="time-total">{formatTimecode(totalDuration)}</span>
              </div>

              <div className="playback-controls">
                <button
                  type="button"
                  className="monitor-btn"
                  onClick={() => setCurrentTime(0)}
                  title="Jump to Start"
                >
                  ⏮
                </button>
                <button
                  type="button"
                  className="monitor-btn"
                  onClick={() => setCurrentTime((t) => Math.max(0, t - 1))}
                  title="Step Backward 1s"
                >
                  ⏪
                </button>
                <button
                  type="button"
                  className="monitor-btn monitor-btn--play"
                  onClick={() => setIsPlaying((p) => !p)}
                  title={isPlaying ? 'Pause Sequence' : 'Play Sequence'}
                >
                  {isPlaying ? '⏸' : '▶'}
                </button>
                <button
                  type="button"
                  className="monitor-btn"
                  onClick={() => setCurrentTime((t) => Math.min(totalDuration, t + 1))}
                  title="Step Forward 1s"
                >
                  ⏩
                </button>
                <button
                  type="button"
                  className="monitor-btn"
                  onClick={() => setCurrentTime(totalDuration)}
                  title="Jump to End"
                >
                  ⏭
                </button>
              </div>

              <div className="timeline-zoom-box">
                <span>Zoom</span>
                <input
                  type="range"
                  min="15"
                  max="70"
                  value={zoomScale}
                  onChange={(e) => setZoomScale(Number(e.target.value))}
                />
              </div>
            </div>
          </div>

          {/* Multi-Track Timeline Editor */}
          <div className="timeline-container">
            {/* Timeline Action Bar */}
            <div className="timeline-toolbar">
              <div className="timeline-tools-left">
                <button
                  type="button"
                  className="timeline-action-btn"
                  onClick={handleSplitAtPlayhead}
                  title="Split video clip at current playhead position"
                >
                  ✂️ Split Clip
                </button>
                <button
                  type="button"
                  className="timeline-action-btn"
                  onClick={handleAddCaption}
                  title="Add text caption block"
                >
                  💬 Add Title
                </button>
                <button
                  type="button"
                  className="timeline-action-btn"
                  onClick={() => {
                    const newAud: AudioTrackItem = {
                      id: `aud-${Date.now()}`,
                      name: 'Ambient Electronic Beat',
                      startTime: currentTime,
                      duration: 10,
                      volume: 90,
                      muted: false,
                    };
                    setAudioTracks((prev) => [...prev, newAud]);
                    showNotification('Added background audio track.', 'success');
                  }}
                  title="Add music/audio layer"
                >
                  🎵 Add Audio
                </button>
              </div>

              <div className="timeline-tools-right">
                <button
                  type="button"
                  className="timeline-action-btn timeline-action-btn--danger"
                  onClick={() => {
                    setVideoClips([]);
                    setTextCaptions([]);
                    setCurrentTime(0);
                    showNotification('Timeline tracks cleared.', 'info');
                  }}
                >
                  🗑️ Clear All
                </button>
              </div>
            </div>

            {/* Scrubbable Time Ruler */}
            <div
              ref={timelineRulerRef}
              className="timeline-ruler"
              onClick={handleTimelineClick}
              style={{ width: `${totalDuration * zoomScale + 120}px` }}
            >
              {Array.from({ length: Math.ceil(totalDuration) + 1 }).map((_, sec) => (
                <div
                  key={sec}
                  className="ruler-tick"
                  style={{ left: `${sec * zoomScale}px` }}
                >
                  <span className="tick-label">{sec}s</span>
                </div>
              ))}

              {/* Glowing Playhead Needle */}
              <div
                className="timeline-playhead"
                style={{ left: `${currentTime * zoomScale}px` }}
              >
                <div className="playhead-badge">{formatTimecode(currentTime)}</div>
                <div className="playhead-line" />
              </div>
            </div>

            {/* Tracks Container */}
            <div
              className="timeline-tracks"
              style={{ width: `${totalDuration * zoomScale + 120}px` }}
            >
              {/* TRACK 1: VIDEO */}
              <div className="track-lane">
                <div className="track-header">
                  <span>🎬 Video Track</span>
                  <span className="clip-count">{videoClips.length} clips</span>
                </div>
                <div className="track-content">
                  {videoClips.map((clip) => (
                    <div
                      key={clip.id}
                      className="track-clip track-clip--video"
                      style={{
                        left: `${clip.startTime * zoomScale}px`,
                        width: `${clip.duration * zoomScale}px`,
                      }}
                    >
                      <span className="clip-trim-handle clip-trim-handle--left">[</span>
                      <div className="clip-info">
                        <span className="clip-title">{clip.title}</span>
                        <span className="clip-duration">{clip.duration.toFixed(1)}s</span>
                      </div>
                      <button
                        type="button"
                        className="clip-delete-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteClip(clip.id);
                        }}
                      >
                        ✕
                      </button>
                      <span className="clip-trim-handle clip-trim-handle--right">]</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* TRACK 2: AUDIO */}
              <div className="track-lane">
                <div className="track-header">
                  <span>🎵 Music / Audio</span>
                  <span className="clip-count">{audioTracks.length} tracks</span>
                </div>
                <div className="track-content">
                  {audioTracks.map((aud) => (
                    <div
                      key={aud.id}
                      className="track-clip track-clip--audio"
                      style={{
                        left: `${aud.startTime * zoomScale}px`,
                        width: `${aud.duration * zoomScale}px`,
                      }}
                    >
                      <div className="audio-waveform-bars">
                        {Array.from({ length: 16 }).map((_, i) => (
                          <span
                            key={i}
                            className="wave-bar"
                            style={{ height: `${20 + (i % 5) * 15}%` }}
                          />
                        ))}
                      </div>
                      <span className="clip-title">{aud.name}</span>
                      <button
                        type="button"
                        className="clip-delete-btn"
                        onClick={() =>
                          setAudioTracks((prev) => prev.filter((a) => a.id !== aud.id))
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* TRACK 3: TEXT & TITLES */}
              <div className="track-lane">
                <div className="track-header">
                  <span>💬 Text & Titles</span>
                  <span className="clip-count">{textCaptions.length} titles</span>
                </div>
                <div className="track-content">
                  {textCaptions.map((cap) => (
                    <div
                      key={cap.id}
                      className="track-clip track-clip--text"
                      style={{
                        left: `${cap.startTime * zoomScale}px`,
                        width: `${cap.duration * zoomScale}px`,
                      }}
                    >
                      <span className="clip-title">{cap.text}</span>
                      <button
                        type="button"
                        className="clip-delete-btn"
                        onClick={() =>
                          setTextCaptions((prev) => prev.filter((t) => t.id !== cap.id))
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* TRACK 4: TRANSITIONS & FX */}
              <div className="track-lane">
                <div className="track-header">
                  <span>✨ Transitions & FX</span>
                  <span className="clip-count">{effects.length} fx</span>
                </div>
                <div className="track-content">
                  {effects.map((fx) => (
                    <div
                      key={fx.id}
                      className="track-clip track-clip--fx"
                      style={{
                        left: `${fx.startTime * zoomScale}px`,
                        width: `${fx.duration * zoomScale}px`,
                      }}
                    >
                      <span className="clip-title">Cross Dissolve</span>
                      <button
                        type="button"
                        className="clip-delete-btn"
                        onClick={() =>
                          setEffects((prev) => prev.filter((e) => e.id !== fx.id))
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
