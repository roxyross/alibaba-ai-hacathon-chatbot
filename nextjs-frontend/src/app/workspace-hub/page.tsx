"use client";

import React, { useState, useEffect, useCallback } from "react";

interface ProjectItem {
  id: string;
  name: string;
  description: string;
  status: "active" | "in_progress" | "archived" | "completed";
  lastUpdated: string;
  tasksCount: number;
  completedCount: number;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function WorkspaceHubPage() {
  const [filter, setFilter] = useState("All");
  const [modalOpen, setModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("accessToken") || localStorage.getItem("roxy_token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const statusParam = filter !== "All" ? `?status=${filter.toLowerCase().replace(" ", "_")}` : "";
      const res = await fetch(`${API_BASE}/projects${statusParam}`, { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.projects)) {
          setProjects(
            data.projects.map((p: any) => ({
              id: p.id,
              name: p.name,
              description: p.description || "",
              status: p.status || "active",
              lastUpdated: p.last_updated || "Recently",
              tasksCount: p.tasks_count || 0,
              completedCount: p.completed_count || 0,
            }))
          );
        }
      } else {
        setErrorMessage("Failed to load workspace projects.");
      }
    } catch {
      // Offline or guest mode zeroed projects
      setProjects([]);
    } finally {
      setIsLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async () => {
    if (!newProjectName.trim()) return;
    setErrorMessage(null);

    const token = typeof window !== "undefined" ? localStorage.getItem("accessToken") || localStorage.getItem("roxy_token") : null;
    if (!token) {
      setErrorMessage("Please sign in to create and persist workspace projects.");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newProjectName.trim(),
          description: newProjectDesc.trim() || "Workspace project",
          status: "active",
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const p = data.project;
        setProjects((prev) => [
          {
            id: p.id,
            name: p.name,
            description: p.description,
            status: p.status || "active",
            lastUpdated: p.last_updated || "Just now",
            tasksCount: 0,
            completedCount: 0,
          },
          ...prev,
        ]);
        setNewProjectName("");
        setNewProjectDesc("");
        setModalOpen(false);
        setNotification(`Created project "${p.name}".`);
        setTimeout(() => setNotification(null), 4000);
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMessage(err.detail || "Could not create project.");
      }
    } catch {
      setErrorMessage("Network error while creating project.");
    }
  };

  const getStatusBadge = (status: ProjectItem["status"]) => {
    switch (status) {
      case "active":
        return "bg-teal-50 text-[#0d9488] border-teal-200";
      case "in_progress":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "archived":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "completed":
        return "bg-slate-100 text-slate-700 border-slate-200";
      default:
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

      {notification && (
        <div className="p-3.5 bg-teal-50 border border-teal-200 rounded-xl text-xs font-semibold text-[#0d9488]">
          ✨ {notification}
        </div>
      )}

      {errorMessage && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs font-semibold text-rose-600 flex items-center justify-between">
          <span>⚠️ {errorMessage}</span>
          <button onClick={() => setErrorMessage(null)} className="font-bold text-sm">✕</button>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex gap-2 border-b border-slate-200 pb-3">
        {["All", "Active", "In Progress", "Completed", "Archived"].map((tab) => (
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
      {projects.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center text-slate-500">
          <div className="text-3xl mb-2">📁</div>
          <p className="text-sm font-semibold text-slate-700">No workspace projects found</p>
          <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
            Create your first project to organize tasks, link Knowledge Vault documents, and orchestrate agent tasks.
          </p>
          <button
            onClick={() => setModalOpen(true)}
            className="mt-4 px-4 py-2 rounded-xl text-xs font-semibold bg-[#0d9488] hover:bg-[#0f766e] text-white transition-all"
          >
            + Create Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((p) => (
            <div
              key={p.id}
              className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Workspace
                  </span>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${getStatusBadge(p.status)}`}>
                    {p.status.replace("_", " ")}
                  </span>
                </div>
                <h3 className="text-sm font-bold text-[#1e292b] mb-1.5 leading-snug">
                  {p.name}
                </h3>
                <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                  {p.description || "No project description provided."}
                </p>
              </div>

              <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span>
                  {p.completedCount}/{p.tasksCount} tasks · Updated {p.lastUpdated}
                </span>
                <span className="text-[#0d9488] font-semibold">
                  Active
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

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
                  placeholder="e.g. Q4 Autonomous Workflows"
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
