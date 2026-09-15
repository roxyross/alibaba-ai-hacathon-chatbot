import React, { useState, useRef } from 'react';
import './ImageStudio.css';

interface MediaItem {
  id: string;
  url: string;
  prompt: string;
  type: 'image' | 'video';
  quality: string;
  aspectRatio: string;
  speed: string;
  date: string;
}

interface ImageStudioProps {
  accessToken: string | null;
  onBack: () => void;
}

export const ImageStudio: React.FC<ImageStudioProps> = ({ accessToken: _accessToken, onBack }) => {
  const [activeTab, setActiveTab] = useState<'generations' | 'uploads'>('generations');
  const [prompt, setPrompt] = useState('');
  const [mediaType, setMediaType] = useState<'image' | 'video'>('image');
  const [speed, setSpeed] = useState('Fast');
  const [quality, setQuality] = useState('Quality 2.0');
  const [aspectRatio, setAspectRatio] = useState('2:3');
  const [selectedModel, setSelectedModel] = useState('imagen-3.0');
  const [showPlusPopup, setShowPlusPopup] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [generations, setGenerations] = useState<MediaItem[]>([
    {
      id: 'gen-1',
      url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80',
      prompt: 'Minimalist architecture with soft teal glass reflection and cinematic ambient light',
      type: 'image',
      quality: 'Quality 2.0',
      aspectRatio: '2:3',
      speed: 'Fast',
      date: 'Just now',
    },
  ]);

  const [uploads, setUploads] = useState<MediaItem[]>([]);

  // Speech Recognition integration
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
          setPrompt((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };

      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleGenerate = () => {
    if (!prompt.trim() || isGenerating) return;
    setIsGenerating(true);

    setTimeout(() => {
      const samplePool = [
        'https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=800&q=80',
        'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=800&q=80',
        'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=800&q=80',
      ];
      const newMedia: MediaItem = {
        id: `gen-${Date.now()}`,
        url: samplePool[generations.length % samplePool.length],
        prompt,
        type: mediaType,
        quality,
        aspectRatio,
        speed,
        date: 'Just now',
      };
      setGenerations((prev) => [newMedia, ...prev]);
      setIsGenerating(false);
      setPrompt('');
    }, 1200);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const dummyUrl = URL.createObjectURL(file);
    const newUpload: MediaItem = {
      id: `upl-${Date.now()}`,
      url: dummyUrl,
      prompt: file.name,
      type: file.type.startsWith('video') ? 'video' : 'image',
      quality: 'Source',
      aspectRatio: 'Original',
      speed: 'Direct',
      date: 'Just now',
    };
    setUploads((prev) => [newUpload, ...prev]);
    setActiveTab('uploads');
  };

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
              🖼️ Generations
            </button>
            <button
              type="button"
              className={`image-studio__sidebar-btn ${activeTab === 'uploads' ? 'active' : ''}`}
              onClick={() => setActiveTab('uploads')}
            >
              📤 Uploads
            </button>
          </nav>

          {/* Bottom left Upload Media */}
          <div className="image-studio__sidebar-bottom">
            <button
              type="button"
              className="image-studio__upload-media-btn"
              onClick={() => fileInputRef.current?.click()}
            >
              📁 Upload media
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
                  title="Generation Options"
                >
                  +
                </button>

                {/* "+" Popup inside Image Studio */}
                {showPlusPopup && (
                  <div className="image-studio__popup-menu">
                    <div className="image-studio__popup-title">Creative Controls</div>
                    <button
                      type="button"
                      className="image-studio__popup-item"
                      onClick={() => {
                        fileInputRef.current?.click();
                        setShowPlusPopup(false);
                      }}
                    >
                      <span>📸</span> Generate from picture
                    </button>
                    <button
                      type="button"
                      className="image-studio__popup-item"
                      onClick={() => {
                        fileInputRef.current?.click();
                        setShowPlusPopup(false);
                      }}
                    >
                      <span>🎥</span> Generate from video
                    </button>

                    <div className="image-studio__popup-divider" />

                    <div className="image-studio__popup-row">
                      <label>Model</label>
                      <select
                        value={selectedModel}
                        onChange={(e) => setSelectedModel(e.target.value)}
                      >
                        <option value="imagen-3.0">Imagen 3.0</option>
                        <option value="flux-schnell">FLUX.1 Schnell</option>
                        <option value="sd-xl">Stable Diffusion XL</option>
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
                        <option value="2:3">2:3 (Portrait)</option>
                        <option value="1:1">1:1 (Square)</option>
                        <option value="16:9">16:9 (Landscape)</option>
                        <option value="9:16">9:16 (Story)</option>
                        <option value="3:2">3:2 (Classic)</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* Text Input */}
              <input
                type="text"
                className="image-studio__text-input"
                placeholder="Describe what you want to imagine..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleGenerate();
                }}
              />

              {/* Inline Controls */}
              <div className="image-studio__inline-controls">
                {/* Image / Video toggle */}
                <div className="image-studio__type-toggle">
                  <button
                    type="button"
                    className={`type-btn ${mediaType === 'image' ? 'active' : ''}`}
                    onClick={() => setMediaType('image')}
                  >
                    Image
                  </button>
                  <button
                    type="button"
                    className={`type-btn ${mediaType === 'video' ? 'active' : ''}`}
                    onClick={() => setMediaType('video')}
                  >
                    Video
                  </button>
                </div>

                {/* Speed selector */}
                <select
                  className="image-studio__select"
                  value={speed}
                  onChange={(e) => setSpeed(e.target.value)}
                  title="Speed selector"
                >
                  <option value="Fast">Fast</option>
                  <option value="Quality">Quality</option>
                  <option value="Cinematic">Cinematic</option>
                </select>

                {/* Quality selector */}
                <select
                  className="image-studio__select"
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                  title="Quality selector"
                >
                  <option value="Quality 1.0">Quality 1.0</option>
                  <option value="Quality 2.0">Quality 2.0</option>
                  <option value="Ultra HD">Ultra HD</option>
                </select>

                {/* Aspect ratio selector */}
                <select
                  className="image-studio__select"
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  title="Aspect ratio selector"
                >
                  <option value="2:3">2:3</option>
                  <option value="1:1">1:1</option>
                  <option value="16:9">16:9</option>
                  <option value="9:16">9:16</option>
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

                {/* Circular Send Button (soft teal) */}
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
          </div>

          {/* Main Gallery Area */}
          <div className="image-studio__gallery-section">
            <div className="image-studio__gallery-header">
              <h2 className="image-studio__gallery-title">
                {activeTab === 'generations' ? 'Generations' : 'Uploads'}
              </h2>
              {/* Black "+ Upload" button */}
              <button
                type="button"
                className="image-studio__black-upload-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                + Upload
              </button>
            </div>

            {activeTab === 'generations' ? (
              generations.length === 0 ? (
                <div className="image-studio__empty-state">
                  <div className="image-studio__empty-icon">🎨</div>
                  <p>Your recent generations will appear here</p>
                </div>
              ) : (
                <div className="image-studio__grid">
                  {generations.map((item) => (
                    <div key={item.id} className="image-studio__card">
                      <img src={item.url} alt={item.prompt} className="image-studio__card-img" />
                      <div className="image-studio__card-footer">
                        <p className="image-studio__card-prompt">{item.prompt}</p>
                        <div className="image-studio__card-tags">
                          <span>{item.aspectRatio}</span>
                          <span>{item.quality}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : uploads.length === 0 ? (
              <div className="image-studio__empty-state">
                <div className="image-studio__empty-icon">📤</div>
                <p>No uploaded media yet. Click "+ Upload" above to start.</p>
              </div>
            ) : (
              <div className="image-studio__grid">
                {uploads.map((item) => (
                  <div key={item.id} className="image-studio__card">
                    <img src={item.url} alt={item.prompt} className="image-studio__card-img" />
                    <div className="image-studio__card-footer">
                      <p className="image-studio__card-prompt">{item.prompt}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
};
