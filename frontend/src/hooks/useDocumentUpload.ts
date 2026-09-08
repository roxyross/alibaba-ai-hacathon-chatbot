// useDocumentUpload — upload files to the RAG pipeline and list/delete documents

import { useCallback, useState } from 'react';

export interface UploadedDocument {
  document_id: string;
  document_name: string;
  chunk_count: number;
  last_ingested: string | null;
}

export interface UploadResult {
  document_id: string;
  document_name: string;
  chunks_stored: number;
  doc_type: string;
}

export interface UseDocumentUploadOptions {
  runtimeUrl?: string;
  accessToken?: string | null;
}

interface UploadState {
  uploading: boolean;
  error: string | null;
  uploadProgress: number; // 0-100
  lastResult: UploadResult | null;
}

const RUNTIME_DOCS_PATH = '/api/v1/documents';
const RUNTIME_UPLOAD_PATH = '/api/v1/documents/upload';

export function useDocumentUpload(options: UseDocumentUploadOptions = {}) {
  const { runtimeUrl = '', accessToken } = options;
  const [state, setState] = useState<UploadState>({
    uploading: false,
    error: null,
    uploadProgress: 0,
    lastResult: null,
  });

  // ── Upload a file ────────────────────────────────────────────────────────

  const upload = useCallback(
    async (file: File, documentName?: string, replaceExisting = false) => {
      if (!accessToken) {
        setState((s) => ({ ...s, error: 'Not authenticated' }));
        return null;
      }

      setState({ uploading: true, error: null, uploadProgress: 0, lastResult: null });

      try {
        const formData = new FormData();
        formData.append('file', file);
        if (documentName) {
          formData.append('document_name', documentName);
        }
        formData.append('replace_existing', String(replaceExisting));

        // Simulate progress (XHR would give real progress, but fetch doesn't)
        const progressInterval = setInterval(() => {
          setState((s) => ({
            ...s,
            uploadProgress: Math.min(s.uploadProgress + 15, 85),
          }));
        }, 200);

        const response = await fetch(`${runtimeUrl}${RUNTIME_UPLOAD_PATH}`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
          body: formData,
        });

        clearInterval(progressInterval);

        if (!response.ok) {
          let detail = `HTTP ${response.status}`;
          try {
            const err = await response.json();
            detail = err.detail || detail;
          } catch {}
          throw new Error(detail);
        }

        const result: UploadResult = await response.json();

        setState({
          uploading: false,
          error: null,
          uploadProgress: 100,
          lastResult: result,
        });

        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed';
        setState({ uploading: false, error: message, uploadProgress: 0, lastResult: null });
        return null;
      }
    },
    [runtimeUrl, accessToken],
  );

  // ── List documents ────────────────────────────────────────────────────────

  const listDocuments = useCallback(
    async (): Promise<UploadedDocument[]> => {
      if (!accessToken) return [];

      try {
        const response = await fetch(`${runtimeUrl}${RUNTIME_DOCS_PATH}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });

        if (!response.ok) return [];
        const data = await response.json();
        return (data.documents ?? []) as UploadedDocument[];
      } catch {
        return [];
      }
    },
    [runtimeUrl, accessToken],
  );

  // ── Delete a document ─────────────────────────────────────────────────────

  const deleteDocument = useCallback(
    async (documentId: string): Promise<boolean> => {
      if (!accessToken) return false;

      try {
        const response = await fetch(`${runtimeUrl}${RUNTIME_DOCS_PATH}/${documentId}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        });

        return response.ok;
      } catch {
        return false;
      }
    },
    [runtimeUrl, accessToken],
  );

  // ── Clear error ───────────────────────────────────────────────────────────

  const clearError = useCallback(() => {
    setState((s) => ({ ...s, error: null }));
  }, []);

  return {
    ...state,
    upload,
    listDocuments,
    deleteDocument,
    clearError,
  };
}
