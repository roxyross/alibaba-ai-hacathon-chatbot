import React, { useState } from 'react';
import {
  Users,
  Code2,
  Globe,
  Monitor,
  CheckSquare,
  Columns,
  Maximize2,
  Minimize2,
  X,
} from 'lucide-react';
import { CodingStudio } from '../CodingStudio/CodingStudio';
import { BrowserStudio } from '../BrowserStudio/BrowserStudio';
import { DeviceHub, type DeviceInfo } from '../DeviceHub';
import { TaskWorkspacePanel } from '../TaskWorkspacePanel';
import './CoworkWorkspace.css';

export type CoworkSurface = 'code' | 'browser' | 'device' | 'plan';

export interface CoworkWorkspaceProps {
  accessToken?: string | null;
  onExitCowork: () => void;
  onSendToChat: (message: string) => void;
  chatChildren: React.ReactNode;
  devices?: DeviceInfo[];
}

export const CoworkWorkspace: React.FC<CoworkWorkspaceProps> = ({
  accessToken,
  onExitCowork,
  onSendToChat,
  chatChildren,
}) => {
  const [activeSurface, setActiveSurface] = useState<CoworkSurface>('code');
  const [layoutMode, setLayoutMode] = useState<'split' | 'maximize_surface' | 'maximize_chat'>('split');

  return (
    <div className={`cowork-workspace cowork-workspace--${layoutMode}`}>
      {/* 1. Cowork Global Collaboration Banner */}
      <div className="cowork-workspace__header">
        <div className="cowork-workspace__header-left">
          <div className="cowork-workspace__status-badge">
            <span className="cowork-workspace__pulse-dot" />
            <Users size={15} />
            <span>Collaborative Cowork Active</span>
          </div>
          <span className="cowork-workspace__divider">•</span>
          <span className="cowork-workspace__hint">
            ROXY AI and you are co-piloting on shared active surfaces with real-time state synchronization
          </span>
        </div>

        {/* Surface Switcher Tabs */}
        <div className="cowork-workspace__surface-tabs">
          <button
            type="button"
            className={`cowork-workspace__surface-tab ${
              activeSurface === 'code' ? 'cowork-workspace__surface-tab--active' : ''
            }`}
            onClick={() => setActiveSurface('code')}
          >
            <Code2 size={14} />
            <span>Code Workspace</span>
          </button>

          <button
            type="button"
            className={`cowork-workspace__surface-tab ${
              activeSurface === 'browser' ? 'cowork-workspace__surface-tab--active' : ''
            }`}
            onClick={() => setActiveSurface('browser')}
          >
            <Globe size={14} />
            <span>Web Workspace (Phase 16)</span>
          </button>

          <button
            type="button"
            className={`cowork-workspace__surface-tab ${
              activeSurface === 'device' ? 'cowork-workspace__surface-tab--active' : ''
            }`}
            onClick={() => setActiveSurface('device')}
          >
            <Monitor size={14} />
            <span>Device & Screen (Phase 19)</span>
          </button>

          <button
            type="button"
            className={`cowork-workspace__surface-tab ${
              activeSurface === 'plan' ? 'cowork-workspace__surface-tab--active' : ''
            }`}
            onClick={() => setActiveSurface('plan')}
          >
            <CheckSquare size={14} />
            <span>Task Plan</span>
          </button>
        </div>

        {/* Layout & Exit Controls */}
        <div className="cowork-workspace__header-right">
          <div className="cowork-workspace__layout-toggle">
            <button
              type="button"
              className={`cowork-workspace__layout-btn ${
                layoutMode === 'split' ? 'cowork-workspace__layout-btn--active' : ''
              }`}
              onClick={() => setLayoutMode('split')}
              title="50/50 Split View"
            >
              <Columns size={14} />
            </button>
            <button
              type="button"
              className={`cowork-workspace__layout-btn ${
                layoutMode === 'maximize_surface' ? 'cowork-workspace__layout-btn--active' : ''
              }`}
              onClick={() => setLayoutMode('maximize_surface')}
              title="Maximize Collaborative Surface"
            >
              <Maximize2 size={14} />
            </button>
            <button
              type="button"
              className={`cowork-workspace__layout-btn ${
                layoutMode === 'maximize_chat' ? 'cowork-workspace__layout-btn--active' : ''
              }`}
              onClick={() => setLayoutMode('maximize_chat')}
              title="Maximize Conversation Pane"
            >
              <Minimize2 size={14} />
            </button>
          </div>

          <button
            type="button"
            className="cowork-workspace__exit-btn"
            onClick={onExitCowork}
            title="Exit Cowork Mode"
          >
            <X size={15} />
            <span>Exit Cowork</span>
          </button>
        </div>
      </div>

      {/* 2. Dual Pane Split Viewport */}
      <div className="cowork-workspace__panes">
        {/* Left Pane: Chat & Copilot Conversation */}
        {layoutMode !== 'maximize_surface' && (
          <div className="cowork-workspace__chat-pane">
            {chatChildren}
          </div>
        )}

        {/* Right Pane: Active Collaborative Surface */}
        {layoutMode !== 'maximize_chat' && (
          <div className="cowork-workspace__surface-pane">
            {activeSurface === 'code' && (
              <CodingStudio
                accessToken={accessToken}
                onBack={() => onExitCowork()}
                onSendToChat={onSendToChat}
              />
            )}

            {activeSurface === 'browser' && (
              <BrowserStudio
                accessToken={accessToken}
                onBack={() => onExitCowork()}
                onSendToChat={onSendToChat}
              />
            )}

            {activeSurface === 'device' && (
              <DeviceHub
                accessToken={accessToken || null}
                onBack={() => onExitCowork()}
                onSendToChat={onSendToChat}
              />
            )}

            {activeSurface === 'plan' && (
              <div className="cowork-workspace__plan-wrapper">
                <TaskWorkspacePanel
                  isOpen={true}
                  onClose={() => setActiveSurface('code')}
                  taskTitle="Active Cowork Collaboration Plan"
                  onSendToChat={onSendToChat}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default CoworkWorkspace;
