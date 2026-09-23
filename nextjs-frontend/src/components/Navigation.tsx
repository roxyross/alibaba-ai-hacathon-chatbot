"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navigation() {
  const pathname = usePathname();
  const [pinMenuOpen, setPinMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [pinnedItems, setPinnedItems] = useState<string[]>([
    "Q3 Tax filing checklist for Raast",
    "Product Roadmap sprint 12 draft",
    "Scheduled daily market brief at 09:00"
  ]);

  const removePin = (item: string) => {
    setPinnedItems(prev => prev.filter(p => p !== item));
  };

  const navLinks = [
    { href: "/", label: "Chat", icon: "💬" },
    { href: "/coding", label: "Coding", icon: "💻" },
    { href: "/memory", label: "Memory", icon: "🧠" },
    { href: "/audit", label: "Audit", icon: "🛡️" },
    { href: "/study", label: "Study", icon: "🎓" },
    { href: "/browser", label: "Browser", icon: "🌐" },
    { href: "/research", label: "Research", icon: "🔬" },
    { href: "/voice", label: "Voice", icon: "🎙️" },
    { href: "/calendar", label: "Calendar", icon: "📅" },
    { href: "/email", label: "Email", icon: "📧" },
    { href: "/image-studio", label: "Image Studio", icon: "🎨" },
    { href: "/knowledge-vault", label: "Knowledge Vault", icon: "📚" },
    { href: "/workspace-hub", label: "Workspace Hub", icon: "📁" },
    { href: "/scheduled-jobs", label: "Scheduled", icon: "⏰" },
    { href: "/finance", label: "Finance", icon: "💳" },
    { href: "/usage", label: "Usage", icon: "📊" },
    { href: "/billing", label: "Billing", icon: "📑" },
  ];

  return (
    <header className="sticky top-0 z-50 bg-[#f8faf9]/90 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 group">
            <span className="text-xl">☀️</span>
            <span className="font-bold text-lg tracking-tight text-[#1e292b] group-hover:text-[#0d9488] transition-colors">
              ROXY <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200 ml-1">AI</span>
            </span>
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden lg:flex items-center gap-1">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 ${
                    isActive
                      ? "bg-teal-50 text-[#0d9488] font-semibold"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                  }`}
                >
                  <span>{link.icon}</span>
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2.5">
          {/* Interactive Pin Menu */}
          <div className="relative">
            <button
              onClick={() => setPinMenuOpen(!pinMenuOpen)}
              className="p-2 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-lg text-sm transition-colors relative"
              title="Pinned items (Click to view saved chats, tools & statements)"
            >
              📌
              {pinnedItems.length > 0 && (
                <span className="absolute top-1 right-1 w-2 h-2 bg-[#0d9488] rounded-full" />
              )}
            </button>

            {pinMenuOpen && (
              <div className="absolute right-0 mt-2 w-72 bg-white rounded-xl shadow-xl border border-slate-200 p-3 z-50 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-100">
                  <span className="text-xs font-bold text-[#1e292b] uppercase tracking-wider flex items-center gap-1.5">
                    📌 Pinned Items
                  </span>
                  <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">
                    {pinnedItems.length}
                  </span>
                </div>
                {pinnedItems.length === 0 ? (
                  <p className="text-xs text-slate-400 py-3 text-center">No pinned items yet</p>
                ) : (
                  <ul className="space-y-1.5 max-h-60 overflow-y-auto">
                    {pinnedItems.map((item, i) => (
                      <li
                        key={i}
                        className="text-xs text-slate-700 bg-slate-50 hover:bg-slate-100 p-2 rounded-lg flex items-center justify-between gap-2 group transition-colors"
                      >
                        <span className="truncate">{item}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            removePin(item);
                          }}
                          className="text-slate-400 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity text-xs"
                          title="Unpin"
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* ⚡ Upgrade Button (Directly before Sign In) */}
          <Link
            href="/pricing"
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-white text-[#0d9488] border border-teal-200 hover:border-teal-400 hover:bg-teal-50 shadow-sm transition-all"
          >
            <span>⚡</span>
            <span>Upgrade</span>
          </Link>

          {/* Sign In Button */}
          <button className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-[#1e292b] text-white hover:bg-black transition-colors shadow-sm">
            Sign In
          </button>

          {/* Mobile menu toggle */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden p-2 text-slate-600 hover:bg-slate-100 rounded-lg text-base"
          >
            ☰
          </button>
        </div>
      </div>

      {/* Mobile Nav Drawer */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-t border-slate-200 bg-[#f8faf9] px-4 py-3 space-y-1">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                pathname === link.href
                  ? "bg-teal-50 text-[#0d9488]"
                  : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              <span>{link.icon}</span>
              <span>{link.label}</span>
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
