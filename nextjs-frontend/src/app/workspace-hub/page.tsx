"use client";

import React, { useState } from "react";

interface ProjectItem {
  id: string;
  name: string;
  description: string;
  status: "Active" | "Planning" | "Review" | "Completed";
  updatedAt: string;
  tasksCount: number;
  category: string;
}

export default function WorkspaceHubPage() {
  const [filter, setFilter] = useState("All");
  const [modalOpen, setModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");

  const [projects, setProjects] = useState<ProjectItem[]>([
    {
      id: "1",
      name: "Raast PISP Integration Phase 2",
      description: "Direct instant bank-to-bank settlement pipeline with State Bank of Pakistan standards.",
      status: "Active",
      updatedAt: "Today",
      tasksCount: 8,
      category: "Fintech"
    },
    {
      id: "2",
      name: "Autonomous AI Gateway Benchmarking",
      description: "Evaluation and latency testing across Gemini 2.5 Flash, Grok 2, and Qwen 2.5 72B.",
      status: "Active",
      updatedAt: "Yesterday",
      tasksCount: 14,
      category: "AI & ML"
    },
    {
      id: "3",
      name: "Global Multi-Currency Billing Engine",
      description: "Seamless dual currency ($ USD and Rs PKR) invoices, webhooks, and Stripe integration.",
      status: "Review",
      updatedAt: "3 days ago",
      tasksCount: 5,
      category: "Infrastructure"
    },
    {
      id: "4",
      name: "Mobile Responsive Layout Migration",
      description: "Next.js 15 App Router and Tailwind CSS responsive interface optimization.",
      status: "Completed",
      updatedAt: "Last week",
      tasksCount: 12,
      category: "Design"
    }
  ]);

  const filteredProjects = projects.filter(p => {
    if (filter === "All") return true;
    return p.status === filter;
  });

  const handleCreate = () => {
    if (!newProjectName.trim()) return;
    const item: ProjectItem = {
      id: Date.now().toString(),
      name: newProjectName.trim(),
      description: newProjectDesc.trim() || "New workspace project",
      status: "Active",
      updatedAt: "Just now",
      tasksCount: 0,
      category: "General"
    };
    setProjects(prev => [item, ...prev]);
    setNewProjectName("");
    setNewProjectDesc("");
    setModalOpen(false);
  };

  const getStatusBadge = (status: ProjectItem["status"]) => {
    switch (status) {
      case "Active":
        return "bg-teal-50 text-[#0d9488] border-teal-200";
      case "Planning":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "Review":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "Completed":
        return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-[#1e292b]">Workspace Hub</h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
              {projects.length} Projects
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Organize long-running initiatives, research artifacts, and multi-agent coordination.
          </p>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#0d9488] hover:bg-[#0f766e] text-white transition-colors flex items-center gap-1.5 shadow-sm"
        >
          <span>+</span>
          <span>New Project</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2 border-b border-slate-200 pb-3">
        {["All", "Active", "Planning", "Review", "Completed"].map((tab) => (
          <button
            key={tab}
            onClick={() => setFilter(tab)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === tab
                ? "bg-[#1e292b] text-white"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Projects Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredProjects.map((p) => (
          <div
            key={p.id}
            className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                  {p.category}
                </span>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${getStatusBadge(p.status)}`}>
                  {p.status}
                </span>
              </div>
              <h3 className="text-sm font-bold text-[#1e292b] mb-1.5 leading-snug">
                {p.name}
              </h3>
              <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                {p.description}
              </p>
            </div>

            <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
              <span>{p.tasksCount} active tasks · {p.updatedAt}</span>
              <button
                onClick={() => alert(`Opening workspace context for ${p.name}`)}
                className="text-[#0d9488] font-semibold hover:underline"
              >
                Open →
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* New Project Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-sm font-bold text-[#1e292b]">Create New Project</h3>
              <button
                onClick={() => setModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Project Name</label>
                <input
                  type="text"
                  placeholder="e.g. Q4 Growth & Automations"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-[#0d9488]"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Description</label>
                <textarea
                  rows={3}
                  placeholder="Describe the scope, goals, or connected tools..."
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-[#0d9488] resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={!newProjectName.trim()}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-50 text-white"
              >
                Create Project
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
