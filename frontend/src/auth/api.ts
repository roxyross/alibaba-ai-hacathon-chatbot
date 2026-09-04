// Auth API client. All requests target VITE_API_BASE (e.g. /api/v1).
//
// VITE_API_BASE may be an absolute origin (e.g. "http://localhost:8000/api/v1")
// or a path-only base (e.g. "/api/v1"). The "/api/v1" prefix is mandatory —
// the backend mounts every router under it (see backend/src/app/main.py).
// We normalize the value here so call sites can keep doing
// `${API_BASE}/auth/...` without having to remember the prefix.

const RAW_API_BASE =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';

const API_BASE = /\/api\/v1\/?$/.test(RAW_API_BASE)
  ? RAW_API_BASE.replace(/\/$/, '')
  : `${RAW_API_BASE.replace(/\/$/, '')}/api/v1`;

export interface AuthUser {
  id: string;
  email: string;
  created_at: string;
}

export interface RequestLinkResponse {
  ok: boolean;
}

export interface VerifyResponse {
  user: AuthUser;
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText || ''} ${text}`.trim());
  }
  return (await res.json()) as T;
}

export async function fetchWithToken<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });
  return readJson<T>(res);
}

/**
 * Build the URL the browser should navigate to in order to start an OAuth flow
 * for the given provider (e.g. 'google'). The backend will 302 the user to
 * the provider's consent screen. This must be a top-level navigation — not
 * an XHR — so the resulting `Set-Cookie` is honored and the user actually
 * sees the consent screen.
 */
export function getOAuthStartUrl(provider: 'google' | 'github'): string {
  return `${API_BASE}/auth/oauth/${provider}/start`;
}

export const authApi = {
  async requestLink(email: string): Promise<RequestLinkResponse> {
    const res = await fetch(`${API_BASE}/auth/request-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    return readJson<RequestLinkResponse>(res);
  },

  async verify(token: string): Promise<VerifyResponse> {
    const res = await fetch(`${API_BASE}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    return readJson<VerifyResponse>(res);
  },

  async me(token: string): Promise<AuthUser> {
    return fetchWithToken<AuthUser>('/auth/me', token);
  },
};
