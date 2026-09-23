import React, { useState, useRef, useEffect, useCallback } from 'react';
import './KnowledgeVault.css';

interface DocItem {
  id: string;
  name: string;
  folder: string;
  size: string;
  updatedAt: string;
  snippet: string;
}

interface VaultChatMessage {
  sender: 'user' | 'assistant';
  text: string;
  sources?: string[];
  error?: boolean;
}

interface KnowledgeVaultProps {
  accessToken: string | null;
  onBack: () => void;
}

export const KnowledgeVault: React.FC<KnowledgeVaultProps> = ({ accessToken, onBack }) => {
  const rawApiBase = (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ?? '';
  const API_BASE = rawApiBase.endsWith('/api/v1') ? rawApiBase : (rawApiBase ? `${rawApiBase}/api/v1` : '/api/v1');

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFolder, setSelectedFolder] = useState<string>('All');
  const [activeDoc, setActiveDoc] = useState<DocItem | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [vaultChatMessages, setVaultChatMessages] = useState<VaultChatMessage[]>([
    { sender: 'assistant', text: 'Ask questions grounded directly in your private Knowledge Vault documents.' },
  ]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [documents, setDocuments] = useState<DocItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchDocs = useCallback(async () => {
    if (!accessToken) {
      setIsLoading(false);
      setFetchError(null);
      setDocuments([]);
      return;
    }
    setIsLoading(true);
    setFetchError(null);
    try {
      const res = await fetch(`${API_BASE}/documents`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.documents)) {
          setDocuments(
            data.documents.map((d: any) => ({
              id: d.document_id,
              name: d.document_name,
              folder: 'General',
              size: `${d.chunk_count || 1} chunks`,
              updatedAt: d.last_ingested ? new Date(d.last_ingested).toLocaleDateString() : 'Recently',
              snippet: `Indexed document with ${d.chunk_count || 1} chunks ready for RAG querying.`,
            }))
          );
        }
      } else {
        const err = await res.json().catch(() => ({}));
        setFetchError(err.detail || `Server returned error (${res.status})`);
      }
    } catch (err: any) {
      setFetchError(err?.message || 'Failed to connect to Knowledge Vault service.');
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, API_BASE]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const folders = ['All', 'Finance', 'Engineering', 'Strategy', 'General'];

  const filteredDocs = documents.filter((doc) => {
    const matchesFolder = selectedFolder === 'All' || doc.folder === selectedFolder;
    const matchesSearch =
      doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.snippet.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFolder && matchesSearch;
  });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!accessToken) {
      setNotice({ type: 'error', text: 'Please sign in to upload documents to your private Knowledge Vault.' });
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    // 50 MB limit
    if (file.size > 50 * 1024 * 1024) {
      setNotice({ type: 'error', text: `File "${file.name}" exceeds the maximum allowed size of 50 MB.` });
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setIsUploading(true);
    setNotice(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_name', file.name);

      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const newDoc: DocItem = {
          id: data.document_id || `doc-${Date.now()}`,
          name: data.document_name || file.name,
          folder: selectedFolder === 'All' ? 'General' : selectedFolder,
          size: `${data.chunks_stored || 1} chunks`,
          updatedAt: 'Just now',
          snippet: `Indexed document containing ${data.chunks_stored || 1} chunks from ${file.name}. Vector embeddings generated.`,
        };
        setDocuments((prev) => [newDoc, ...prev]);
        setNotice({ type: 'success', text: `Successfully indexed "${file.name}" into your Knowledge Vault.` });
      } else {
        const err = await res.json().catch(() => ({}));
        setNotice({ type: 'error', text: err.detail || `Failed to index "${file.name}".` });
      }
    } catch (err: any) {
      setNotice({ type: 'error', text: err?.message || `Network error uploading "${file.name}".` });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (e: React.MouseEvent, docId: string, docName: string) => {
    e.stopPropagation();
    if (!accessToken) {
      setNotice({ type: 'error', text: 'Authentication required to delete documents.' });
      return;
    }

    const confirmed = window.confirm(`Are you sure you want to delete "${docName}" from your Knowledge Vault? This will permanently remove all associated vector embeddings.`);
    if (!confirmed) return;

    const previousDocs = [...documents];
    setDocuments((prev) => prev.filter((d) => d.id !== docId));
    if (activeDoc?.id === docId) setActiveDoc(null);

    try {
      const res = await fetch(`${API_BASE}/documents/${docId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (res.ok) {
        setNotice({ type: 'success', text: `Document "${docName}" deleted from Knowledge Vault.` });
      } else {
        const err = await res.json().catch(() => ({}));
        setDocuments(previousDocs);
        setNotice({ type: 'error', text: err.detail || `Failed to delete "${docName}".` });
      }
    } catch (err: any) {
      setDocuments(previousDocs);
      setNotice({ type: 'error', text: err?.message || `Network error deleting "${docName}".` });
    }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim() || isQuerying) return;
    const q = chatInput;
    setVaultChatMessages((prev) => [...prev, { sender: 'user', text: q }]);
    setChatInput('');
    setIsQuerying(true);

    if (!accessToken) {
      setIsQuerying(false);
      setVaultChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: '🔒 Please sign in to query your private Knowledge Vault documents.',
          error: true,
        },
      ]);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/documents/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          query: q,
          document_ids: activeDoc ? [activeDoc.id] : undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const answer = data.answer || 'No relevant information found in your selected documents matching this query.';
        const sources: string[] = Array.isArray(data.sources) ? data.sources : [];
        setVaultChatMessages((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: answer,
            sources: sources.length > 0 ? sources : undefined,
          },
        ]);
      } else {
        const err = await res.json().catch(() => ({}));
        setVaultChatMessages((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: `⚠️ Query failed: ${err.detail || 'The server could not process the RAG request.'}`,
            error: true,
          },
        ]);
      }
    } catch (err: any) {
      setVaultChatMessages((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: `⚠️ Unable to reach Knowledge Vault service: ${err?.message || 'Connection error'}.`,
          error: true,
        },
      ]);
    } finally {
      setIsQuerying(false);
    }
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
            onClick={() => {
              if (!accessToken) {
                setNotice({ type: 'error', text: 'Please sign in to upload documents to your Knowledge Vault.' });
                return;
              }
              fileInputRef.current?.click();
            }}
            disabled={isUploading}
          >
            {isUploading ? 'Uploading...' : '+ Upload Document'}
          </button>
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            onChange={handleUpload}
            accept=".pdf,.docx,.pptx,.txt,.csv,.md,.json"
          />
        </div>
      </header>

      {/* Action Toast Notice */}
      {notice && (
        <div className={`vault-notice vault-notice--${notice.type}`}>
          <span className="vault-notice__icon">{notice.type === 'success' ? '✓' : '⚠️'}</span>
          <span className="vault-notice__text">{notice.text}</span>
          <button type="button" className="vault-notice__close" onClick={() => setNotice(null)}>×</button>
        </div>
      )}

      {/* Uploading Banner */}
      {isUploading && (
        <div className="vault-uploading-bar">
          <span className="vault-spinner"></span>
          <span>Indexing document and generating vector embeddings for RAG...</span>
        </div>
      )}

      <div className="knowledge-vault__content">
        {/* Document Explorer Left Area */}
        <div className="knowledge-vault__explorer">
          {/* Guest Auth Banner */}
          {!accessToken && (
            <div className="vault-auth-banner">
              <div className="vault-auth-banner__icon">🔒</div>
              <div className="vault-auth-banner__body">
                <h4 className="vault-auth-banner__title">Guest Session Mode</h4>
                <p className="vault-auth-banner__desc">
                  Sign in to your account to upload documents, generate vector embeddings, and chat with AI grounded in your private knowledge base.
                </p>
              </div>
            </div>
          )}

          {/* Connection Error Banner */}
          {fetchError && (
            <div className="vault-error-banner">
              <div className="vault-error-banner__content">
                <span className="vault-error-banner__icon">⚠️</span>
                <div>
                  <h4 className="vault-error-banner__title">Failed to load Knowledge Vault</h4>
                  <p className="vault-error-banner__msg">{fetchError}</p>
                </div>
              </div>
              <button
                type="button"
                className="vault-error-banner__retry-btn"
                onClick={fetchDocs}
                disabled={isLoading}
              >
                {isLoading ? 'Retrying...' : '↻ Retry Connection'}
              </button>
            </div>
          )}

          {/* Search & Folder filters */}
          <div className="knowledge-vault__filters">
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
            <div className="knowledge-vault__section-header">
              <h3 className="knowledge-vault__section-title">Recent Documents ({filteredDocs.length})</h3>
              {activeDoc && (
                <span className="knowledge-vault__active-filter-badge">
                  Filtered to: <strong>{activeDoc.name}</strong>
                  <button type="button" onClick={() => setActiveDoc(null)}>✕</button>
                </span>
              )}
            </div>

            {isLoading ? (
              <div className="knowledge-vault__empty" style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
                <span className="vault-spinner" style={{ margin: '0 auto 1rem', display: 'block' }}></span>
                <p style={{ color: 'var(--color-muted, #64748b)', fontSize: '0.88rem' }}>Loading documents...</p>
              </div>
            ) : filteredDocs.length === 0 ? (
              <div className="knowledge-vault__empty" style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
                <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '0.6rem' }}>📂</span>
                <h4 style={{ margin: '0 0 0.4rem 0', fontWeight: 700, fontSize: '1.1rem' }}>
                  {!accessToken ? 'No documents available in guest mode' : 'Your Knowledge Vault is empty'}
                </h4>
                <p style={{ color: 'var(--color-muted, #64748b)', fontSize: '0.88rem', maxWidth: '440px', margin: '0 auto 1rem' }}>
                  {!accessToken
                    ? 'Please sign in to upload and manage your private files with vector search and RAG synthesis.'
                    : 'Upload PDFs, Word documents, spreadsheets, or text files to index your files and ground AI answers.'}
                </p>
                {accessToken && (
                  <button
                    type="button"
                    className="knowledge-vault__upload-btn"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    + Upload Document
                  </button>
                )}
              </div>
            ) : (
              <div className="knowledge-vault__docs-grid">
                {filteredDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className={`doc-card ${activeDoc?.id === doc.id ? 'doc-card--active' : ''}`}
                    onClick={() => setActiveDoc(activeDoc?.id === doc.id ? null : doc)}
                  >
                    <div className="doc-card__header">
                      <span className="doc-card__icon">📄</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span className="doc-card__folder-tag">{doc.folder}</span>
                        <button
                          type="button"
                          className="doc-card__delete-btn"
                          onClick={(e) => handleDelete(e, doc.id, doc.name)}
                          title={`Delete "${doc.name}"`}
                          aria-label={`Delete "${doc.name}"`}
                        >
                          🗑️
                        </button>
                      </div>
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
                Clear filter
              </button>
            )}
          </div>

          <div className="vault-chat__messages">
            {vaultChatMessages.map((m, idx) => (
              <div key={idx} className={`vault-chat__bubble vault-chat__bubble--${m.sender} ${m.error ? 'vault-chat__bubble--error' : ''}`}>
                <div className="vault-chat__text">{m.text}</div>
                {m.sources && m.sources.length > 0 && (
                  <div className="vault-chat__sources">
                    <div className="vault-chat__sources-title">Verified Sources:</div>
                    <div className="vault-chat__sources-list">
                      {m.sources.map((src, i) => (
                        <span key={i} className="vault-chat__source-tag">📄 {src}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
            {isQuerying && (
              <div className="vault-chat__bubble vault-chat__bubble--assistant vault-chat__bubble--thinking">
                <span className="vault-pulse-dot"></span> Synthesizing answer from documents...
              </div>
            )}
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
              disabled={isQuerying}
            />
            <button
              type="button"
              className="vault-chat__send-btn"
              onClick={handleSendChat}
              disabled={!chatInput.trim() || isQuerying}
            >
              {isQuerying ? '...' : 'Send'}
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
};
