import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  AuthUser,
  authApi,
  fetchWithToken,
} from './api';

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  loading: boolean;
  error: string | null;
  requestLink: (email: string) => Promise<import('./api').RequestLinkResponse>;
  verify: (token: string) => Promise<void>;
  completeOAuth: (accessToken: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  signOut: () => void;
  authedFetch: <T>(path: string, init?: RequestInit) => Promise<T>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const TOKEN_KEY = 'roxy.access_token';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(
    () => localStorage.getItem(TOKEN_KEY),
  );
  const [loading, setLoading] = useState<boolean>(!!accessToken);
  const [error, setError] = useState<string | null>(null);

  // Bootstrap from a stored token.
  useEffect(() => {
    let cancelled = false;
    if (!accessToken) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const me = await authApi.me(accessToken);
        if (!cancelled) {
          setUser(me);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setAccessToken(null);
          localStorage.removeItem(TOKEN_KEY);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const requestLink = useCallback(async (email: string) => {
    setError(null);
    try {
      return await authApi.requestLink(email);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, []);

  const verify = useCallback(async (token: string) => {
    setError(null);
    setLoading(true);
    try {
      const result = await authApi.verify(token);
      localStorage.setItem(TOKEN_KEY, result.access_token);
      setAccessToken(result.access_token);
      setUser(result.user);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Adopt a JWT that was delivered in the URL hash by the OAuth callback
   * redirect. We trust the JWT is well-formed (HS256, our issuer) because it
   * came from our backend over a server-side redirect, but we still call
   * `/auth/me` to confirm the session is valid and to populate the user.
   */
  const completeOAuth = useCallback(async (accessToken: string) => {
    setError(null);
    setLoading(true);
    try {
      const me = await authApi.me(accessToken);
      localStorage.setItem(TOKEN_KEY, accessToken);
      setAccessToken(accessToken);
      setUser(me);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const demoLogin = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      let result;
      try {
        result = await authApi.demoLogin();
      } catch {
        const req = await authApi.requestLink('demo@roxy.ai');
        if (!req.dev_token) {
          throw new Error('Instant access is temporarily unavailable');
        }
        result = await authApi.verify(req.dev_token);
      }
      localStorage.setItem(TOKEN_KEY, result.access_token);
      setAccessToken(result.access_token);
      setUser(result.user);
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setAccessToken(null);
    setUser(null);
  }, []);

  const authedFetch = useCallback(
    <T,>(path: string, init: RequestInit = {}) => {
      if (!accessToken) {
        return Promise.reject(new Error('Not authenticated'));
      }
      return fetchWithToken<T>(path, accessToken, init);
    },
    [accessToken],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      loading,
      error,
      requestLink,
      verify,
      completeOAuth,
      demoLogin,
      signOut,
      authedFetch,
    }),
    [
      user,
      accessToken,
      loading,
      error,
      requestLink,
      verify,
      completeOAuth,
      demoLogin,
      signOut,
      authedFetch,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
