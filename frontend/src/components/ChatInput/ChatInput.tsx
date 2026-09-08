/* ChatInput — modern ChatGPT/Claude style input capsule with + flyout tools menu */

import React, { useEffect, useRef, useState } from 'react';
import './ChatInput.css';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  /** When true, the input is disabled with a "choose a model first" hint. */
  disabledNoModel?: boolean;
  /** Optional element rendered to the left of the textarea (e.g. a model picker). */
  leftSlot?: React.ReactNode;
  /** Callback to trigger interactive live voice session */
  onVoiceClick?: () => void;
  /** Callback to trigger document attachment / upload view */
  onAttachmentClick?: () => void;
  /** Custom placeholder override */
  placeholder?: string;
  /** Navigation callback to switch modules directly from tools menu */
  onNavigateView?: (view: 'finance' | 'jobs' | 'email' | 'calculator' | 'calendar') => void;
}

// File extension to icon resolver
function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'].includes(ext)) return '🖼️';
  if (['mp4', 'mkv', 'webm', 'mov', 'avi', 'm4v'].includes(ext)) return '🎥';
  if (['mp3', 'wav', 'ogg', 'm4a', 'flac'].includes(ext)) return '🎵';
  if (ext === 'pdf') return '📕';
  if (['ppt', 'pptx', 'key'].includes(ext)) return '📊';
  if (['doc', 'docx', 'odt', 'rtf'].includes(ext)) return '📄';
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '📈';
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '📦';
  if (['py', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'json', 'yaml', 'yml', 'c', 'cpp', 'rs', 'go', 'java', 'sql', 'sh', 'md'].includes(ext)) return '💻';
  return '📎';
}

// Check for Web Speech API
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

type DictationState = 'idle' | 'recording' | 'transcribing';

