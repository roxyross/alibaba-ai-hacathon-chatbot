import React, { useState, useRef, useEffect, useCallback } from 'react';
import './ImageStudio.css';
import { CanvasEditor } from './CanvasEditor';

interface MediaItem {
  id: string;
  url: string;
  prompt: string;
  revised_prompt?: string;
  type: 'image' | 'video';
  style_preset?: string;
  quality: string;
  aspectRatio: string;
  speed: string;
  date: string;
  is_favorite?: boolean;
  vault_document_id?: string;
  width?: number;
  height?: number;
  seed?: number;
  model?: string;
}

interface ImageStudioProps {
  accessToken: string | null;
  onBack: () => void;
}

const STYLE_CHIPS = [
  { id: 'photorealistic', label: '📸 Photorealistic' },
  { id: 'cinematic', label: '🎬 Cinematic' },
  { id: 'anime', label: '🌸 Anime' },
  { id: 'cyberpunk', label: '🌆 Cyberpunk' },
  { id: '3d_render', label: '🧸 3D Render' },
  { id: 'oil_painting', label: '🎨 Oil Painting' },
  { id: 'minimalist', label: '📐 Minimalist' },
  { id: 'watercolor', label: '💧 Watercolor' },
];

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const ImageStudio: React.FC<ImageStudioProps> = ({ accessToken, onBack }) => {
  const [activeTab, setActiveTab] = useState<'generations' | 'favorites' | 'uploads'>('generations');
  const [prompt, setPrompt] = useState('');
  const [selectedStyle, setSelectedStyle] = useState('photorealistic');
  const [speed, setSpeed] = useState('Fast');
  const [quality, setQuality] = useState('Quality 2.0');
  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [selectedModel, setSelectedModel] = useState('flux');
  const [availableModels, setAvailableModels] = useState<Array<{ id: string; name: string; is_available: boolean; badge?: string }>>([
    { id: 'flux', name: 'FLUX.1 Schnell', is_available: true, badge: 'Fast' },
    { id: 'imagen-3.0', name: 'Google Imagen 3', is_available: true, badge: 'Photo' },
    { id: 'imagen-4.0', name: 'Google Imagen 4', is_available: true, badge: 'Ultra HD' },
    { id: 'turbo', name: 'Diffusion Turbo', is_available: true, badge: 'Ultra Fast' },
  ]);
  const [showPlusPopup, setShowPlusPopup] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isEnhancing, setIsEnhancing] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [selectedModalItem, setSelectedModalItem] = useState<MediaItem | null>(null);
  const [editingCanvasItem, setEditingCanvasItem] = useState<MediaItem | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [generations, setGenerations] = useState<MediaItem[]>([]);
  const [uploads, setUploads] = useState<MediaItem[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const showNotification = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification((curr) => (curr?.message === message ? null : curr));
    }, 4000);
  };

  const fetchGenerations = useCallback(async () => {
    if (!accessToken) return;
    try {
      setFetchError(null);
      const res = await fetch(`${API_BASE}/images/generations`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        const mapped: MediaItem[] = (data.generations || []).map((g: any) => ({
          id: g.id,
          url: g.media_url,
          prompt: g.prompt,
          revised_prompt: g.revised_prompt,
          type: g.media_type || 'image',
          style_preset: g.style_preset || 'photorealistic',
          quality: g.quality || 'Quality 2.0',
          aspectRatio: g.aspect_ratio || '1:1',
          speed: g.speed || 'Fast',
          date: g.created_at ? new Date(g.created_at).toLocaleDateString() : 'Recently',
          is_favorite: Boolean(g.is_favorite),
          vault_document_id: g.vault_document_id,
          width: g.width,
          height: g.height,
          seed: g.seed,
          model: g.model,
        }));
        setGenerations(mapped);
      } else {
        setFetchError('Failed to load image generations from the studio server.');
      }
    } catch {
      setFetchError('Unable to connect to the Image Studio service. Please check your connection.');
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
          type: u.media_type || 'image',
          quality: 'Source',
          aspectRatio: 'Original',
          speed: 'Direct',
          date: u.created_at ? new Date(u.created_at).toLocaleDateString() : 'Recently',
        }));
        setUploads(mapped);
      }
    } catch {
      // offline error handled gracefully
    }
  }, [accessToken]);

  const fetchModels = useCallback(async () => {
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      const res = await fetch(`${API_BASE}/media/models`, { headers });
      if (res.ok) {
        const data = await res.json();
        const imgModels = (data.models || []).filter((m: any) => m.media_type === 'image');
        if (imgModels.length > 0) {
          setAvailableModels(imgModels);
        }
      }
    } catch {
      // keep default models
    }
  }, [accessToken]);

  useEffect(() => {
    fetchGenerations();
    fetchUploads();
    fetchModels();
  }, [fetchGenerations, fetchUploads, fetchModels]);

  // Speech Recognition integration
  const toggleSpeech = () => {
    const SpeechRecognition =
      (window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      showNotification('Speech recognition is not supported in this browser.', 'error');
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
          setPrompt((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };

      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleEnhancePrompt = async () => {
    if (!prompt.trim() || isEnhancing) return;
    if (!accessToken) {
      showNotification('Sign in to utilize AI prompt enhancement.', 'info');
      return;
    }
    setIsEnhancing(true);
    try {
      const res = await fetch(`${API_BASE}/images/enhance-prompt`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ prompt, style_preset: selectedStyle }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.enhanced_prompt) {
          setPrompt(data.enhanced_prompt);
          showNotification('Prompt enhanced successfully!', 'success');
        }
      } else {
        showNotification('Unable to enhance prompt at this moment.', 'error');
      }
    } catch {
      showNotification('Network error while enhancing prompt.', 'error');
    } finally {
      setIsEnhancing(false);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim() || isGenerating) return;
    if (!accessToken) {
      showNotification('Please sign in to generate neural artwork and persist it to your gallery.', 'info');
      return;
    }
    setIsGenerating(true);

    try {
      const res = await fetch(`${API_BASE}/images/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          prompt,
          media_type: 'image',
          style_preset: selectedStyle,
          speed,
          quality,
          aspect_ratio: aspectRatio,
          model: selectedModel,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const g = data.generation;
        const newItem: MediaItem = {
          id: g.id,
          url: g.media_url,
          prompt: g.prompt,
          revised_prompt: g.revised_prompt,
          type: 'image',
          style_preset: g.style_preset,
          quality: g.quality,
          aspectRatio: g.aspect_ratio,
          speed: g.speed,
          date: 'Just now',
          is_favorite: false,
          width: g.width,
          height: g.height,
          seed: g.seed,
          model: g.model,
        };
        setGenerations((prev) => [newItem, ...prev]);
        setPrompt('');
        setActiveTab('generations');
        showNotification('Artwork synthesized successfully!', 'success');
        return;
      } else {
        const errData = await res.json().catch(() => ({}));
        showNotification(errData.detail || 'Image generation failed. Please try again.', 'error');
      }
    } catch {
      showNotification('Network error during image synthesis. Please verify your connection.', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleToggleFavorite = async (itemId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!accessToken) {
      showNotification('Sign in to add artwork to favorites.', 'info');
      return;
    }
    const previous = [...generations];
    // Optimistic update
    setGenerations((prev) =>
      prev.map((it) => (it.id === itemId ? { ...it, is_favorite: !it.is_favorite } : it))
    );

    try {
      const res = await fetch(`${API_BASE}/images/${itemId}/favorite`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setGenerations((prev) =>
          prev.map((it) => (it.id === itemId ? { ...it, is_favorite: data.generation.is_favorite } : it))
        );
        return;
      }
      // Rollback on failure
      setGenerations(previous);
      showNotification('Failed to update favorite status.', 'error');
    } catch {
      setGenerations(previous);
      showNotification('Network error updating favorite status.', 'error');
    }
  };

  const handleDelete = async (itemId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!accessToken) {
      showNotification('Sign in to manage and delete artwork.', 'info');
      return;
    }
    const previous = [...generations];
    // Optimistic deletion
    setGenerations((prev) => prev.filter((it) => it.id !== itemId));
    if (selectedModalItem?.id === itemId) setSelectedModalItem(null);

    try {
      const res = await fetch(`${API_BASE}/images/${itemId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        // Rollback on failure
        setGenerations(previous);
        showNotification('Failed to delete artwork from studio.', 'error');
      } else {
        showNotification('Artwork deleted from studio.', 'info');
      }
    } catch {
      setGenerations(previous);
      showNotification('Network error while deleting artwork.', 'error');
    }
  };

  const handleSaveToVault = async (itemId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!accessToken) {
      showNotification('Sign in to index artwork into Knowledge Vault.', 'info');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/images/${itemId}/save-to-vault`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setGenerations((prev) =>
          prev.map((it) => (it.id === itemId ? { ...it, vault_document_id: data.vault_document_id } : it))
        );
        showNotification('Artwork and metadata successfully indexed into your Knowledge Vault!', 'success');
      } else {
        const err = await res.json().catch(() => ({}));
        showNotification(err.detail || 'Could not save artwork to Knowledge Vault.', 'error');
      }
    } catch {
      showNotification('Network error saving artwork to Knowledge Vault.', 'error');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!accessToken) {
      showNotification('Sign in to upload reference assets.', 'info');
      return;
    }

    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/images/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      });
      if (res.ok) {
        await fetchUploads();
        setActiveTab('uploads');
        showNotification(`Reference asset "${file.name}" uploaded successfully.`, 'success');
      } else {
        const err = await res.json().catch(() => ({}));
        showNotification(err.detail || 'Failed to upload reference asset.', 'error');
      }
    } catch {
      showNotification('Network error while uploading reference asset.', 'error');
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const displayedGenerations = activeTab === 'favorites'
    ? generations.filter((g) => g.is_favorite)
    : generations;

  return (
    <div className="image-studio">
      <header className="image-studio__topbar">
        <button type="button" className="image-studio__back-btn" onClick={onBack}>
          ← Back to Chat
        </button>
        <span className="image-studio__brand-pill">🎨 Image Studio</span>
      </header>

      <div className="image-studio__body">
        {/* Left Sidebar */}
        <aside className="image-studio__sidebar">
          <nav className="image-studio__sidebar-nav">
            <button
              type="button"
              className={`image-studio__sidebar-btn ${activeTab === 'generations' ? 'active' : ''}`}
              onClick={() => setActiveTab('generations')}
            >
              🖼️ Generations ({generations.length})
            </button>
            <button
              type="button"
              className={`image-studio__sidebar-btn ${activeTab === 'favorites' ? 'active' : ''}`}
              onClick={() => setActiveTab('favorites')}
            >
              ⭐ Favorites ({generations.filter((g) => g.is_favorite).length})
            </button>
            <button
              type="button"
              className={`image-studio__sidebar-btn ${activeTab === 'uploads' ? 'active' : ''}`}
              onClick={() => setActiveTab('uploads')}
            >
              📤 Reference Uploads ({uploads.length})
            </button>
          </nav>

          {/* Bottom left Upload Media */}
          <div className="image-studio__sidebar-bottom">
            <button
              type="button"
              className="image-studio__upload-media-btn"
              onClick={() => fileInputRef.current?.click()}
            >
              📁 Upload Reference
            </button>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept="image/*,video/*"
              onChange={handleFileUpload}
            />
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="image-studio__main">
          {/* Notifications Toast */}
          {notification && (
            <div
              className={`image-studio__notice image-studio__notice--${notification.type}`}
              role="status"
            >
              <span>{notification.type === 'success' ? '✓' : notification.type === 'error' ? '⚠️' : 'ℹ️'}</span>
              <span>{notification.message}</span>
            </div>
          )}

          {/* Connection Error Banner */}
          {fetchError && (
            <div className="image-studio__error-banner" role="alert">
              <div>
                <strong>Connection Error:</strong> {fetchError}
              </div>
              <button
                type="button"
                className="image-studio__retry-btn"
                onClick={() => {
                  fetchGenerations();
                  fetchUploads();
                }}
              >
                ↻ Retry Connection
              </button>
            </div>
          )}

          {/* Guest Mode Auth Notice */}
          {!accessToken && (
            <div className="image-studio__auth-banner">
              <span>🔒</span>
              <span>
                You are currently in guest preview mode. Sign in to synthesize neural artwork, save favorites, upload reference assets, and index creations into your Knowledge Vault.
              </span>
            </div>
          )}

          {/* Top Heading */}
          <div className="image-studio__heading-wrap">
            <h1 className="image-studio__heading">What should we imagine?</h1>
          </div>

          {/* Main Input Bar */}
          <div className="image-studio__input-bar-container">
            <div className="image-studio__input-bar">
              {/* Left "+" Button */}
              <div className="image-studio__plus-wrap">
                <button
                  type="button"
                  className="image-studio__plus-btn"
                  onClick={() => setShowPlusPopup((v) => !v)}
                  title="Creative Model Controls"
                >
                  ⚙️
                </button>

                {showPlusPopup && (
                  <div className="image-studio__popup-menu">
                    <div className="image-studio__popup-row">
                      <label>Model</label>
                      <select
                        value={selectedModel}
                        onChange={(e) => setSelectedModel(e.target.value)}
                      >
                        {availableModels.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} {m.badge ? `(${m.badge})` : ''} {!m.is_available ? '⚠️ Key Req.' : ''}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="image-studio__popup-row">
                      <label>Speed</label>
                      <select value={speed} onChange={(e) => setSpeed(e.target.value)}>
                        <option value="Fast">Fast</option>
                        <option value="Quality">Quality</option>
                        <option value="Cinematic">Cinematic</option>
                      </select>
                    </div>

                    <div className="image-studio__popup-row">
                      <label>Quality</label>
                      <select value={quality} onChange={(e) => setQuality(e.target.value)}>
                        <option value="Quality 1.0">Quality 1.0</option>
                        <option value="Quality 2.0">Quality 2.0</option>
                        <option value="Ultra HD">Ultra HD</option>
                      </select>
                    </div>

                    <div className="image-studio__popup-row">
                      <label>Aspect Ratio</label>
                      <select
                        value={aspectRatio}
                        onChange={(e) => setAspectRatio(e.target.value)}
                      >
                        <option value="1:1">1:1 (Square)</option>
                        <option value="16:9">16:9 (Landscape)</option>
                        <option value="9:16">9:16 (Story / Mobile)</option>
                        <option value="2:3">2:3 (Portrait)</option>
                        <option value="3:2">3:2 (Classic 35mm)</option>
                        <option value="4:5">4:5 (Social Feed)</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* Text Input */}
              <input
                type="text"
                className="image-studio__text-input"
                placeholder="Describe what you want to imagine with neural precision..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleGenerate();
                }}
              />

              {/* Inline Controls */}
              <div className="image-studio__inline-controls">
                <button
                  type="button"
                  className="image-studio__enhance-btn"
                  onClick={handleEnhancePrompt}
                  disabled={!prompt.trim() || isEnhancing}
                  title="Enhance prompt with AI"
                >
                  {isEnhancing ? '✨ Enhancing...' : '✨ Enhance'}
                </button>

                {/* Aspect ratio selector */}
                <select
                  className="image-studio__select"
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  title="Aspect ratio selector"
                >
                  <option value="1:1">1:1</option>
                  <option value="16:9">16:9</option>
                  <option value="9:16">9:16</option>
                  <option value="2:3">2:3</option>
                  <option value="3:2">3:2</option>
                </select>

                {/* Microphone Icon */}
                <button
                  type="button"
                  className={`image-studio__mic-btn ${isListening ? 'listening' : ''}`}
                  onClick={toggleSpeech}
                  title="Voice prompt"
                  aria-label="Voice prompt"
                >
                  🎤
                </button>

                {/* Circular Send Button */}
                <button
                  type="button"
                  className="image-studio__send-btn"
                  onClick={handleGenerate}
                  disabled={!prompt.trim() || isGenerating}
                  aria-label="Generate"
                  title="Generate"
                >
                  {isGenerating ? (
                    <span className="spinner" />
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="19" x2="12" y2="5" />
                      <polyline points="5 12 12 5 19 12" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Style Presets Strip */}
            <div className="image-studio__styles-strip">
              {STYLE_CHIPS.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  className={`image-studio__style-chip ${selectedStyle === chip.id ? 'active' : ''}`}
                  onClick={() => setSelectedStyle(chip.id)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>

          {/* Main Gallery Area */}
          <div className="image-studio__gallery-section">
            <div className="image-studio__gallery-header">
              <h2 className="image-studio__gallery-title">
                {activeTab === 'generations'
                  ? 'Recent Generations'
                  : activeTab === 'favorites'
                  ? 'Favorite Artwork'
                  : 'Uploaded Reference Media'}
              </h2>
              <button
                type="button"
                className="image-studio__black-upload-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                + Upload Reference
              </button>
            </div>

            {activeTab === 'generations' || activeTab === 'favorites' ? (
              displayedGenerations.length === 0 ? (
                <div className="image-studio__empty-state">
                  <div className="image-studio__empty-icon">🎨</div>
                  <p>
                    {activeTab === 'favorites'
                      ? 'No favorite artworks yet. Click the heart icon on any generation to save it here.'
                      : 'Your neural studio gallery is clean and ready. Describe any concept above to synthesize artwork.'}
                  </p>
                </div>
              ) : (
                <div className="image-studio__grid">
                  {displayedGenerations.map((item) => (
                    <div
                      key={item.id}
                      className="image-studio__card"
                      onClick={() => setSelectedModalItem(item)}
                      style={{ cursor: 'pointer' }}
                    >
                      <img src={item.url} alt={item.prompt} className="image-studio__card-img" />
                      <div className="image-studio__card-footer">
                        <p className="image-studio__card-prompt">{item.prompt}</p>
                        <div className="image-studio__card-tags">
                          <span>{item.aspectRatio}</span>
                          <span>{item.style_preset || item.quality}</span>
                        </div>
                        <div className="image-studio__card-bar">
                          <button
                            type="button"
                            className="image-studio__icon-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingCanvasItem(item);
                            }}
                            title="Edit in Canvas Studio (Crop, Filters, Inpaint)"
                          >
                            🖌️
                          </button>
                          <button
                            type="button"
                            className="image-studio__icon-btn"
                            onClick={(e) => handleToggleFavorite(item.id, e)}
                            title={item.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
                          >
                            {item.is_favorite ? '❤️' : '🤍'}
                          </button>
                          <button
                            type="button"
                            className={`image-studio__vault-btn ${item.vault_document_id ? 'saved' : ''}`}
                            onClick={(e) => handleSaveToVault(item.id, e)}
                            title="Save artwork and specifications to Knowledge Vault"
                          >
                            {item.vault_document_id ? '✓ In Vault' : '📑 Save to Vault'}
                          </button>
                          <button
                            type="button"
                            className="image-studio__icon-btn"
                            onClick={(e) => handleDelete(item.id, e)}
                            title="Delete artwork"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : uploads.length === 0 ? (
              <div className="image-studio__empty-state">
                <div className="image-studio__empty-icon">📤</div>
                <p>No uploaded reference media yet. Click "+ Upload Reference" above to begin.</p>
              </div>
            ) : (
              <div className="image-studio__grid">
                {uploads.map((item) => (
                  <div key={item.id} className="image-studio__card">
                    <img src={item.url} alt={item.prompt} className="image-studio__card-img" />
                    <div className="image-studio__card-footer">
                      <p className="image-studio__card-prompt">{item.prompt}</p>
                      <div className="image-studio__card-tags">
                        <span>{item.type}</span>
                        <span>{item.date}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Lightbox / Detail Modal */}
      {selectedModalItem && (
        <div className="image-studio__modal-overlay" onClick={() => setSelectedModalItem(null)}>
          <div className="image-studio__modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="image-studio__modal-header">
              <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>
                🎨 Artwork Specifications
              </h3>
              <button
                type="button"
                className="image-studio__icon-btn"
                onClick={() => setSelectedModalItem(null)}
              >
                ✕
              </button>
            </div>
            <div className="image-studio__modal-body">
              <img
                src={selectedModalItem.url}
                alt={selectedModalItem.prompt}
                className="image-studio__modal-img"
              />
              <div>
                <h4 style={{ margin: '0 0 0.35rem', fontSize: '0.9rem', color: '#64748b' }}>Original Prompt</h4>
                <p style={{ margin: '0 0 1rem', fontSize: '0.95rem', fontWeight: 600 }}>{selectedModalItem.prompt}</p>
                {selectedModalItem.revised_prompt && (
                  <>
                    <h4 style={{ margin: '0 0 0.35rem', fontSize: '0.9rem', color: '#64748b' }}>Enhanced Neural Prompt</h4>
                    <p style={{ margin: '0 0 1rem', fontSize: '0.85rem', color: '#475569', fontStyle: 'italic' }}>
                      {selectedModalItem.revised_prompt}
                    </p>
                  </>
                )}
                <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.82rem', color: '#64748b', flexWrap: 'wrap' }}>
                  <span><strong>Style:</strong> {selectedModalItem.style_preset || 'Photorealistic'}</span>
                  <span><strong>Aspect Ratio:</strong> {selectedModalItem.aspectRatio}</span>
                  {selectedModalItem.width && selectedModalItem.height && (
                    <span><strong>Resolution:</strong> {selectedModalItem.width}x{selectedModalItem.height}</span>
                  )}
                  <span><strong>Model:</strong> {selectedModalItem.model || 'flux'}</span>
                  {selectedModalItem.seed && <span><strong>Seed:</strong> {selectedModalItem.seed}</span>}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="image-studio__black-upload-btn"
                  onClick={() => {
                    setEditingCanvasItem(selectedModalItem);
                    setSelectedModalItem(null);
                  }}
                  style={{ background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)', color: '#fff' }}
                >
                  🖌️ Open in Canvas Studio
                </button>
                <a
                  href={selectedModalItem.url}
                  target="_blank"
                  rel="noreferrer"
                  className="image-studio__black-upload-btn"
                  style={{ textDecoration: 'none', display: 'inline-block' }}
                >
                  🔗 Open High-Res Image
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Neural Canvas Studio */}
      {editingCanvasItem && (
        <CanvasEditor
          imageUrl={editingCanvasItem.url}
          initialPrompt={editingCanvasItem.prompt}
          accessToken={accessToken}
          onClose={() => setEditingCanvasItem(null)}
          onSaveVersion={(newUrl, meta) => {
            const newItem: MediaItem = {
              id: `ver-${Date.now()}`,
              url: newUrl,
              prompt: meta.prompt,
              type: 'image',
              quality: 'Canvas Edited',
              aspectRatio: 'Preserved',
              speed: 'Instant',
              date: 'Just now',
              is_favorite: false,
            };
            setGenerations((prev) => [newItem, ...prev]);
            setEditingCanvasItem(null);
          }}
          showNotification={showNotification}
        />
      )}
    </div>
  );
};
