"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

interface VaultDoc {
  id: string;
  filename: string;
  folder: string;
  size: string;
  updatedAt: string;
  status: "Indexed" | "Processing";
}

export default function KnowledgeVaultPage() {
  const [search, setSearch] = useState("");
  const [selectedFolder, setSelectedFolder] = useState("All");
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [groundedQuery, setGroundedQuery] = useState("");
  const [groundedAnswer, setGroundedAnswer] = useState<string | null>(null);
  const [groundedSources, setGroundedSources] = useState<string[]>([]);
  const [isAnswering, setIsAnswering] = useState(false);
  const [docs, setDocs] = useState<VaultDoc[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocs = useCallback(async () => {
    setIsLoading(true);
    setErrorBanner(null);
    try {
      const res = await fetch("/api/v1/documents");
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.documents)) {
          setDocs(
            data.documents.map((d: any) => ({
              id: d.document_id,
              filename: d.document_name,
              folder: "General",
              size: `${d.chunk_count || 1} chunks`,
              updatedAt: d.last_ingested ? new Date(d.last_ingested).toLocaleDateString() : "Recently",
              status: "Indexed",
            }))
          );
        }
      } else if (res.status === 401) {
        // Unauthenticated guest mode in Next.js companion
        setDocs([]);
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorBanner(err.detail || `Server returned error (${res.status})`);
      }
    } catch {
      // Offline / standalone mode: empty state
      setDocs([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const folders = ["All", "Finance", "Engineering", "Research", "General"];

  const filteredDocs = docs.filter((d) => {
    const matchesFolder = selectedFolder === "All" || d.folder === selectedFolder;
    const matchesSearch = d.filename.toLowerCase().includes(search.toLowerCase());
    return matchesFolder && matchesSearch;
  });

  const handleAskVault = async () => {
    if (!groundedQuery.trim() || isAnswering) return;
    const q = groundedQuery;
    setIsAnswering(true);
    setGroundedAnswer(null);
    setGroundedSources([]);

    try {
      const res = await fetch("/api/v1/documents/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });

      if (res.ok) {
        const data = await res.json();
        setGroundedAnswer(data.answer || "No matching citations found in indexed documents.");
        if (Array.isArray(data.sources)) {
          setGroundedSources(data.sources);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        setGroundedAnswer(`⚠️ Query could not be completed: ${err.detail || "Server error"}`);
      }
    } catch (err: any) {
      setGroundedAnswer(`⚠️ Unable to reach Knowledge Vault service: ${err?.message || "Connection error"}.`);
    } finally {
      setIsAnswering(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 50 * 1024 * 1024) {
      setToastMessage({ type: "error", text: "File exceeds maximum size of 50 MB." });
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("document_name", file.name);

      const res = await fetch("/api/v1/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const newDoc: VaultDoc = {
          id: data.document_id || `doc-${Date.now()}`,
          filename: data.document_name || file.name,
          folder: selectedFolder === "All" ? "General" : selectedFolder,
          size: `${data.chunks_stored || 1} chunks`,
          updatedAt: "Just now",
          status: "Indexed",
        };
        setDocs((prev) => [newDoc, ...prev]);
        setToastMessage({ type: "success", text: `Successfully indexed "${file.name}".` });
        setUploadModalOpen(false);
      } else {
        const err = await res.json().catch(() => ({}));
        setToastMessage({ type: "error", text: err.detail || `Upload failed: ${res.status}` });
      }
    } catch (err: any) {
      setToastMessage({ type: "error", text: err?.message || "Network error uploading file." });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    const confirmed = window.confirm(`Permanently remove "${filename}" and its vector embeddings from Knowledge Vault?`);
    if (!confirmed) return;

    const previousDocs = [...docs];
    setDocs((prev) => prev.filter((d) => d.id !== docId));

    try {
      const res = await fetch(`/api/v1/documents/${docId}`, { method: "DELETE" });
      if (res.ok) {
        setToastMessage({ type: "success", text: `"${filename}" removed from Knowledge Vault.` });
      } else {
        const err = await res.json().catch(() => ({}));
        setDocs(previousDocs);
        setToastMessage({ type: "error", text: err.detail || "Failed to delete document on server." });
      }
    } catch {
      setDocs(previousDocs);
      setToastMessage({ type: "error", text: "Connection error deleting document." });
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          className={`flex items-center justify-between p-3 rounded-xl text-xs font-medium ${
            toastMessage.type === "success"
              ? "bg-teal-50 border border-teal-200 text-teal-800"
              : "bg-rose-50 border border-rose-200 text-rose-800"
          }`}
        >
          <span>{toastMessage.text}</span>
          <button
            onClick={() => setToastMessage(null)}
            className="text-slate-400 hover:text-slate-700 ml-3 text-sm font-bold"
          >
            ✕
          </button>
        </div>
      )}

      {/* Connection Error Banner */}
      {errorBanner && (
        <div className="flex items-center justify-between p-4 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-800">
          <div className="flex items-center gap-2">
            <span className="text-base">⚠️</span>
            <span>{errorBanner}</span>
          </div>
          <button
            onClick={fetchDocs}
            className="px-3 py-1 bg-rose-600 text-white rounded-lg hover:bg-rose-700 font-semibold transition-colors"
          >
            ↻ Retry
          </button>
        </div>
      )}

      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-[#1e292b]">Knowledge Vault</h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
              RAG Grounded
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Store documents, whitepapers, and guides. Roxy synthesizes answers grounded strictly in your verified files.
          </p>
        </div>

        <button
          onClick={() => setUploadModalOpen(true)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#1e292b] text-white hover:bg-black transition-colors flex items-center gap-1.5 shadow-sm"
        >
          <span>+</span>
          <span>Upload Document</span>
        </button>
      </div>

      {/* Main Grid: Document List on Left + Grounded Query on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Document Explorer */}
        <div className="lg:col-span-7 xl:col-span-8 space-y-4">
          {/* Filter & Search Bar */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <span className="absolute left-3 top-2.5 text-xs text-slate-400">🔍</span>
              <input
                type="text"
                placeholder="Search documents by name..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-[#0d9488]"
              />
            </div>
            <div className="flex gap-1.5 overflow-x-auto pb-1">
              {folders.map((f) => (
                <button
                  key={f}
                  onClick={() => setSelectedFolder(f)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                    selectedFolder === f
                      ? "bg-[#0d9488] text-white"
                      : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* Documents Table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            {isLoading ? (
              <div className="py-12 text-center text-xs text-slate-500">
                <div className="w-6 h-6 border-2 border-[#0d9488] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <span>Loading Knowledge Vault...</span>
              </div>
            ) : filteredDocs.length === 0 ? (
              <div className="py-12 px-6 text-center space-y-2">
                <span className="text-3xl block">📂</span>
                <h4 className="text-sm font-bold text-slate-800">Your Knowledge Vault is empty</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Upload PDFs, Word documents, or spreadsheets to generate vector embeddings and enable RAG grounding.
                </p>
                <button
                  onClick={() => setUploadModalOpen(true)}
                  className="mt-2 px-3 py-1.5 text-xs font-semibold bg-[#0d9488] text-white rounded-lg hover:bg-[#0f766e] transition-colors"
                >
                  + Upload First Document
                </button>
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-3 px-4">Document Name</th>
                    <th className="py-3 px-4">Folder</th>
                    <th className="py-3 px-4">Size</th>
                    <th className="py-3 px-4">Updated</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredDocs.map((doc) => (
                    <tr key={doc.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-medium text-slate-800 flex items-center gap-2">
                        <span className="text-base">📄</span>
                        <span className="truncate max-w-[200px]">{doc.filename}</span>
                      </td>
                      <td className="py-3 px-4 text-slate-500">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-medium">
                          {doc.folder}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">{doc.size}</td>
                      <td className="py-3 px-4 text-slate-400 text-[11px]">{doc.updatedAt}</td>
                      <td className="py-3 px-4">
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#0d9488] bg-teal-50 px-2 py-0.5 rounded border border-teal-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#0d9488]" />
                          {doc.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => handleDelete(doc.id, doc.filename)}
                          className="text-slate-400 hover:text-rose-600 font-medium transition-colors"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Grounded Chat Panel */}
        <div className="lg:col-span-5 xl:col-span-4 bg-white rounded-2xl border border-slate-200 shadow-sm p-5 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center gap-2 pb-3 border-b border-slate-100">
              <span className="text-base">🧠</span>
              <h3 className="text-sm font-bold text-[#1e292b]">Grounded Vault Query</h3>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Ask questions strictly grounded in your uploaded documents. Roxy cites exact files and excerpts.
            </p>

            {groundedAnswer ? (
              <div className="mt-4 p-3.5 bg-teal-50/70 border border-teal-200 rounded-xl text-xs text-slate-800 leading-relaxed space-y-2">
                <p className="font-medium text-[#0d9488]">Grounded Answer:</p>
                <p>{groundedAnswer}</p>
                {groundedSources.length > 0 && (
                  <div className="pt-2 border-t border-teal-200/60">
                    <p className="text-[10px] font-bold uppercase text-slate-500 mb-1">Citations:</p>
                    <div className="flex flex-wrap gap-1">
                      {groundedSources.map((src, i) => (
                        <span key={i} className="px-1.5 py-0.5 rounded bg-teal-100/80 text-[#0d9488] text-[10px] font-medium">
                          📄 {src}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <button
                  onClick={() => {
                    setGroundedAnswer(null);
                    setGroundedSources([]);
                  }}
                  className="text-[11px] text-[#0d9488] font-semibold hover:underline block pt-1"
                >
                  Clear response
                </button>
              </div>
            ) : isAnswering ? (
              <div className="mt-6 py-8 text-center space-y-2">
                <div className="w-6 h-6 border-2 border-[#0d9488] border-t-transparent rounded-full animate-spin mx-auto" />
                <p className="text-xs text-slate-500">Searching indexed embeddings...</p>
              </div>
            ) : (
              <div className="mt-6 p-4 rounded-xl border border-dashed border-slate-200 text-center text-xs text-slate-400">
                Type a question below to query all {docs.length} indexed files.
              </div>
            )}
          </div>

          {/* Query Input */}
          <div className="pt-2">
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl p-1.5 focus-within:border-[#0d9488]">
              <input
                type="text"
                placeholder="Ask grounded question..."
                value={groundedQuery}
                onChange={(e) => setGroundedQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAskVault();
                  }
                }}
                className="flex-1 bg-transparent px-2 text-xs text-slate-800 focus:outline-none placeholder-slate-400"
                disabled={isAnswering}
              />
              <button
                onClick={handleAskVault}
                disabled={!groundedQuery.trim() || isAnswering}
                className="px-3 py-1.5 bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-50 text-white rounded-lg text-xs font-semibold shadow-sm transition-all"
              >
                {isAnswering ? "..." : "Ask"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Document Modal */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-sm font-bold text-[#1e292b]">Upload to Knowledge Vault</h3>
              <button
                onClick={() => setUploadModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 text-sm"
              >
                ✕
              </button>
            </div>

            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-300 hover:border-[#0d9488] rounded-xl p-6 text-center transition-colors cursor-pointer bg-slate-50"
            >
              <span className="text-3xl">📥</span>
              <p className="text-xs font-semibold text-slate-700 mt-2">
                {isUploading ? "Uploading & Generating Embeddings..." : "Click to select a file"}
              </p>
              <p className="text-[10px] text-slate-400 mt-1">PDF, DOCX, TXT, CSV, MD up to 50MB</p>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileUpload}
                accept=".pdf,.docx,.pptx,.txt,.csv,.md,.json"
                disabled={isUploading}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