export const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  disabled = false,
  isStreaming = false,
  disabledNoModel = false,
  leftSlot,
  onVoiceClick,
  onAttachmentClick: _onAttachmentClick,
  placeholder: customPlaceholder,
  onNavigateView,
}) => {
  const [value, setValue] = useState('');
  const [dictationState, setDictationState] = useState<DictationState>('idle');
  const [audioLevels, setAudioLevels] = useState<number[]>([12, 18, 14, 24, 16, 28, 20, 32, 18, 22, 16, 26, 14, 20, 15, 24]);
  const [showToolsMenu, setShowToolsMenu] = useState(false);
  const [thinkMode, setThinkMode] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const actionBtnRef = useRef<HTMLButtonElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const dictationStateRef = useRef<DictationState>('idle');
  dictationStateRef.current = dictationState;

  const baseValueRef = useRef<string>('');
  const dictationTranscriptRef = useRef<string>('');
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // Close flyout menu on click outside
  useEffect(() => {
    if (!showToolsMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        actionBtnRef.current &&
        !actionBtnRef.current.contains(target)
      ) {
        setShowToolsMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showToolsMenu]);

  // Web Audio analyser for dynamic waveform pulsation
  const startAudioAnalyser = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        const ctx = new AudioCtx();
        audioContextRef.current = ctx;
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 64;
        analyserRef.current = analyser;
        const source = ctx.createMediaStreamSource(stream);
        source.connect(analyser);

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const updateWaveform = () => {
          if (!analyserRef.current || dictationStateRef.current !== 'recording') return;
          analyserRef.current.getByteFrequencyData(dataArray);
          const levels: number[] = [];
          const count = 18;
          const step = Math.floor(bufferLength / count) || 1;
          for (let i = 0; i < count; i++) {
            const val = dataArray[i * step] || 0;
            // Map 0-255 to bar height 6px to 38px
            const h = Math.max(6, Math.min(38, Math.round((val / 255) * 38) + (i % 2 === 0 ? 4 : 2)));
            levels.push(h);
          }
          setAudioLevels(levels);
          animFrameRef.current = requestAnimationFrame(updateWaveform);
        };
        animFrameRef.current = requestAnimationFrame(updateWaveform);
      }
    } catch {
      // Audio stream error — CSS fallback will animate
    }
  };

  const stopAudioAnalyser = () => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try {
        audioContextRef.current.close();
      } catch {
        // ignore
      }
      audioContextRef.current = null;
    }
    analyserRef.current = null;
  };

  // Keyboard shortcut Ctrl+Shift+D for dictation, Esc for cancel
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        if (dictationState === 'recording') {
          finishDictation();
        } else if (dictationState === 'idle') {
          startDictation();
        }
      } else if (e.key === 'Escape' && dictationState === 'recording') {
        e.preventDefault();
        cancelDictation();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [dictationState, value]);

  // Cleanup dictation on unmount
  useEffect(() => {
    return () => {
      stopAudioAnalyser();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const startDictation = () => {
    if (disabled || isStreaming || disabledNoModel) return;

    if (!SpeechRecognitionClass) {
      onVoiceClick?.();
      return;
    }

    baseValueRef.current = value;
    dictationTranscriptRef.current = '';
    setDictationState('recording');

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = navigator.language || 'en-US';

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onresult = (event: any) => {
        let finalChunk = '';
        let interimChunk = '';
        for (let i = 0; i < event.results.length; i++) {
          const res = event.results[i];
          if (res.isFinal) {
            finalChunk += res[0].transcript + ' ';
          } else {
            interimChunk += res[0].transcript;
          }
        }
        dictationTranscriptRef.current = (finalChunk + interimChunk).trim();
      };

      recognition.onerror = () => {
        if (dictationStateRef.current === 'recording') {
          finishDictation();
        }
      };

      recognition.onend = () => {
        if (dictationStateRef.current === 'recording') {
          finishDictation();
        }
      };

      recognition.start();
      recognitionRef.current = recognition;
      startAudioAnalyser();
    } catch {
      setDictationState('idle');
    }
  };

  const finishDictation = () => {
    if (dictationStateRef.current !== 'recording') return;
    setDictationState('transcribing');
    stopAudioAnalyser();

    try {
      recognitionRef.current?.stop();
    } catch {
      // ignore
    }

    // Smooth ChatGPT-like transcribing transition (550ms)
    setTimeout(() => {
      const speech = dictationTranscriptRef.current.trim();
      if (speech) {
        const base = baseValueRef.current.trim();
        const combined = base ? `${base} ${speech}` : speech;
        setValue(combined);
      }
      setDictationState('idle');
      requestAnimationFrame(() => {
        adjustHeight();
        textareaRef.current?.focus();
      });
    }, 550);
  };

  const cancelDictation = () => {
    setDictationState('idle');
    stopAudioAnalyser();
    try {
      recognitionRef.current?.abort();
    } catch {
      // ignore
    }
    setValue(baseValueRef.current);
    requestAnimationFrame(() => {
      adjustHeight();
      textareaRef.current?.focus();
    });
  };

  const sendWhileDictating = () => {
    stopAudioAnalyser();
    try {
      recognitionRef.current?.stop();
    } catch {
      // ignore
    }

    const speech = dictationTranscriptRef.current.trim();
    const base = baseValueRef.current.trim();
    const combined = base ? (speech ? `${base} ${speech}` : base) : speech;

    setDictationState('idle');

    if (combined) {
      onSend(combined);
      setValue('');
      setAttachedFiles([]);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const toggleVoiceDictation = () => {
    if (dictationState === 'recording') {
      finishDictation();
    } else if (dictationState === 'idle') {
      startDictation();
    }
  };

  const adjustHeight = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  };

  const handleFilesSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setAttachedFiles((prev) => [...prev, ...newFiles]);
    }
    e.target.value = '';
  };

  const removeAttachedFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const text = value.trim();
    if ((!text && attachedFiles.length === 0) || disabled || isStreaming || disabledNoModel) return;

    if (dictationState === 'recording') {
      try {
        recognitionRef.current?.stop();
      } catch {
        // ignore
      }
      stopAudioAnalyser();
      setDictationState('idle');
    }

    let messageToSend = text;
    if (thinkMode) {
      messageToSend = `[Deep Reasoning Mode]\n${messageToSend}`;
    }

    if (attachedFiles.length > 0) {
      const fileListDesc = attachedFiles
        .map((f) => `• ${getFileIcon(f.name)} ${f.name} (${(f.size / 1024).toFixed(1)} KB, ${f.type || 'file'})`)
        .join('\n');

      let fileContents = '';
      for (const file of attachedFiles) {
        const ext = file.name.split('.').pop()?.toLowerCase() || '';
        const isText = ['py', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'json', 'yaml', 'yml', 'txt', 'md', 'sql', 'sh', 'csv', 'env'].includes(ext);
        if (isText && file.size < 120 * 1024) {
          try {
            const content = await file.text();
            fileContents += `\n\n--- [File: ${file.name}] ---\n\`\`\`${ext}\n${content.slice(0, 6000)}\n\`\`\``;
          } catch {
            // ignore
          }
        }
      }

      messageToSend = messageToSend
        ? `${messageToSend}\n\n[Attached files from device]:\n${fileListDesc}${fileContents}`
        : `[Attached files from device]:\n${fileListDesc}${fileContents}\nPlease analyze and assist with the attached files.`;
    }

    onSend(messageToSend);
    setValue('');
    setAttachedFiles([]);

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
      return;
    }

    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.currentTarget;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newValue = value.substring(0, start) + '  ' + value.substring(end);
      setValue(newValue);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
        adjustHeight();
      });
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    adjustHeight();
  };

  const placeholder =
    customPlaceholder ||
    (disabledNoModel
      ? 'Choose a model to start chatting…'
      : isStreaming
        ? 'ROXY AI is thinking…'
        : dictationState === 'recording'
          ? 'Listening... speak now'
          : 'Ask anything, chat, or paste code…');

  const hasContent = value.trim().length > 0 || attachedFiles.length > 0;

  return (
    <form className="chat-input" onSubmit={handleSubmit} aria-label="Send message">
      {/* Hidden file input for native computer file access (all extensions: images, videos, pdfs, ppts, docs, code, zips) */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFilesSelected}
        multiple
        accept="*/*"
        style={{ position: 'fixed', top: -9999, left: -9999, opacity: 0, pointerEvents: 'none' }}
        tabIndex={-1}
        aria-hidden="true"
      />

      {/* Hidden folder input for native computer folder upload */}
      <input
        type="file"
        ref={folderInputRef}
        onChange={handleFilesSelected}
        multiple
        {...({ webkitdirectory: '', directory: '' } as unknown as React.InputHTMLAttributes<HTMLInputElement>)}
        style={{ position: 'fixed', top: -9999, left: -9999, opacity: 0, pointerEvents: 'none' }}
        tabIndex={-1}
        aria-hidden="true"
      />

      {/* Floating Tools Popover (+ Menu) */}
      {showToolsMenu && (
        <div className="chat-input__flyout" ref={menuRef} role="menu" aria-label="Add options">
          {/* 1. Add files (opens native device file explorer dialog) */}
          <button
            type="button"
            className="chat-input__flyout-item chat-input__flyout-item--highlight"
            role="menuitem"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setShowToolsMenu(false);
              fileInputRef.current?.click();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--blue">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="chat-input__flyout-title" style={{ fontWeight: 600 }}>Add files</span>
                <span className="chat-input__flyout-badge">Upload</span>
              </div>
              <span className="chat-input__flyout-subtitle">Upload files, PDFs, PPTs, videos, images, code from device</span>
            </div>
          </button>

          {/* 2. Add folder (upload entire folder) */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              folderInputRef.current?.click();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--yellow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Add folder</span>
              <span className="chat-input__flyout-subtitle">Upload complete directory from device</span>
            </div>
          </button>

          {/* 3. Calculator */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              if (onNavigateView) {
                onNavigateView('calculator');
              } else {
                setValue('Calculate: ');
                textareaRef.current?.focus();
              }
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--purple">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="2" width="16" height="20" rx="2" />
                <line x1="8" y1="6" x2="16" y2="6" />
                <line x1="16" y1="14" x2="16" y2="18" />
                <path d="M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M8 18h.01M12 18h.01" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="chat-input__flyout-title">Calculator</span>
                <span className="chat-input__flyout-badge">Tool</span>
              </div>
              <span className="chat-input__flyout-subtitle">Solve math &amp; expressions with Python AST engine</span>
            </div>
          </button>

          {/* 4. Calendar & Agenda */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              if (onNavigateView) {
                onNavigateView('calendar');
              } else {
                setValue('Check my calendar schedule for today and upcoming events.');
                textareaRef.current?.focus();
              }
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--green">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="chat-input__flyout-title">Calendar &amp; Schedule</span>
                <span className="chat-input__flyout-badge">Events</span>
              </div>
              <span className="chat-input__flyout-subtitle">View agenda, monthly grid &amp; schedule events</span>
            </div>
          </button>

          {/* 5. Write or edit code */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Write a script to: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--cyan">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Write or edit code</span>
              <span className="chat-input__flyout-subtitle">Build code, scripts, or debug</span>
            </div>
          </button>

          {/* 6. Flashcards generator */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Generate 5 study flashcards with questions and answers about: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--yellow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Flashcards Generator</span>
              <span className="chat-input__flyout-subtitle">Create study Q&amp;A cards from any topic</span>
            </div>
          </button>

          {/* 7. Search the web */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Search the web for: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--blue">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Search the web</span>
              <span className="chat-input__flyout-subtitle">Find real-time news and info</span>
            </div>
          </button>

          {/* 5. Check finances & balances */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              if (onNavigateView) {
                onNavigateView('finance');
              } else {
                setValue('Check my current bank account balance and review recent transactions.');
                textareaRef.current?.focus();
              }
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--green">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="1" x2="12" y2="23" />
                <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Check finances &amp; balances</span>
              <span className="chat-input__flyout-subtitle">Review accounts and balances</span>
            </div>
          </button>

          {/* 6. Schedule a task or reminder */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              if (onNavigateView) {
                onNavigateView('jobs');
              } else {
                setValue('Schedule a reminder for tomorrow at 10 AM to: ');
                textareaRef.current?.focus();
              }
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--blue">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Schedule a task or reminder</span>
              <span className="chat-input__flyout-subtitle">Automate jobs and reminders</span>
            </div>
          </button>

          {/* 7. Create image */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Create an image of: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--cyan">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Create image</span>
              <span className="chat-input__flyout-subtitle">Visualize anything with diffusion</span>
            </div>
          </button>

          {/* 8. Maps */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Find places near: ');
              setTimeout(() => {
                if (textareaRef.current) {
                  textareaRef.current.focus();
                  const len = textareaRef.current.value.length;
                  textareaRef.current.setSelectionRange(len, len);
                }
              }, 50);
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--pin">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Maps</span>
              <span className="chat-input__flyout-subtitle">Find Nearby Places</span>
            </div>
          </button>

          {/* 9. Deep research */}
          <button
            type="button"
            className="chat-input__flyout-item"
            role="menuitem"
            onClick={() => {
              setShowToolsMenu(false);
              setValue('Conduct deep research on: ');
              textareaRef.current?.focus();
            }}
          >
            <div className="chat-input__flyout-icon chat-input__flyout-icon--telescope">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
                <line x1="11" y1="8" x2="11" y2="14" />
                <line x1="8" y1="11" x2="14" y2="11" />
              </svg>
            </div>
            <div className="chat-input__flyout-text">
              <span className="chat-input__flyout-title">Deep research</span>
              <span className="chat-input__flyout-subtitle">Get a detailed report</span>
            </div>
          </button>

        </div>
      )}

      {/* Attached Files Chips Bar */}
      {attachedFiles.length > 0 && (
        <div className="chat-input__attached-bar">
          {attachedFiles.map((file, idx) => (
            <div key={`${file.name}-${idx}`} className="chat-input__file-chip">
              <span className="chat-input__chip-icon">{getFileIcon(file.name)}</span>
              <span className="chat-input__chip-name" title={file.name}>{file.name}</span>
              <span className="chat-input__chip-size">{(file.size / 1024).toFixed(0)}KB</span>
              <button
                type="button"
                className="chat-input__chip-remove"
                onClick={() => removeAttachedFile(idx)}
                aria-label={`Remove ${file.name}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Capsule Render: recording vs transcribing vs normal */}
      {dictationState === 'recording' ? (
        <div className="chat-input__capsule chat-input__capsule--dictating">
          {/* ✕ Cancel Button */}
          <button
            type="button"
            className="chat-input__dictate-cancel-btn"
            onClick={cancelDictation}
            title="Cancel dictation (Esc)"
            aria-label="Cancel dictation"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          {/* Center Dynamic Audio Waveform */}
          <div className="chat-input__dictate-waveform" aria-label="Recording audio">
            {audioLevels.map((lvl, idx) => (
              <span
                key={idx}
                className="chat-input__dictate-bar"
                style={{ height: `${lvl}px` }}
              />
            ))}
          </div>

          {/* Right Action Buttons: Stop (■) and Send (↑) */}
          <div className="chat-input__dictate-actions">
            <button
              type="button"
              className="chat-input__dictate-stop-btn"
              onClick={finishDictation}
              title="Done dictating — transcribe"
              aria-label="Stop dictation"
            >
              <span className="chat-input__dictate-stop-icon" />
            </button>

            <button
              type="button"
              className="chat-input__dictate-send-btn"
              onClick={sendWhileDictating}
              title="Send message"
              aria-label="Send message"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </div>
      ) : dictationState === 'transcribing' ? (
        <div className="chat-input__capsule chat-input__capsule--transcribing">
          <div className="chat-input__transcribing-box">
            <span className="chat-input__spinner" aria-hidden="true" />
            <span className="chat-input__transcribing-label">Transcribing…</span>
          </div>
        </div>
      ) : (
        <div className="chat-input__capsule">
          {/* Left tools slot: Attachment (+), Direct Attach, and ModelPicker */}
          <div className="chat-input__left">
            <button
              ref={actionBtnRef}
              type="button"
              className={`chat-input__action-btn ${showToolsMenu ? 'chat-input__action-btn--active' : ''}`}
              onClick={() => setShowToolsMenu((prev) => !prev)}
              title="Add tools, files, and skills (+)"
              aria-label="Add options"
              aria-expanded={showToolsMenu}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>

            <button
              type="button"
              className="chat-input__action-btn"
              onClick={() => fileInputRef.current?.click()}
              title="Add files from device (PDFs, PPTs, images, videos, code)"
              aria-label="Add files from device"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>
            {leftSlot}
          </div>

          {/* Text & Code Textarea */}
          <textarea
            ref={textareaRef}
            className="chat-input__textarea"
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || isStreaming || disabledNoModel}
            rows={1}
            aria-label="Message input"
            aria-multiline="true"
          />

          {/* Right tools slot: Think button, Mic button, and Send / Voice Mode button */}
          <div className="chat-input__right">
            {/* Think Toggle Button */}
            <button
              type="button"
              className={`chat-input__think-btn ${thinkMode ? 'chat-input__think-btn--active' : ''}`}
              onClick={() => setThinkMode((prev) => !prev)}
              title={thinkMode ? 'Deep reasoning enabled' : 'Enable deep reasoning (Think)'}
              aria-label={thinkMode ? 'Deep reasoning enabled' : 'Enable deep reasoning (Think)'}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <span>Think</span>
            </button>

            {/* Voice dictation mic button */}
            <button
              type="button"
              className="chat-input__mic-btn"
              onClick={toggleVoiceDictation}
              title="Dictate with voice (Ctrl+Shift+D)"
              aria-label="Dictate with voice"
              disabled={disabled || isStreaming || disabledNoModel}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </button>

            {/* If there is content: show Send (↑) button. If empty and onVoiceClick provided: show interactive Voice button */}
            {hasContent || isStreaming || !onVoiceClick ? (
              <button
                type="submit"
                className={`chat-input__send-btn ${hasContent ? 'chat-input__send-btn--ready' : ''}`}
                disabled={!hasContent || disabled || isStreaming || disabledNoModel}
                aria-label="Send message"
              >
                {isStreaming ? (
                  <span className="chat-input__spinner" aria-hidden="true" />
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="19" x2="12" y2="5" />
                    <polyline points="5 12 12 5 19 12" />
                  </svg>
                )}
              </button>
            ) : (
              <button
                type="button"
                className="chat-input__voice-mode-btn"
                onClick={onVoiceClick}
                title="Talk out loud with ROXY AI using Voice"
                aria-label="Talk out loud with ROXY AI using Voice"
              >
                <div className="chat-input__waveform">
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
              </button>
            )}
          </div>
        </div>
      )}

      <div className="chat-input__footer">
        <span className="chat-input__shortcut-hint">
          <strong>Enter</strong> to send · <strong>Shift + Enter</strong> for new line · <strong>Tab</strong> to indent code
        </span>
      </div>
    </form>
  );
};
