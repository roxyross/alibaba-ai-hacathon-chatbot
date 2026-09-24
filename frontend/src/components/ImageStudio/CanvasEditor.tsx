import React, { useState, useRef, useEffect, useCallback } from 'react';
import './CanvasEditor.css';

interface CanvasEditorProps {
  imageUrl: string;
  initialPrompt?: string;
  accessToken: string | null;
  onClose: () => void;
  onSaveVersion: (newImageUrl: string, metadata: { prompt: string; version: number }) => void;
  showNotification: (message: string, type?: 'success' | 'error' | 'info') => void;
}

interface FilterState {
  brightness: number; // -100 to 100 (0 default)
  contrast: number;   // -100 to 100 (0 default)
  saturation: number; // -100 to 100 (0 default)
  blur: number;       // 0 to 20 (0 default)
  grayscale: number;  // 0 to 100 (0 default)
  sepia: number;      // 0 to 100 (0 default)
}

const DEFAULT_FILTERS: FilterState = {
  brightness: 0,
  contrast: 0,
  saturation: 0,
  blur: 0,
  grayscale: 0,
  sepia: 0,
};

const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

export const CanvasEditor: React.FC<CanvasEditorProps> = ({
  imageUrl,
  initialPrompt = 'Canvas Artwork Edit',
  accessToken,
  onClose,
  onSaveVersion,
  showNotification,
}) => {
  const [activeTool, setActiveTool] = useState<'adjust' | 'crop' | 'inpaint' | 'rotate'>('adjust');
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [rotation, setRotation] = useState<number>(0); // 0, 90, 180, 270
  const [flipH, setFlipH] = useState<boolean>(false);
  const [flipV, setFlipV] = useState<boolean>(false);

  // Inpaint & Mask state
  const [brushSize, setBrushSize] = useState<number>(24);
  const [isDrawingMask, setIsDrawingMask] = useState<boolean>(false);
  const [hasMask, setHasMask] = useState<boolean>(false);
  const [inpaintPrompt, setInpaintPrompt] = useState<string>('');
  const [isInpainting, setIsInpainting] = useState<boolean>(false);

  // Crop state
  const [cropAspect, setCropAspect] = useState<string>('free');

  // Canvases
  const baseCanvasRef = useRef<HTMLCanvasElement>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement>(null);
  const imageObjRef = useRef<HTMLImageElement | null>(null);

  // Version counter
  const [versionCounter, setVersionCounter] = useState<number>(2);

  // Load image onto main canvas
  useEffect(() => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = imageUrl;
    img.onload = () => {
      imageObjRef.current = img;
      renderBaseCanvas();
    };
  }, [imageUrl]);

  // Re-render base canvas when filters, rotation, or flip change
  const renderBaseCanvas = useCallback(() => {
    const img = imageObjRef.current;
    const canvas = baseCanvasRef.current;
    if (!img || !canvas) return;

    const isRotatedSideways = rotation === 90 || rotation === 270;
    const targetWidth = isRotatedSideways ? img.height : img.width;
    const targetHeight = isRotatedSideways ? img.width : img.height;

    canvas.width = targetWidth;
    canvas.height = targetHeight;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Apply CSS filters on context
    const b = 100 + filters.brightness;
    const c = 100 + filters.contrast;
    const s = 100 + filters.saturation;
    ctx.filter = `brightness(${b}%) contrast(${c}%) saturate(${s}%) blur(${filters.blur}px) grayscale(${filters.grayscale}%) sepia(${filters.sepia}%)`;

    // Apply rotation and flips around center
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.scale(flipH ? -1 : 1, flipV ? -1 : 1);

    ctx.drawImage(img, -img.width / 2, -img.height / 2, img.width, img.height);
    ctx.restore();

    // Match mask canvas dimensions
    const maskCanvas = maskCanvasRef.current;
    if (maskCanvas && (maskCanvas.width !== canvas.width || maskCanvas.height !== canvas.height)) {
      maskCanvas.width = canvas.width;
      maskCanvas.height = canvas.height;
    }
  }, [filters, rotation, flipH, flipV]);

  useEffect(() => {
    renderBaseCanvas();
  }, [renderBaseCanvas]);

  // Rotate handlers
  const handleRotateCW = () => setRotation((prev) => (prev + 90) % 360);
  const handleRotateCCW = () => setRotation((prev) => (prev + 270) % 360);
  const handleToggleFlipH = () => setFlipH((prev) => !prev);
  const handleToggleFlipV = () => setFlipV((prev) => !prev);

  // Mask Drawing Logic
  const getCanvasCoords = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const startDrawingMask = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool !== 'inpaint') return;
    setIsDrawingMask(true);
    const { x, y } = getCanvasCoords(e);
    drawMaskPoint(x, y);
  };

  const drawMaskMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawingMask || activeTool !== 'inpaint') return;
    const { x, y } = getCanvasCoords(e);
    drawMaskPoint(x, y);
  };

  const stopDrawingMask = () => {
    setIsDrawingMask(false);
  };

  const drawMaskPoint = (x: number, y: number) => {
    const maskCanvas = maskCanvasRef.current;
    if (!maskCanvas) return;
    const ctx = maskCanvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = 'rgba(239, 68, 68, 0.55)'; // Semi-transparent red mask
    ctx.beginPath();
    ctx.arc(x, y, brushSize, 0, Math.PI * 2);
    ctx.fill();
    setHasMask(true);
  };

  const handleClearMask = () => {
    const maskCanvas = maskCanvasRef.current;
    if (!maskCanvas) return;
    const ctx = maskCanvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
    setHasMask(false);
    showNotification('Inpaint mask cleared.', 'info');
  };

  // Perform Inpainting via AI endpoint
  const handlePerformInpaint = async () => {
    if (!hasMask || !inpaintPrompt.trim()) {
      showNotification('Please draw a mask on the canvas and describe your inpaint concept.', 'error');
      return;
    }
    if (!accessToken) {
      showNotification('Sign in to synthesize neural inpainting.', 'info');
      return;
    }

    setIsInpainting(true);
    try {
      const baseCanvas = baseCanvasRef.current;
      const maskCanvas = maskCanvasRef.current;
      if (!baseCanvas || !maskCanvas) return;

      const baseDataUrl = baseCanvas.toDataURL('image/png');
      const maskDataUrl = maskCanvas.toDataURL('image/png');

      const res = await fetch(`${API_BASE}/media/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          prompt: inpaintPrompt,
          media_type: 'image',
          model: 'flux',
          reference_images: [baseDataUrl],
          mask_image: maskDataUrl,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const job = data.job;
        showNotification('Inpainting job scheduled. Polling synthesis...', 'info');

        // Poll job status
        let attempts = 0;
        const interval = setInterval(async () => {
          attempts++;
          try {
            const checkRes = await fetch(`${API_BASE}/media/jobs/${job.id}`, {
              headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (checkRes.ok) {
              const checkData = await checkRes.json();
              if (checkData.status === 'completed' && checkData.media_url) {
                clearInterval(interval);
                setIsInpainting(false);
                handleClearMask();

                // Reload canvas with inpaint result
                const updatedImg = new Image();
                updatedImg.crossOrigin = 'anonymous';
                updatedImg.src = checkData.media_url;
                updatedImg.onload = () => {
                  imageObjRef.current = updatedImg;
                  renderBaseCanvas();
                  showNotification('Inpaint applied successfully!', 'success');
                };
              } else if (checkData.status === 'failed') {
                clearInterval(interval);
                setIsInpainting(false);
                showNotification(checkData.error_message || 'Inpainting failed.', 'error');
              }
            }
          } catch {
            // keep polling
          }
          if (attempts > 30) {
            clearInterval(interval);
            setIsInpainting(false);
            showNotification('Inpainting timed out. Check asset library.', 'error');
          }
        }, 2000);
      } else {
        const err = await res.json().catch(() => ({}));
        showNotification(err.detail || 'Failed to start inpaint synthesis.', 'error');
        setIsInpainting(false);
      }
    } catch {
      showNotification('Network error during inpainting synthesis.', 'error');
      setIsInpainting(false);
    }
  };

  // Crop Preset Execution
  const handleApplyCrop = () => {
    const baseCanvas = baseCanvasRef.current;
    if (!baseCanvas) return;
    const ctx = baseCanvas.getContext('2d');
    if (!ctx) return;

    let targetRatio = 1;
    if (cropAspect === '1:1') targetRatio = 1;
    else if (cropAspect === '16:9') targetRatio = 16 / 9;
    else if (cropAspect === '9:16') targetRatio = 9 / 16;
    else if (cropAspect === '4:5') targetRatio = 4 / 5;
    else if (cropAspect === '3:2') targetRatio = 3 / 2;
    else {
      showNotification('Custom freeform crop selected.', 'info');
      return;
    }

    const currentWidth = baseCanvas.width;
    const currentHeight = baseCanvas.height;
    let cropWidth = currentWidth;
    let cropHeight = currentWidth / targetRatio;

    if (cropHeight > currentHeight) {
      cropHeight = currentHeight;
      cropWidth = currentHeight * targetRatio;
    }

    const startX = (currentWidth - cropWidth) / 2;
    const startY = (currentHeight - cropHeight) / 2;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = cropWidth;
    tempCanvas.height = cropHeight;
    const tempCtx = tempCanvas.getContext('2d');
    if (!tempCtx) return;

    tempCtx.drawImage(baseCanvas, startX, startY, cropWidth, cropHeight, 0, 0, cropWidth, cropHeight);

    const croppedDataUrl = tempCanvas.toDataURL('image/png');
    const croppedImg = new Image();
    croppedImg.onload = () => {
      imageObjRef.current = croppedImg;
      setRotation(0);
      setFlipH(false);
      setFlipV(false);
      renderBaseCanvas();
      showNotification(`Cropped to ${cropAspect} aspect ratio.`, 'success');
    };
    croppedImg.src = croppedDataUrl;
  };

  // Save As New Non-Destructive Version
  const handleSaveAsVersion = async () => {
    const baseCanvas = baseCanvasRef.current;
    if (!baseCanvas) return;

    const dataUrl = baseCanvas.toDataURL('image/png');

    if (!accessToken) {
      // Offline fallback: download directly
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = `roxy_edit_v${versionCounter}.png`;
      a.click();
      showNotification('Downloaded high-res edited canvas (Guest mode).', 'success');
      return;
    }

    try {
      // Convert Data URL to Blob for real upload
      const byteString = atob(dataUrl.split(',')[1]);
      const mimeString = dataUrl.split(',')[0].split(':')[1].split(';')[0];
      const ab = new ArrayBuffer(byteString.length);
      const ia = new Uint8Array(ab);
      for (let i = 0; i < byteString.length; i++) {
        ia[i] = byteString.charCodeAt(i);
      }
      const blob = new Blob([ab], { type: mimeString });
      const file = new File([blob], `edit_version_${versionCounter}.png`, { type: 'image/png' });

      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_BASE}/media/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const savedUrl = data.asset.url;
        onSaveVersion(savedUrl, {
          prompt: `${initialPrompt} (v${versionCounter})`,
          version: versionCounter,
        });
        setVersionCounter((v) => v + 1);
        showNotification(`Saved as Version ${versionCounter} in Media Library!`, 'success');
      } else {
        // Fallback: trigger direct download
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `roxy_edit_v${versionCounter}.png`;
        a.click();
        showNotification('Saved to local downloads.', 'info');
      }
    } catch {
      showNotification('Error persisting version to server. Downloaded locally.', 'error');
    }
  };

  // Download High-Res PNG
  const handleDownloadPNG = () => {
    const baseCanvas = baseCanvasRef.current;
    if (!baseCanvas) return;
    const a = document.createElement('a');
    a.href = baseCanvas.toDataURL('image/png');
    a.download = `roxy_artwork_${Date.now()}.png`;
    a.click();
    showNotification('High-resolution PNG downloaded.', 'success');
  };

  return (
    <div className="canvas-editor-overlay">
      <div className="canvas-editor-container">
        {/* Top bar */}
        <header className="canvas-editor-header">
          <div className="canvas-editor-title">
            <span className="canvas-editor-icon">🖌️</span>
            <div>
              <h3>Neural Canvas Studio</h3>
              <p className="canvas-editor-subtitle">Crop, filter, mask, and inpaint non-destructively</p>
            </div>
          </div>
          <div className="canvas-editor-actions">
            <button
              type="button"
              className="canvas-editor-btn canvas-editor-btn--secondary"
              onClick={handleDownloadPNG}
              title="Download High-Res PNG"
            >
              📥 Download PNG
            </button>
            <button
              type="button"
              className="canvas-editor-btn canvas-editor-btn--primary"
              onClick={handleSaveAsVersion}
              title="Save as non-destructive new version"
            >
              💾 Save as New Version (v{versionCounter})
            </button>
            <button type="button" className="canvas-editor-close-btn" onClick={onClose} title="Exit Editor">
              ✕
            </button>
          </div>
        </header>

        {/* Main Work Area */}
        <div className="canvas-editor-body">
          {/* Left Toolbar */}
          <aside className="canvas-editor-toolbar">
            <button
              type="button"
              className={`canvas-tool-btn ${activeTool === 'adjust' ? 'active' : ''}`}
              onClick={() => setActiveTool('adjust')}
            >
              <span>🎚️</span>
              <span>Adjust</span>
            </button>
            <button
              type="button"
              className={`canvas-tool-btn ${activeTool === 'crop' ? 'active' : ''}`}
              onClick={() => setActiveTool('crop')}
            >
              <span>📐</span>
              <span>Crop</span>
            </button>
            <button
              type="button"
              className={`canvas-tool-btn ${activeTool === 'rotate' ? 'active' : ''}`}
              onClick={() => setActiveTool('rotate')}
            >
              <span>🔄</span>
              <span>Rotate</span>
            </button>
            <button
              type="button"
              className={`canvas-tool-btn ${activeTool === 'inpaint' ? 'active' : ''}`}
              onClick={() => setActiveTool('inpaint')}
            >
              <span>🪄</span>
              <span>Inpaint</span>
            </button>
          </aside>

          {/* Canvas Viewport */}
          <div className="canvas-viewport">
            <div className="canvas-stage">
              <canvas ref={baseCanvasRef} className="canvas-stage__base" />
              <canvas
                ref={maskCanvasRef}
                className={`canvas-stage__mask ${activeTool === 'inpaint' ? 'drawing-active' : ''}`}
                onMouseDown={startDrawingMask}
                onMouseMove={drawMaskMove}
                onMouseUp={stopDrawingMask}
                onMouseLeave={stopDrawingMask}
              />
            </div>
          </div>

          {/* Right Inspector Panel */}
          <aside className="canvas-inspector">
            {activeTool === 'adjust' && (
              <div className="inspector-group">
                <h4>Color & Light Adjustments</h4>
                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Brightness</label>
                    <span>{filters.brightness}%</span>
                  </div>
                  <input
                    type="range"
                    min="-100"
                    max="100"
                    value={filters.brightness}
                    onChange={(e) => setFilters({ ...filters, brightness: Number(e.target.value) })}
                  />
                </div>

                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Contrast</label>
                    <span>{filters.contrast}%</span>
                  </div>
                  <input
                    type="range"
                    min="-100"
                    max="100"
                    value={filters.contrast}
                    onChange={(e) => setFilters({ ...filters, contrast: Number(e.target.value) })}
                  />
                </div>

                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Saturation</label>
                    <span>{filters.saturation}%</span>
                  </div>
                  <input
                    type="range"
                    min="-100"
                    max="100"
                    value={filters.saturation}
                    onChange={(e) => setFilters({ ...filters, saturation: Number(e.target.value) })}
                  />
                </div>

                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Blur</label>
                    <span>{filters.blur}px</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="20"
                    value={filters.blur}
                    onChange={(e) => setFilters({ ...filters, blur: Number(e.target.value) })}
                  />
                </div>

                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Grayscale</label>
                    <span>{filters.grayscale}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={filters.grayscale}
                    onChange={(e) => setFilters({ ...filters, grayscale: Number(e.target.value) })}
                  />
                </div>

                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Sepia</label>
                    <span>{filters.sepia}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={filters.sepia}
                    onChange={(e) => setFilters({ ...filters, sepia: Number(e.target.value) })}
                  />
                </div>

                <button
                  type="button"
                  className="inspector-reset-btn"
                  onClick={() => setFilters(DEFAULT_FILTERS)}
                >
                  ↻ Reset All Adjustments
                </button>
              </div>
            )}

            {activeTool === 'crop' && (
              <div className="inspector-group">
                <h4>Aspect Ratio Crop</h4>
                <p className="inspector-hint">Select a target ratio to crop your canvas:</p>
                <div className="aspect-ratio-grid">
                  {['1:1', '16:9', '9:16', '4:5', '3:2'].map((ratio) => (
                    <button
                      key={ratio}
                      type="button"
                      className={`ratio-btn ${cropAspect === ratio ? 'active' : ''}`}
                      onClick={() => setCropAspect(ratio)}
                    >
                      {ratio}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="inspector-apply-btn"
                  onClick={handleApplyCrop}
                >
                  ✓ Apply Crop ({cropAspect})
                </button>
              </div>
            )}

            {activeTool === 'rotate' && (
              <div className="inspector-group">
                <h4>Transform & Orientation</h4>
                <div className="transform-actions-grid">
                  <button type="button" className="transform-btn" onClick={handleRotateCCW}>
                    ↺ Rotate 90° Left
                  </button>
                  <button type="button" className="transform-btn" onClick={handleRotateCW}>
                    ↻ Rotate 90° Right
                  </button>
                  <button
                    type="button"
                    className={`transform-btn ${flipH ? 'active' : ''}`}
                    onClick={handleToggleFlipH}
                  >
                    ↔ Flip Horizontal
                  </button>
                  <button
                    type="button"
                    className={`transform-btn ${flipV ? 'active' : ''}`}
                    onClick={handleToggleFlipV}
                  >
                    ↕ Flip Vertical
                  </button>
                </div>
              </div>
            )}

            {activeTool === 'inpaint' && (
              <div className="inspector-group">
                <h4>Neural Inpaint Brush</h4>
                <p className="inspector-hint">
                  Paint a mask over the area you want to replace, then enter what to generate.
                </p>

                <div className="inspector-control">
                  <div className="inspector-label-row">
                    <label>Brush Diameter</label>
                    <span>{brushSize * 2}px</span>
                  </div>
                  <input
                    type="range"
                    min="6"
                    max="60"
                    value={brushSize}
                    onChange={(e) => setBrushSize(Number(e.target.value))}
                  />
                </div>

                <button
                  type="button"
                  className="inspector-reset-btn"
                  onClick={handleClearMask}
                  disabled={!hasMask}
                >
                  🧹 Clear Mask
                </button>

                <div className="inpaint-prompt-box">
                  <label>Inpaint Prompt</label>
                  <textarea
                    rows={3}
                    placeholder="E.g., golden luxury watch on wrist, glowing blue neon glasses, futuristic skyline..."
                    value={inpaintPrompt}
                    onChange={(e) => setInpaintPrompt(e.target.value)}
                  />
                </div>

                <button
                  type="button"
                  className="inspector-apply-btn inpaint-btn"
                  onClick={handlePerformInpaint}
                  disabled={!hasMask || !inpaintPrompt.trim() || isInpainting}
                >
                  {isInpainting ? '✨ Synthesizing Inpaint...' : '🪄 Synthesize Inpaint'}
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
};
