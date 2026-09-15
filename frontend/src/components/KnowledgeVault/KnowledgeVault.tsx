import React, { useState, useRef } from 'react';
import './KnowledgeVault.css';

interface DocItem {
  id: string;
  name: string;
  folder: string;
  size: string;
  updatedAt: string;
  snippet: string;
}

interface KnowledgeVaultProps {
  accessToken: string | null;
  onBack: () => void;
}

export const KnowledgeVault: React.FC<KnowledgeVaultProps> = ({ accessToken: _accessToken, onBack }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFolder, setSelectedFolder] = useState<string>('All');
  const [activeDoc, setActiveDoc] = useState<DocItem | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [vaultChatMessages, setVaultChatMessages] = useState<Array<{ sender: 'user' | 'assistant'; text: string }>>([
    { sender: 'assistant', text: 'Ask questions grounded directly in your private Knowledge Vault documents.' },
  ]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [documents, setDocuments] = useState<DocItem[]>([
    {
      id: 'doc-1',
      name: 'Q3_Financial_Analysis_Report.pdf',
      folder: 'Finance',
      size: '2.4 MB',
      updatedAt: 'Sep 12, 2026',
      snippet: 'Executive summary detailing operating margins, multi-currency revenue targets, and Raast transaction reconciliations.',
    },
    {
      id: 'doc-2',
      name: 'System_Architecture_Blueprint_v4.pdf',
      folder: 'Engineering',
      size: '4.8 MB',
      updatedAt: 'Sep 14, 2026',
      snippet: 'High level multi-agent event loop with fallback LLM providers, token rate limiting, and vector embeddings cache.',
    },
    {
      id: 'doc-3',
      name: 'Investor_Deck_Master_2026.pdf',
      folder: 'Strategy',
      size: '11.2 MB',
      updatedAt: 'Sep 10, 2026',
      snippet: 'Pitch deck outlining market expansion for autonomous operating AI assistants in emerging markets.',
    },
  ]);

  const folders = ['All', 'Finance', 'Engineering', 'Strategy', 'General'];

  const filteredDocs = documents.filter((doc) => {
    const matchesFolder = selectedFolder === 'All' || doc.folder === selectedFolder;
    const matchesSearch =
      doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.snippet.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFolder && matchesSearch;
  });

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const newDoc: DocItem = {
      id: `doc-${Date.now()}`,
      name: file.name,
      folder: selectedFolder === 'All' ? 'General' : selectedFolder,
      size: `${(file.size / (1024 * 1024)).toFixed(1)} MB`,
      updatedAt: 'Just now',
      snippet: `Indexed document containing text from ${file.name}. Vector embeddings generated.`,
    };
    setDocuments((prev) => [newDoc, ...prev]);
  };

  const handleSendChat = () => {
    if (!chatInput.trim()) return;
    const q = chatInput;
    setVaultChatMessages((prev) => [...prev, { sender: 'user', text: q }]);
    setChatInput('');

    setTimeout(() => {
      const targetName = activeDoc ? activeDoc.name : 'Knowledge Vault';
      setVaultChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: `Grounded in **${targetName}**: Relevant excerpts indicate verified data points matching "${q}". Memory vector similarity score: 0.94.`,
        },
      ]);
    }, 800);
  };

  return (
    <div className="knowledge-vault">
      {/* Header */}
      <header className="knowledge-vault__topbar">
        <div className="knowledge-vault__topbar-left">
          <button type="button" className="knowledge-vault__back-btn" onClick={onBack}>
            ← Back to Chat
          </button>
          <span className="knowledge-vault__badge">📚 Knowledge Vault</span>
        </div>
        <div className="knowledge-vault__topbar-actions">
          <button
            type="button"
            className="knowledge-vault__upload-btn"
            onClick={() => fileInputRef.current?.click()}
          >
            + Upload Document
          </button>
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            onChange={handleUpload}
          />
        </div>
      </header>

      <div className="knowledge-vault__content">
        {/* Document Library Left Area */}
        <div className="knowledge-vault__library">
          {/* Search & Folder filters */}
          <div className="knowledge-vault__controls">
            <div className="knowledge-vault__search">
              <span>🔍</span>
              <input
                type="search"
                placeholder="Search documents or semantic contents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="knowledge-vault__folders">
              {folders.map((folder) => (
                <button
                  key={folder}
                  type="button"
                  className={`folder-chip ${selectedFolder === folder ? 'active' : ''}`}
                  onClick={() => setSelectedFolder(folder)}
                >
                  📁 {folder}
                </button>
              ))}
            </div>
          </div>

          {/* Recent Documents Table / List */}
          <div className="knowledge-vault__list-section">
            <h3 className="knowledge-vault__section-title">Recent Documents ({filteredDocs.length})</h3>
            {filteredDocs.length === 0 ? (
              <div className="knowledge-vault__empty">
                <span>📄</span>
                <p>No documents found matching your filter.</p>
              </div>
            ) : (
              <div className="knowledge-vault__docs-grid">
                {filteredDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className={`doc-card ${activeDoc?.id === doc.id ? 'doc-card--active' : ''}`}
                    onClick={() => setActiveDoc(doc)}
                  >
                    <div className="doc-card__header">
                      <span className="doc-card__icon">📄</span>
                      <span className="doc-card__folder-tag">{doc.folder}</span>
                    </div>
                    <h4 className="doc-card__title">{doc.name}</h4>
                    <p className="doc-card__snippet">{doc.snippet}</p>
                    <div className="doc-card__footer">
                      <span>{doc.size}</span>
                      <span>•</span>
                      <span>{doc.updatedAt}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Grounded Chat Panel Right Area */}
        <aside className="knowledge-vault__chat-panel">
          <div className="vault-chat__header">
            <h3 className="vault-chat__title">
              {activeDoc ? `Chat with ${activeDoc.name}` : 'Document Grounding Chat'}
            </h3>
            {activeDoc && (
              <button
                type="button"
                className="vault-chat__clear-filter"
                onClick={() => setActiveDoc(null)}
              >
                Clear selection
              </button>
            )}
          </div>

          <div className="vault-chat__messages">
            {vaultChatMessages.map((m, idx) => (
              <div key={idx} className={`vault-chat__bubble vault-chat__bubble--${m.sender}`}>
                {m.text}
              </div>
            ))}
          </div>

          <div className="vault-chat__input-area">
            <input
              type="text"
              className="vault-chat__input"
              placeholder={activeDoc ? `Ask about ${activeDoc.name}...` : 'Ask across all vault documents...'}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendChat();
              }}
            />
            <button
              type="button"
              className="vault-chat__send-btn"
              onClick={handleSendChat}
              disabled={!chatInput.trim()}
            >
              Send
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
};
