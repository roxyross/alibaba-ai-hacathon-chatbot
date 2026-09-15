"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

const GREETINGS_MAP: Record<string, string> = {
  "hello": "Hello! Welcome to Roxy AI. How can I assist you today?",
  "hi": "Hi there! Great to see you. What are we creating or solving today?",
  "assalam o alaikum": "Assalam o Alaikum! Welcome back to Roxy AI. How may I be of service today?",
  "salam": "Walaikum Assalam! Roxy is ready when you are. What's on your mind?",
  "hola": "¡Hola! Bienvenido a Roxy AI. ¿En qué puedo ayudarte hoy?",
  "bonjour": "Bonjour! Bienvenue sur Roxy AI. Comment puis-je vous aider aujourd'hui?",
  "namaste": "Namaste! Welcome to Roxy AI. How can I assist you today?",
  "marhaba": "Marhaba! Welcome to Roxy AI. How can I assist you today?",
  "ciao": "Ciao! Benvenuto in Roxy AI. Come posso aiutarti oggi?"
};

export default function ChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [greetingBanner, setGreetingBanner] = useState<string | null>(null);
  const [inputPrompt, setInputPrompt] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "Ready when you are. I can manage your workspace, schedule jobs, track finances across Plaid & Raast, generate images, and ground intelligence in your Knowledge Vault.",
      timestamp: "Just now"
    }
  ]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [plusMenuOpen, setPlusMenuOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gemini-2.5-flash");
  
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll when messages update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  // Speech to text toggle
  const toggleVoiceInput = () => {
    const SpeechRec = (typeof window !== "undefined" && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));

    if (!SpeechRec) {
      alert("Speech recognition is not supported in this browser. Please use Google Chrome or Edge.");
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
      recognition.lang = "en-US";

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setInputPrompt(prev => prev ? `${prev} ${transcript}` : transcript);
      };

      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleSend = () => {
    const text = inputPrompt.trim();
    if (!text || isGenerating) return;

    // Detect greeting in user message
    const lower = text.toLowerCase();
    for (const [key, greetingText] of Object.entries(GREETINGS_MAP)) {
      if (lower.startsWith(key) || lower.includes(key)) {
        setGreetingBanner(greetingText);
        break;
      }
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    setMessages(prev => [...prev, userMsg]);
    setInputPrompt("");
    setIsGenerating(true);

    // Simulate fast streaming response
    setTimeout(() => {
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `I've analyzed your request: "${text}". All systems are operational across the AI Gateway, NeonDB, and active tools. You can also view Scheduled Jobs, Finance telemetry, or Document Vault from the top bar.`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setMessages(prev => [...prev, assistantMsg]);
      setIsGenerating(false);
    }, 1200);
  };

  const handleStop = () => {
    setIsGenerating(false);
  };

  const handleReplyNow = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    textareaRef.current?.focus();
  };

  const previousConversations = [
    { title: "Raast PISP Mode settlement setup", date: "Today" },
    { title: "Q3 financial forecast & invoices", date: "Yesterday" },
    { title: "Weekly cron schedule for report emails", date: "3 days ago" },
    { title: "Logo concepts & marketing variations", date: "Last week" }
  ].filter(c => c.title.toLowerCase().includes(searchQuery.toLowerCase()));

  return (
    <div className="flex-1 flex h-[calc(100vh-4rem)] overflow-hidden bg-[#f8faf9]">
      {/* Collapsible Left Sidebar */}
      {sidebarOpen ? (
        <aside className="w-64 border-r border-slate-200 bg-white/70 backdrop-blur-sm flex flex-col transition-all duration-300">
          <div className="p-3 border-b border-slate-100 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">Conversations</span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="text-xs text-slate-400 hover:text-slate-700 p-1 rounded hover:bg-slate-100 transition-colors"
              title="Close Sidebar"
            >
              ✕ Close
            </button>
          </div>

          {/* Search bar */}
          <div className="p-3 border-b border-slate-100">
            <div className="relative">
              <span className="absolute left-2.5 top-2 text-xs text-slate-400">🔍</span>
              <input
                type="text"
                placeholder="Search history..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0d9488]"
              />
            </div>
          </div>

          {/* Conversation history list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            <button
              onClick={() => {
                setMessages([
                  {
                    id: Date.now().toString(),
                    role: "assistant",
                    content: "Ready when you are. How can I assist you with your project today?",
                    timestamp: "Just now"
                  }
                ]);
                setGreetingBanner(null);
              }}
              className="w-full text-left px-3 py-2 text-xs font-semibold text-[#0d9488] bg-teal-50 hover:bg-teal-100 rounded-lg transition-colors flex items-center gap-2 mb-2"
            >
              <span>+</span>
              <span>New Conversation</span>
            </button>

            {previousConversations.map((conv, i) => (
              <div
                key={i}
                className="px-3 py-2 rounded-lg text-xs text-slate-700 hover:bg-slate-100 cursor-pointer transition-colors group flex items-center justify-between"
              >
                <div className="truncate flex-1">
                  <p className="font-medium truncate">{conv.title}</p>
                  <p className="text-[10px] text-slate-400">{conv.date}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Sidebar footer */}
          <div className="p-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span className="text-[11px]">Personal AI Engine</span>
            <Link href="/usage" className="hover:text-[#0d9488] transition-colors text-[11px] font-medium">
              View Stats →
            </Link>
          </div>
        </aside>
      ) : (
        <button
          onClick={() => setSidebarOpen(true)}
          className="fixed left-3 top-20 z-40 bg-white border border-slate-200 shadow-md p-2 rounded-lg text-xs text-slate-700 hover:bg-slate-50 hover:text-[#0d9488] transition-all flex items-center gap-1"
          title="Open Sidebar"
        >
          <span>📂</span>
          <span className="hidden sm:inline">Open Sidebar</span>
        </button>
      )}

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Warm Greeting Banner if detected */}
        {greetingBanner && (
          <div className="bg-teal-50 border-b border-teal-100 px-6 py-3 flex items-center justify-between animate-in fade-in slide-in-from-top-2">
            <div className="flex items-center gap-2.5">
              <span className="text-base">☀️</span>
              <span className="text-xs font-medium text-[#0d9488]">{greetingBanner}</span>
            </div>
            <button
              onClick={() => setGreetingBanner(null)}
              className="text-xs text-teal-600 hover:text-teal-800 p-1"
            >
              ✕
            </button>
          </div>
        )}

        {/* Messages Scroll Area */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-4">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center text-sm flex-shrink-0">
                    ☀️
                  </div>
                )}
                <div
                  className={`max-w-[85%] sm:max-w-[75%] rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-[#1e292b] text-white rounded-br-sm shadow-sm"
                      : "bg-white border border-slate-200 text-slate-800 rounded-bl-sm shadow-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  <span className={`block text-[10px] mt-1.5 text-right ${msg.role === "user" ? "text-slate-400" : "text-slate-400"}`}>
                    {msg.timestamp}
                  </span>
                </div>
              </div>
            ))}

            {/* Thinking / Tool Execution State */}
            {isGenerating && (
              <div className="flex gap-3 items-center">
                <div className="w-8 h-8 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center text-sm animate-pulse">
                  ☀️
                </div>
                <div className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm flex items-center gap-3">
                  <div className="flex gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-[#0d9488] animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-2 h-2 rounded-full bg-[#0d9488] animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-2 h-2 rounded-full bg-[#0d9488] animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                  <span className="text-xs text-slate-500 font-medium">Thinking & synthesizing...</span>
                  <div className="flex items-center gap-1.5 ml-2">
                    <button
                      onClick={handleStop}
                      className="px-2 py-1 text-[11px] font-semibold text-rose-600 bg-rose-50 hover:bg-rose-100 rounded border border-rose-200 transition-colors"
                    >
                      ■ Stop
                    </button>
                    <button
                      onClick={handleReplyNow}
                      className="px-2 py-1 text-[11px] font-semibold text-[#0d9488] bg-teal-50 hover:bg-teal-100 rounded border border-teal-200 transition-colors"
                    >
                      Reply now
                    </button>
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input Bar Section */}
        <div className="border-t border-slate-200 bg-white/80 backdrop-blur-md p-4">
          <div className="max-w-3xl mx-auto space-y-2">
            {/* Quick Actions / Model Selector */}
            <div className="flex items-center justify-between text-xs text-slate-500">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-700">Model:</span>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="bg-slate-50 border border-slate-200 rounded-md px-2 py-1 text-xs text-slate-800 focus:outline-none focus:border-[#0d9488]"
                >
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
                  <option value="grok-beta">Grok Beta</option>
                  <option value="qwen-2.5-72b">Qwen 2.5 72B</option>
                </select>
              </div>
              <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400">
                <span>Enter to send</span>
                <span>·</span>
                <span>Shift+Enter new line</span>
              </div>
            </div>

            {/* Input Box */}
            <div className="relative flex items-center bg-white border border-slate-200 rounded-xl shadow-sm focus-within:border-[#0d9488] focus-within:ring-1 focus-within:ring-[#0d9488] transition-all">
              {/* Plus Menu Button */}
              <div className="relative pl-2">
                <button
                  type="button"
                  onClick={() => setPlusMenuOpen(!plusMenuOpen)}
                  className="w-8 h-8 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 flex items-center justify-center text-lg transition-colors"
                  title="Attach tools or files"
                >
                  +
                </button>

                {plusMenuOpen && (
                  <div className="absolute bottom-11 left-0 w-52 bg-white rounded-xl shadow-xl border border-slate-200 p-2 z-50">
                    <Link
                      href="/image-studio"
                      onClick={() => setPlusMenuOpen(false)}
                      className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2"
                    >
                      <span>🎨</span>
                      <span>Generate Image</span>
                    </Link>
                    <Link
                      href="/knowledge-vault"
                      onClick={() => setPlusMenuOpen(false)}
                      className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2"
                    >
                      <span>📁</span>
                      <span>Upload Document</span>
                    </Link>
                    <Link
                      href="/scheduled-jobs"
                      onClick={() => setPlusMenuOpen(false)}
                      className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2"
                    >
                      <span>⏰</span>
                      <span>Schedule Cron Job</span>
                    </Link>
                    <Link
                      href="/finance"
                      onClick={() => setPlusMenuOpen(false)}
                      className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2"
                    >
                      <span>💳</span>
                      <span>Check Raast / Plaid</span>
                    </Link>
                  </div>
                )}
              </div>

              {/* Textarea */}
              <textarea
                ref={textareaRef}
                rows={1}
                placeholder="Think or ask anything in any language..."
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                className="flex-1 py-3 px-3 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:outline-none resize-none bg-transparent"
              />

              {/* Mic & Send Buttons */}
              <div className="flex items-center gap-1.5 pr-2.5">
                <button
                  type="button"
                  onClick={toggleVoiceInput}
                  className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors text-sm ${
                    isListening
                      ? "bg-rose-50 text-rose-600 animate-pulse border border-rose-200"
                      : "text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                  }`}
                  title={isListening ? "Listening... (Click to stop)" : "Speak your prompt"}
                >
                  🎙️
                </button>

                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!inputPrompt.trim() || isGenerating}
                  className="w-8 h-8 rounded-full bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-40 disabled:hover:bg-[#0d9488] text-white flex items-center justify-center text-sm shadow-sm transition-all"
                  title="Send message"
                >
                  ↑
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
