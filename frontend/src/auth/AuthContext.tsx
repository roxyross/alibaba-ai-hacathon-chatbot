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
  const [user, setUser] = useState<AuthUser | null>(() => {
    if (typeof window !== 'undefined') {
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
      const token = hashParams.get('access_token') || localStorage.getItem(TOKEN_KEY);
      if (token) {
        try {
          const payloadPart = token.split('.')[1];
          if (payloadPart) {
            const decoded = JSON.parse(atob(payloadPart.replace(/-/g, '+').replace(/_/g, '/')));
            if (decoded.sub) {
              return {
                id: decoded.sub,
                email: decoded.email || 'user@roxy.ai',
                created_at: new Date().toISOString(),
              };
            }
          }
        } catch {
          // ignore
        }
      }
    }
    return null;
  });

  const [accessToken, setAccessToken] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
      const hashToken = hashParams.get('access_token');
      if (hashToken) {
        localStorage.setItem(TOKEN_KEY, hashToken);
        return hashToken;
      }
      return localStorage.getItem(TOKEN_KEY);
    }
    return null;
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Adopt a JWT delivered in the URL hash by the OAuth callback redirect.
   * Stores the token and sets user state INSTANTLY (0ms delay), then verifies
   * /auth/me in the background without blocking.
   */
  const completeOAuth = useCallback(async (token: string) => {
    setError(null);
    setLoading(false);
    try {
      // 1. Immediately store token and state
      localStorage.setItem(TOKEN_KEY, token);
      setAccessToken(token);

      // 2. Decode user instantly from verified JWT payload
      try {
        const payloadPart = token.split('.')[1];
        if (payloadPart) {
          const decoded = JSON.parse(atob(payloadPart.replace(/-/g, '+').replace(/_/g, '/')));
          if (decoded.sub) {
            setUser({
              id: decoded.sub,
              email: decoded.email || 'user@roxy.ai',
              created_at: new Date().toISOString(),
            });
          }
        }
      } catch {
        // ignore
      }

      // 3. Confirm with /auth/me in the background (non-blocking)
      authApi.me(token).then((me) => {
        if (me) setUser(me);
      }).catch((err) => {
        console.warn('Background user refresh:', err);
      });
    } catch (err) {
      setError((err as Error).message);
      throw err;
    }
  }, []);

  // Bootstrap from a stored token or URL hash token immediately.
  useEffect(() => {
    let cancelled = false;
    let initialToken = accessToken;

    const checkHash = () => {
      if (typeof window !== 'undefined' && window.location.hash.includes('access_token')) {
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        const hashToken = hashParams.get('access_token');
        if (hashToken) {
          completeOAuth(hashToken);
          window.history.replaceState({}, '', window.location.pathname + window.location.search);
          return hashToken;
        }
      }
      return null;
    };

    const tokenFromHash = checkHash();
    if (tokenFromHash) {
      initialToken = tokenFromHash;
    }

    const onHashChange = () => {
      checkHash();
    };
    window.addEventListener('hashchange', onHashChange);

    if (!initialToken) {
      setLoading(false);
      return () => {
        cancelled = true;
        window.removeEventListener('hashchange', onHashChange);
      };
    }

    // Optimistically decode user from token payload immediately
    try {
      const payloadPart = initialToken.split('.')[1];
      if (payloadPart) {
        const decoded = JSON.parse(atob(payloadPart.replace(/-/g, '+').replace(/_/g, '/')));
        if (decoded.sub && !user) {
          setUser({
            id: decoded.sub,
            email: decoded.email || 'user@roxy.ai',
            created_at: new Date().toISOString(),
          });
        }
      }
    } catch {
      // ignore
    }

    (async () => {
      try {
        const me = await authApi.me(initialToken);
        if (!cancelled && me) {
          setUser(me);
          setError(null);
        }
      } catch {
        // Keep optimistic user if me() fails due to server cold start
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      window.removeEventListener('hashchange', onHashChange);
    };
  }, [accessToken, completeOAuth]);

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
    if (typeof window !== 'undefined') {
      if (window.location.hash.includes('access_token')) {
        window.history.replaceState({}, '', window.location.pathname);
      }
    }
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
