/* DocumentUpload — drag-and-drop file uploader with document library + media preview.
 *
 * Supports: PDF, DOCX, PPTX, TXT, MD, CSV, JPG, PNG, GIF, BMP, WEBP, MP4, MOV, AVI, MKV, WEBM
 *
 * Usage:
 *   <DocumentUpload accessToken={token} onUploadDone={(result) => { ... }} />
 */

import React, { useCallback, useRef, useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, Trash2, Image as ImageIcon, Film, FileText, X, Eye, AlertCircle } from 'lucide-react';
import { useDocumentUpload } from '../../hooks/useDocumentUpload';

// ── Accepted file types ──────────────────────────────────────────────────────

const ACCEPTED_EXTENSIONS = [
  '.pdf', '.docx', '.pptx', '.txt', '.md', '.csv',
  '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
  '.mp4', '.mov', '.avi', '.mkv', '.webm', '.mpeg',
].join(',');

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB

// ── Media preview types ──────────────────────────────────────────────────────

type PreviewType = 'none' | 'image' | 'video';

interface FilePreview {
  file: File;
  type: PreviewType;
  url: string; // object URL for preview
}

// ── File type detection ───────────────────────────────────────────────────────

function getPreviewType(file: File): PreviewType {
  if (file.type.startsWith('image/')) return 'image';
  if (file.type.startsWith('video/')) return 'video';
  return 'none';
}

// ── MediaPreview component ────────────────────────────────────────────────────

function MediaPreview({ preview, onClose }: { preview: FilePreview; onClose: () => void }) {
  return (
    <div className="media-preview-overlay" onClick={onClose}>
      <div className="media-preview-modal" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="media-preview-close"
          onClick={onClose}
          aria-label="Close preview"
        >
          <X size={20} />
        </button>
        {preview.type === 'image' && (
          <img
            src={preview.url}
            alt={preview.file.name}
            className="media-preview-image"
          />
        )}
        {preview.type === 'video' && (
          <video
            src={preview.url}
            controls
            autoPlay
            className="media-preview-video"
          >
            Your browser does not support video playback.
          </video>
        )}
        <div className="media-preview-filename">{preview.file.name}</div>
      </div>
    </div>
  );
}

// ── FilePreviewItem component ─────────────────────────────────────────────────

function FilePreviewItem({
  preview,
  onRemove,
  onPreview,
}: {
  preview: FilePreview;
  onRemove: () => void;
  onPreview: () => void;
}) {
  return (
    <div className="document-upload__file-item document-upload__file-item--with-preview">
      <span className="document-upload__file-icon">
        {preview.type === 'image' ? (
          <img src={preview.url} alt="" className="document-upload__thumbnail" />
        ) : preview.type === 'video' ? (
          <Film size={20} className="document-upload__video-icon" />
        ) : (
          <FileText size={20} />
        )}
      </span>
      <span className="document-upload__file-name">{preview.file.name}</span>
      {preview.type !== 'none' && (
        <button
          type="button"
          className="document-upload__preview-btn"
          onClick={onPreview}
          aria-label={`Preview ${preview.file.name}`}
          title="Preview"
        >
          <Eye size={16} />
        </button>
      )}
      <button
        type="button"
        className="document-upload__file-remove"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        aria-label={`Remove ${preview.file.name}`}
      >
        <X size={14} />
      </button>
    </div>
  );
}

// ── Drop zone component ──────────────────────────────────────────────────────

