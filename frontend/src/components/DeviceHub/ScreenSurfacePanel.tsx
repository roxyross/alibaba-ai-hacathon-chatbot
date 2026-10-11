import React from 'react';
import {
  Camera,
  Download,
  Copy,
  ExternalLink,
} from 'lucide-react';
import type { DeviceInfo, ScreenCaptureData } from './DeviceHub';

export interface ScreenSurfacePanelProps {
  device: DeviceInfo | null;
  latestScreen: ScreenCaptureData | null;
  capturingScreen: boolean;
  onCaptureScreen: () => Promise<void>;
  onShowNotification: (type: 'success' | 'error' | 'info', message: string) => void;
}

export const ScreenSurfacePanel: React.FC<ScreenSurfacePanelProps> = ({
  device,
  latestScreen,
  capturingScreen,
  onCaptureScreen,
  onShowNotification,
}) => {
  const handleCopyUrl = () => {
    if (latestScreen?.image_url) {
      const fullUrl = latestScreen.image_url.startsWith('http')
        ? latestScreen.image_url
        : `${window.location.origin}${latestScreen.image_url}`;
      navigator.clipboard.writeText(fullUrl);
      onShowNotification('info', 'Screenshot URL copied to clipboard');
    }
  };

  return (
    <div className="screen-panel">
      {/* 1. Toolbar */}
      <div className="screen-panel__toolbar">
        <div className="screen-panel__toolbar-left">
          <h2>Display & Surface Inspection</h2>
          <p>
            Real-time visual capture of {device?.device_name || 'Host'} display surface for OCR
            grounding and visual agent verification.
          </p>
        </div>

        <div className="screen-panel__toolbar-right">
          <button
            type="button"
            className="screen-panel__action-btn screen-panel__action-btn--primary"
            onClick={onCaptureScreen}
            disabled={capturingScreen}
          >
            <Camera size={15} className={capturingScreen ? 'spin' : ''} />
            <span>{capturingScreen ? 'Capturing Display...' : 'Capture Screenshot'}</span>
          </button>
        </div>
      </div>

      {/* 2. Screen Viewer Box */}
      <div className="screen-panel__viewer-box">
        {latestScreen ? (
          <div className="screen-panel__container">
            {/* Metadata Bar */}
            <div className="screen-panel__meta-bar">
              <div className="screen-panel__meta-left">
                <span className="screen-panel__meta-badge">
                  {latestScreen.width} × {latestScreen.height} px
                </span>
                <span className="screen-panel__meta-item">
                  Captured: {new Date(latestScreen.captured_at).toLocaleTimeString()}
                </span>
                <span className="screen-panel__meta-item">Device: {device?.device_name}</span>
              </div>

              <div className="screen-panel__actions">
                <a
                  href={latestScreen.image_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="screen-panel__icon-btn"
                  title="Open full resolution in new tab"
                >
                  <ExternalLink size={14} />
                  <span>Open Full</span>
                </a>
                <button
                  type="button"
                  className="screen-panel__icon-btn"
                  onClick={handleCopyUrl}
                  title="Copy direct image link"
                >
                  <Copy size={14} />
                  <span>Copy URL</span>
                </button>
                <a
                  href={latestScreen.image_url}
                  download={`roxy_screenshot_${Date.now()}.png`}
                  className="screen-panel__icon-btn screen-panel__icon-btn--primary"
                  title="Download image file"
                >
                  <Download size={14} />
                  <span>Download</span>
                </a>
              </div>
            </div>

            {/* Image Canvas */}
            <div className="screen-panel__image-wrap">
              <img
                src={latestScreen.image_url}
                alt="Display Screen Capture"
                className="screen-panel__img"
              />
            </div>
          </div>
        ) : (
          <div className="screen-panel__empty">
            <Camera size={52} />
            <h3>No Display Frame Captured</h3>
            <p>
              Click "Capture Screenshot" to grab the primary active display of{' '}
              {device?.device_name || 'your device'}.
            </p>
            <button
              type="button"
              className="screen-panel__action-btn screen-panel__action-btn--primary"
              onClick={onCaptureScreen}
              disabled={capturingScreen}
            >
              <Camera size={15} />
              <span>Capture Now</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
