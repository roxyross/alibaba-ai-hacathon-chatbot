"use client";

import React, { useState } from "react";

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
  const [isAnswering, setIsAnswering] = useState(false);

  const [docs, setDocs] = useState<VaultDoc[]>([
    {
      id: "1",
      filename: "Company_Financial_Forecast_2026.pdf",
      folder: "Finance",
      size: "2.4 MB",
      updatedAt: "2 days ago",
      status: "Indexed"
    },
    {
      id: "2",
      filename: "Raast_PISP_Mode_Integration_Spec.docx",
      folder: "Engineering",
      size: "1.1 MB",
      updatedAt: "Yesterday",
      status: "Indexed"
    },
    {
      id: "3",
      filename: "AI_Agent_Architecture_V2.pdf",
      folder: "Research",
      size: "4.8 MB",
      updatedAt: "3 hours ago",
      status: "Indexed"
    }
  ]);

  const folders = ["All", "Finance", "Engineering", "Research", "Legal"];

  const filteredDocs = docs.filter(d => {
    const matchesFolder = selectedFolder === "All" || d.folder === selectedFolder;
    const matchesSearch = d.filename.toLowerCase().includes(search.toLowerCase());
    return matchesFolder && matchesSearch;
  });

  const handleAskVault = () => {
    if (!groundedQuery.trim() || isAnswering) return;
    setIsAnswering(true);
    setGroundedAnswer(null);

    setTimeout(() => {
      setGroundedAnswer(
        `Based on indexed documents in your Vault (${docs.map(d => d.filename).slice(0, 2).join(", ")}): ` +
        `The operational architecture specifies dual Raast PISP and Plaid webhooks, scheduled daily reconciliations at 09:00, and NeonDB PostgreSQL for relational persistence.`
      );
      setIsAnswering(false);
    }, 1200);
  };

  const handleUploadSimulate = (name: string, folder: string) => {
    const newDoc: VaultDoc = {
      id: Date.now().toString(),
      filename: name.endsWith(".pdf") ? name : `${name}.pdf`,
      folder: folder || "General",
      size: "1.5 MB",
      updatedAt: "Just now",
      status: "Indexed"
    };
    setDocs(prev => [newDoc, ...prev]);
    setUploadModalOpen(false);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
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

      {/* Main Grid: Document List on Left (8 cols) + Grounded Query on Right (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Document Explorer (8 cols) */}
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
                        onClick={() => setDocs(prev => prev.filter(d => d.id !== doc.id))}
                        className="text-slate-400 hover:text-rose-600 font-medium transition-colors"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Grounded Chat Panel (4 cols) */}
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
                <button
                  onClick={() => setGroundedAnswer(null)}
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
              />
              <button
                onClick={handleAskVault}
                disabled={!groundedQuery.trim() || isAnswering}
                className="px-3 py-1.5 bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-50 text-white rounded-lg text-xs font-semibold shadow-sm transition-all"
              >
                Ask
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Document Modal */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-md w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h3 className="text-sm font-bold text-[#1e292b]">Upload to Knowledge Vault</h3>
              <button
                onClick={() => setUploadModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="border-2 border-dashed border-slate-300 hover:border-[#0d9488] rounded-xl p-6 text-center transition-colors cursor-pointer bg-slate-50">
              <span className="text-3xl">📥</span>
              <p className="text-xs font-semibold text-slate-700 mt-2">Click or drag & drop files here</p>
              <p className="text-[10px] text-slate-400 mt-1">PDF, DOCX, TXT, CSV, MD up to 25MB</p>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700">Quick Test Upload</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => handleUploadSimulate("Product_Security_Audit_Report.pdf", "Engineering")}
                  className="flex-1 py-1.5 px-2 bg-slate-100 hover:bg-slate-200 rounded-lg text-[11px] font-medium text-slate-800 transition-colors"
                >
                  + Add Security Audit
                </button>
                <button
                  type="button"
                  onClick={() => handleUploadSimulate("Quarterly_Tax_PISP_Guide.pdf", "Finance")}
                  className="flex-1 py-1.5 px-2 bg-slate-100 hover:bg-slate-200 rounded-lg text-[11px] font-medium text-slate-800 transition-colors"
                >
                  + Add Tax Guide
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