function DropZone({
  onFilesSelected,
  selectedPreviews,
  onRemoveFile,
  onPreviewFile,
  onBrowseClick,
}: {
  onFilesSelected: (files: File[]) => void;
  selectedPreviews: FilePreview[];
  onRemoveFile: (file: File) => void;
  onPreviewFile: (preview: FilePreview) => void;
  onBrowseClick: () => void;
}) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'text/csv': ['.csv'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
      'image/gif': ['.gif'],
      'image/bmp': ['.bmp'],
      'image/webp': ['.webp'],
      'image/tiff': ['.tiff', '.tif'],
      'video/mp4': ['.mp4'],
      'video/quicktime': ['.mov'],
      'video/x-msvideo': ['.avi'],
      'video/x-matroska': ['.mkv'],
      'video/webm': ['.webm'],
      'video/mpeg': ['.mpeg'],
    },
    onDrop: (acceptedFiles) => {
      const valid = acceptedFiles.filter((f) => f.size <= MAX_FILE_SIZE);
      if (valid.length < acceptedFiles.length) {
        alert('Some files exceed the 50 MB limit and were skipped.');
      }
      onFilesSelected(valid);
    },
    maxSize: MAX_FILE_SIZE,
    multiple: true,
  });

  const isActive = isDragActive;

  return (
    <div
      {...getRootProps()}
      className={`document-upload__dropzone${isActive ? ' document-upload__dropzone--drag-over' : ''}${selectedPreviews.length > 0 ? ' document-upload__dropzone--has-files' : ''}`}
      onClick={onBrowseClick}
      role="button"
      tabIndex={0}
      aria-label="Click or drop files to upload"
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onBrowseClick();
      }}
    >
      <input
        {...getInputProps()}
        className="document-upload__file-input"
        aria-hidden="true"
        tabIndex={-1}
      />

      {selectedPreviews.length === 0 ? (
        <>
          <div className="document-upload__drop-icon">
            <Upload size={48} strokeWidth={1.5} />
          </div>
          <p className="document-upload__drop-title">
            {isActive ? 'Drop files here' : 'Drop files here or '}
            <span className="document-upload__browse-link">browse</span>
          </p>
          <p className="document-upload__drop-hint">
            PDF, DOCX, PPTX, TXT, CSV, MD, JPG, PNG, GIF, MP4, MOV, ...
          </p>
          <p className="document-upload__drop-hint">Max 50 MB per file</p>
        </>
      ) : (
        <div className="document-upload__file-list">
          {selectedPreviews.map((preview) => (
            <FilePreviewItem
              key={preview.file.name + preview.file.size}
              preview={preview}
              onRemove={() => onRemoveFile(preview.file)}
              onPreview={() => onPreviewFile(preview)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface DocumentUploadProps {
  accessToken: string | null;
  runtimeUrl?: string;
  /** Called after a successful upload */
  onUploadDone?: (result: { document_id: string; document_name: string }) => void;
}

export function DocumentUpload({
  accessToken,
  runtimeUrl,
  onUploadDone,
}: DocumentUploadProps) {
  const { upload, listDocuments, deleteDocument, uploading, error, uploadProgress, clearError } =
    useDocumentUpload({ runtimeUrl, accessToken });

  const [documents, setDocuments] = useState<Awaited<ReturnType<typeof listDocuments>>>([]);
  const [loading, setLoading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [filePreviews, setFilePreviews] = useState<FilePreview[]>([]);
  const [documentName, setDocumentName] = useState('');
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'upload' | 'library'>('upload');
  const [previewModal, setPreviewModal] = useState<FilePreview | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Create object URLs for previews ──────────────────────────────────────

  const buildPreviews = useCallback((files: File[]): FilePreview[] => {
    return files.map((file) => ({
      file,
      type: getPreviewType(file),
      url: URL.createObjectURL(file),
    }));
  }, []);

  // Clean up object URLs when files are removed
  const removePreview = useCallback((file: File) => {
    setFilePreviews((prev) => {
      const preview = prev.find((p) => p.file === file);
      if (preview) URL.revokeObjectURL(preview.url);
      return prev.filter((p) => p.file !== file);
    });
    setSelectedFiles((prev) => prev.filter((f) => f !== file));
  }, []);

  const clearAllPreviews = useCallback(() => {
    filePreviews.forEach((p) => URL.revokeObjectURL(p.url));
    setFilePreviews([]);
    setSelectedFiles([]);
  }, [filePreviews]);

  // ── Load library ─────────────────────────────────────────────────────────

  const loadLibrary = useCallback(async () => {
    setLoading(true);
    const docs = await listDocuments();
    setDocuments(docs);
    setLoading(false);
  }, [listDocuments]);

  // ── Open library tab ─────────────────────────────────────────────────────

  const handleOpenLibrary = useCallback(() => {
    setActiveTab('library');
    void loadLibrary();
  }, [loadLibrary]);

  // ── File selection ───────────────────────────────────────────────────────

  const handleFilesSelected = useCallback(
    (files: FileList | File[] | null) => {
      if (!files) return;
      const incoming = Array.from(files);
      const valid = incoming.filter((f) => {
        if (f.size > MAX_FILE_SIZE) {
          return false;
        }
        return true;
      });

      // Clear old previews
      filePreviews.forEach((p) => URL.revokeObjectURL(p.url));

      setSelectedFiles(valid);
      setFilePreviews(buildPreviews(valid));
      setDocumentName(valid[0]?.name.replace(/\.[^.]+$/, '') ?? '');
    },
    [filePreviews, buildPreviews],
  );

  // ── Upload ───────────────────────────────────────────────────────────────

  const handleUpload = useCallback(async () => {
    if (selectedFiles.length === 0) return;

    for (const file of selectedFiles) {
      const result = await upload(file, documentName || undefined, replaceExisting);
      if (result) {
        onUploadDone?.({ document_id: result.document_id, document_name: result.document_name });
      } else {
        break;
      }
    }

    if (!error) {
      clearAllPreviews();
      setDocumentName('');
    }
  }, [selectedFiles, documentName, replaceExisting, upload, onUploadDone, error, clearAllPreviews]);

  // ── Delete ────────────────────────────────────────────────────────────────

  const handleDelete = useCallback(
    async (documentId: string, docName: string) => {
      if (!confirm(`Delete "${docName}" and all its chunks? This cannot be undone.`)) return;
      setDeletingId(documentId);
      const ok = await deleteDocument(documentId);
      setDeletingId(null);
      if (ok) {
        setDocuments((prev) => prev.filter((d) => d.document_id !== documentId));
      }
    },
    [deleteDocument],
  );

  // ── Format bytes ──────────────────────────────────────────────────────────

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  // ── Browse button ───────────────────────────────────────────────────────

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      handleFilesSelected(e.target.files);
      // Reset so same file can be selected again
      e.target.value = '';
    },
    [handleFilesSelected],
  );

  // ── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      filePreviews.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, []);

  return (
    <div className="document-upload">
      {/* Preview modal */}
      {previewModal && (
        <MediaPreview preview={previewModal} onClose={() => setPreviewModal(null)} />
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS}
        className="document-upload__file-input"
        onChange={handleFileInputChange}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* ── Tab bar ─────────────────────────────────────────────────────── */}
      <div className="document-upload__tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'upload'}
          className={`document-upload__tab${activeTab === 'upload' ? ' document-upload__tab--active' : ''}`}
          onClick={() => setActiveTab('upload')}
          type="button"
        >
          <Upload size={14} />
          Upload
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'library'}
          className={`document-upload__tab${activeTab === 'library' ? ' document-upload__tab--active' : ''}`}
          onClick={handleOpenLibrary}
          type="button"
        >
          📚 Library
          {documents.length > 0 && (
            <span className="document-upload__badge">{documents.length}</span>
          )}
        </button>
      </div>

      {/* ── Upload tab ───────────────────────────────────────────────────── */}
      {activeTab === 'upload' && (
        <div className="document-upload__content">
          {/* Drop zone */}
          <DropZone
            onFilesSelected={handleFilesSelected}
            selectedPreviews={filePreviews}
            onRemoveFile={removePreview}
            onPreviewFile={(p) => setPreviewModal(p)}
            onBrowseClick={handleBrowseClick}
          />

          {/* Options */}
          {selectedFiles.length > 0 && (
            <div className="document-upload__options">
              <div className="document-upload__option">
                <label htmlFor="doc-name" className="document-upload__label">
                  Document name
                </label>
                <input
                  id="doc-name"
                  type="text"
                  className="document-upload__input"
                  value={documentName}
                  onChange={(e) => setDocumentName(e.target.value)}
                  placeholder="Leave blank to use filename"
                  maxLength={200}
                />
              </div>
              <div className="document-upload__option">
                <label className="document-upload__checkbox-label">
                  <input
                    type="checkbox"
                    checked={replaceExisting}
                    onChange={(e) => setReplaceExisting(e.target.checked)}
                  />
                  Replace existing chunks for this document
                </label>
              </div>

              {/* Selected file info */}
              <div className="document-upload__selected-files">
                {selectedFiles.map((f) => (
                  <div key={f.name + f.size} className="document-upload__selected-file">
                    <span className="document-upload__selected-file-icon">
                      {f.type.startsWith('image/') ? (
                        <ImageIcon size={14} />
                      ) : f.type.startsWith('video/') ? (
                        <Film size={14} />
                      ) : (
                        <FileText size={14} />
                      )}
                    </span>
                    <span className="document-upload__selected-file-name">{f.name}</span>
                    <span className="document-upload__selected-file-size">{formatBytes(f.size)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="document-upload__error" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
              <button type="button" onClick={clearError} aria-label="Dismiss error">
                <X size={14} />
              </button>
            </div>
          )}

          {/* Upload button */}
          {selectedFiles.length > 0 && (
            <div className="document-upload__actions">
              {uploading ? (
                <div className="document-upload__progress" aria-live="polite">
                  <div
                    className="document-upload__progress-bar"
                    style={{ width: `${uploadProgress}%` }}
                    role="progressbar"
                    aria-valuenow={uploadProgress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  />
                  <span className="document-upload__progress-text">
                    Uploading... {uploadProgress}%
                  </span>
                </div>
              ) : (
                <button
                  type="button"
                  className="document-upload__upload-btn"
                  onClick={handleUpload}
                  disabled={selectedFiles.length === 0}
                >
                  <Upload size={16} />
                  Upload {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''}
                </button>
              )}
              <button
                type="button"
                className="document-upload__cancel-btn"
                onClick={clearAllPreviews}
              >
                Cancel
              </button>
            </div>
          )}

          {/* Supported types */}
          <div className="document-upload__supported">
            <details>
              <summary>Supported file types</summary>
              <div className="document-upload__supported-grid">
                <div>
                  <strong>Documents:</strong> PDF, DOCX, PPTX, TXT, Markdown, CSV
                </div>
                <div>
                  <strong>Images:</strong> JPEG, PNG, GIF, BMP, WEBP, TIFF — OCR + AI captioning
                </div>
                <div>
                  <strong>Video:</strong> MP4, MOV, AVI, MKV, WEBM — transcription + frame captions
                </div>
              </div>
            </details>
          </div>
        </div>
      )}

      {/* ── Library tab ───────────────────────────────────────────────────── */}
      {activeTab === 'library' && (
        <div className="document-upload__content">
          {loading ? (
            <div className="document-upload__loading">
              <div className="document-upload__spinner" aria-hidden="true" />
              Loading documents...
            </div>
          ) : documents.length === 0 ? (
            <div className="document-upload__empty">
              <FileText size={48} strokeWidth={1} />
              <p>No documents uploaded yet.</p>
              <p>
                Go to the <strong>Upload</strong> tab to add your first document.
              </p>
            </div>
          ) : (
            <ul className="document-upload__library" aria-label="Uploaded documents">
              {documents.map((doc) => (
                <li key={doc.document_id} className="document-upload__library-item">
                  <div className="document-upload__library-info">
                    <strong className="document-upload__library-name">{doc.document_name}</strong>
                    <span className="document-upload__library-meta">
                      {doc.chunk_count} chunks
                      {doc.last_ingested && (
                        <> · {new Date(doc.last_ingested).toLocaleDateString()}</>
                      )}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="document-upload__delete-btn"
                    onClick={() => handleDelete(doc.document_id, doc.document_name)}
                    disabled={deletingId === doc.document_id}
                    aria-label={`Delete ${doc.document_name}`}
                    title="Delete document"
                  >
                    {deletingId === doc.document_id ? (
                      <div className="document-upload__spinner document-upload__spinner--sm" />
                    ) : (
                      <Trash2 size={16} />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
