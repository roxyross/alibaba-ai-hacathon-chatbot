import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  Clock,
  CheckCircle,
  X,
  Volume2,
  VolumeX,
  ChevronDown,
  Calendar,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import { soundEngine } from '../../utils/soundEngine';
import './ReminderAlarmToast.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface ActiveReminderItem {
  id: string;
  user_id: string;
  title: string;
  body: string;
  category: string;
  sound_id: string;
  target_devices: string[];
  status: string;
  scheduled_at: string;
  delivered_at?: string | null;
  snoozed_until?: string | null;
}

interface ReminderAlarmToastProps {
  accessToken?: string | null;
}

export const ReminderAlarmToast: React.FC<ReminderAlarmToastProps> = ({ accessToken }) => {
  const [activeReminders, setActiveReminders] = useState<ActiveReminderItem[]>([]);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [showSnoozeMenu, setShowSnoozeMenu] = useState<string | null>(null);

  // Sync audio playback state
  useEffect(() => {
    return soundEngine.onPlaybackChange((id) => {
      setIsPlayingAudio(!!id);
    });
  }, []);

  // Poll active notifications
  const checkNotifications = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/reminders/notifications`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const items: ActiveReminderItem[] = await res.json();
        const delivered = items.filter((it) => it.status === 'delivered');
        setActiveReminders(delivered);

        // If newly delivered reminders appeared and audio is idle, play sound
        if (delivered.length > 0 && !soundEngine.getCurrentlyPlaying() && !soundEngine.getMute()) {
          const soundToPlay = delivered[0].sound_id || 'roxy_harmonic';
          soundEngine.play(soundToPlay);
        }
      }
    } catch {
      // Offline/network failure resilience
    }
  }, [accessToken]);

  useEffect(() => {
    checkNotifications();
    const timer = setInterval(checkNotifications, 4000);
    return () => clearInterval(timer);
  }, [checkNotifications]);

  // Listen to manual test trigger events
  useEffect(() => {
    const handleCustomTrigger = (e: Event) => {
      const customEvent = e as CustomEvent<ActiveReminderItem>;
      if (customEvent.detail) {
        setActiveReminders((prev) => [customEvent.detail, ...prev]);
        soundEngine.play(customEvent.detail.sound_id || 'roxy_harmonic');
      }
    };
    window.addEventListener('roxy:reminder-triggered', handleCustomTrigger);
    return () => window.removeEventListener('roxy:reminder-triggered', handleCustomTrigger);
  }, []);

  const handleAcknowledge = async (reminderId: string) => {
    soundEngine.stop();
    setActiveReminders((prev) => prev.filter((r) => r.id !== reminderId));
    if (!accessToken) return;
    try {
      await fetch(`${API_BASE}/reminders/${reminderId}/acknowledge`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    } catch {
      // Resilience
    }
  };

  const handleDismiss = async (reminderId: string) => {
    soundEngine.stop();
    setActiveReminders((prev) => prev.filter((r) => r.id !== reminderId));
    if (!accessToken) return;
    try {
      await fetch(`${API_BASE}/reminders/${reminderId}/dismiss`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    } catch {
      // Resilience
    }
  };

  const handleSnooze = async (reminderId: string, minutes: number) => {
    soundEngine.stop();
    setShowSnoozeMenu(null);
    setActiveReminders((prev) => prev.filter((r) => r.id !== reminderId));
    if (!accessToken) return;
    try {
      await fetch(`${API_BASE}/reminders/${reminderId}/snooze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ snooze_minutes: minutes }),
      });
    } catch {
      // Resilience
    }
  };

  if (activeReminders.length === 0) return null;

  return (
    <div className="reminder-alarm-container" role="region" aria-label="Active Reminders & Alarms">
      {activeReminders.map((reminder) => (
        <div key={reminder.id} className="reminder-alarm-card animate-slide-in">
          <div className="reminder-alarm-header">
            <div className="reminder-badge-wrapper">
              <span className={`reminder-category-pill pill-${reminder.category}`}>
                {reminder.category === 'meeting' ? (
                  <Calendar size={13} />
                ) : reminder.category === 'urgent' ? (
                  <AlertTriangle size={13} />
                ) : (
                  <Bell size={13} />
                )}
                <span>{reminder.category.toUpperCase()}</span>
              </span>
              <span className="reminder-sound-badge">
                <Volume2 size={12} />
                <span>{reminder.sound_id.replace('_', ' ')}</span>
              </span>
            </div>

            <div className="reminder-sound-toggle">
              <button
                type="button"
                className={`btn-sound-mute ${isPlayingAudio ? 'is-pulsing' : ''}`}
                title={isPlayingAudio ? 'Stop alarm sound' : 'Sound idle'}
                onClick={() => soundEngine.stop()}
              >
                {isPlayingAudio ? <Volume2 size={16} /> : <VolumeX size={16} />}
              </button>
              <button
                type="button"
                className="btn-toast-close"
                title="Dismiss reminder"
                onClick={() => handleDismiss(reminder.id)}
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="reminder-alarm-body">
            <h4 className="reminder-alarm-title">{reminder.title}</h4>
            {reminder.body && <p className="reminder-alarm-desc">{reminder.body}</p>}
          </div>

          <div className="reminder-alarm-actions">
            <button
              type="button"
              className="btn-action-ack"
              onClick={() => handleAcknowledge(reminder.id)}
            >
              <CheckCircle size={15} />
              <span>Acknowledge</span>
            </button>

            <div className="snooze-dropdown-wrapper">
              <button
                type="button"
                className="btn-action-snooze"
                onClick={() =>
                  setShowSnoozeMenu(showSnoozeMenu === reminder.id ? null : reminder.id)
                }
              >
                <Clock size={15} />
                <span>Snooze</span>
                <ChevronDown size={13} />
              </button>

              {showSnoozeMenu === reminder.id && (
                <div className="snooze-menu-dropdown animate-fade-in">
                  <button type="button" onClick={() => handleSnooze(reminder.id, 5)}>
                    <RotateCcw size={13} /> 5 minutes
                  </button>
                  <button type="button" onClick={() => handleSnooze(reminder.id, 10)}>
                    <RotateCcw size={13} /> 10 minutes
                  </button>
                  <button type="button" onClick={() => handleSnooze(reminder.id, 30)}>
                    <RotateCcw size={13} /> 30 minutes
                  </button>
                  <button type="button" onClick={() => handleSnooze(reminder.id, 60)}>
                    <RotateCcw size={13} /> 1 hour
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              className="btn-action-dismiss"
              onClick={() => handleDismiss(reminder.id)}
            >
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
