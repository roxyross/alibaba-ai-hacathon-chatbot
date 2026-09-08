import React, { useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import { getOAuthStartUrl } from './api';
import './AuthGate.css';

/** Inline Google "G" logo. Inline so we don't pull an external image. */
const GoogleLogo: React.FC = () => (
  <svg
    className="auth-gate__oauth-icon"
    aria-hidden="true"
    viewBox="0 0 48 48"
    width="18"
    height="18"
  >
    <path
      fill="#FFC107"
      d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
    />
    <path
      fill="#FF3D00"
      d="m6.306 14.691 6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
    />
    <path
      fill="#4CAF50"
      d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
    />
    <path
      fill="#1976D2"
      d="M43.611 20.083 43.595 20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
    />
  </svg>
);

/** Inline GitHub mark. */
const GitHubLogo: React.FC = () => (
  <svg
    className="auth-gate__oauth-icon"
    aria-hidden="true"
    viewBox="0 0 24 24"
    width="18"
    height="18"
    fill="currentColor"
  >
    <path d="M12 .5C5.73.5.75 5.48.75 11.75c0 4.97 3.22 9.18 7.69 10.66.56.1.77-.24.77-.54v-1.9c-3.13.68-3.79-1.51-3.79-1.51-.51-1.3-1.25-1.65-1.25-1.65-1.02-.7.08-.69.08-.69 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.73.39-1.22.71-1.5-2.5-.28-5.14-1.25-5.14-5.57 0-1.23.44-2.24 1.16-3.03-.12-.28-.5-1.42.11-2.96 0 0 .95-.3 3.1 1.16.9-.25 1.86-.38 2.82-.38.96 0 1.92.13 2.82.38 2.15-1.46 3.1-1.16 3.1-1.16.61 1.54.23 2.68.11 2.96.72.79 1.16 1.8 1.16 3.03 0 4.33-2.64 5.29-5.16 5.57.4.35.76 1.03.76 2.08v3.08c0 .3.21.65.78.54 4.46-1.49 7.68-5.69 7.68-10.66C23.25 5.48 18.27.5 12 .5z" />
  </svg>
);

export const AuthGate: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, accessToken, loading, error, requestLink, verify, completeOAuth } =
    useAuth();
  const [email, setEmail] = useState('');
  const [phase, setPhase] = useState<'request' | 'pending' | 'verifying'>(
    'request',
  );
  const [manualToken, setManualToken] = useState('');
  const [devToken, setDevToken] = useState<string | null>(null);
  const [oauthErrorMessage, setOauthErrorMessage] = useState<string | null>(null);

  // Handle deep links from both auth flows on initial render:
  //   - Magic link: /auth/callback?token=...
  //   - OAuth:      /auth/callback#access_token=...&...  (or #error=...)
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    const token = url.searchParams.get('token');
    const hashParams = new URLSearchParams(url.hash.replace(/^#/, ''));
    const oauthToken = hashParams.get('access_token');
    const oauthError = hashParams.get('error');

    if (oauthError) {
      // Surface the OAuth error inline and redirect cleanly to /
      console.error('OAuth error:', oauthError);
      setOauthErrorMessage(`OAuth failed: ${oauthError.replace(/_/g, ' ')}`);
      window.history.replaceState({}, '', '/');
      return;
    }

    if (oauthToken) {
      setPhase('verifying');
      setOauthErrorMessage(null);
      completeOAuth(oauthToken)
        .then(() => {
          window.history.replaceState({}, '', '/');
        })
        .catch((err) => {
          setPhase('request');
          setOauthErrorMessage((err as Error).message || 'OAuth sign-in failed');
          window.history.replaceState({}, '', '/');
        });
      return;
    }

    if (!token) return;
    setPhase('verifying');
    setOauthErrorMessage(null);
    verify(token)
      .then(() => {
        window.history.replaceState({}, '', '/');
      })
      .catch((err) => {
        setPhase('pending');
        setManualToken(token);
        console.error('verify failed', err);
      });
  }, [verify, completeOAuth]);

  if (loading) {
    return (
      <div className="auth-gate">
        <div className="auth-gate__panel">
          <p>Loading…</p>
        </div>
      </div>
    );
  }

  if (user && accessToken) {
    if (typeof window !== 'undefined' && window.location.pathname.startsWith('/auth')) {
      window.history.replaceState({}, '', '/');
    }
    return <>{children}</>;
  }

  return (
    <div className="auth-gate">
      <div className="auth-gate__panel">
        <h1 className="auth-gate__brand">
          ROXY <span>AI</span>
        </h1>
        <p className="auth-gate__tagline">A Personal AI That Actually Knows You</p>

        <h2 className="auth-gate__heading">Sign in or create an account</h2>

        {phase === 'request' && (
          <>
            <form
              className="auth-gate__form"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!email) return;
                try {
                  const res = await requestLink(email);
                  if (res?.dev_token) {
                    setDevToken(res.dev_token);
                  }
                  // Keep verification input empty so user enters the code received in their mail
                  setManualToken('');
                  setPhase('pending');
                } catch {
                  /* error already in context */
                }
              }}
            >
              <label htmlFor="auth-email" className="auth-gate__label">
                Email
              </label>
              <input
                id="auth-email"
                type="email"
                required
                autoFocus
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="auth-gate__input"
              />
              <button type="submit" className="auth-gate__submit">
                Continue with email
              </button>
              <p className="auth-gate__hint">
                We'll email you a one-time sign-in link. New here? An account
                is created automatically.
              </p>
            </form>

            <div className="auth-gate__divider" role="separator">
              <span>or</span>
            </div>

            <button
              type="button"
              className="auth-gate__oauth auth-gate__oauth--google"
              onClick={() => {
                // Top-level navigation so Set-Cookie is honored and the user
                // actually sees the Google consent screen.
                window.location.href = getOAuthStartUrl('google');
              }}
              aria-label="Sign in with Google"
            >
              <GoogleLogo />
              <span>Continue with Google</span>
            </button>

            <button
              type="button"
              className="auth-gate__oauth auth-gate__oauth--github"
              onClick={() => {
                window.location.href = getOAuthStartUrl('github');
              }}
              aria-label="Sign in with GitHub"
            >
              <GitHubLogo />
              <span>Continue with GitHub</span>
            </button>

            <div className="auth-gate__divider" role="separator" style={{ margin: '1rem 0 0.75rem 0' }}>
              <span>or instant access</span>
            </div>

            <button
              type="button"
              className="auth-gate__submit"
              style={{
                background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
                border: 'none',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '0.95rem',
                padding: '0.75rem 1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                borderRadius: '8px',
                boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)',
                transition: 'transform 0.15s ease, box-shadow 0.15s ease',
              }}
              onClick={async () => {
                try {
                  const res = await requestLink('demo@roxy.ai');
                  if (res?.dev_token) {
                    await verify(res.dev_token);
                  }
                } catch (err) {
                  console.error('Instant access failed:', err);
                }
              }}
              title="Sign in instantly without Google or GitHub"
            >
              <span>⚡ Enter Instantly (Demo Access)</span>
            </button>

            <details
              style={{
                marginTop: '0.85rem',
                padding: '0.6rem 0.85rem',
                background: 'rgba(30, 41, 59, 0.6)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                fontSize: '0.78rem',
                color: '#94a3b8',
                textAlign: 'left',
              }}
            >
              <summary style={{ cursor: 'pointer', color: '#93c5fd', fontWeight: 500 }}>
                ℹ️ Google / GitHub access blocked? Read how to configure
              </summary>
              <ul style={{ margin: '0.5rem 0 0 0', paddingLeft: '1.2rem', lineHeight: 1.5 }}>
                <li>
                  <strong>Google (Error 400: redirect_uri_mismatch):</strong> Add <code style={{ color: '#60a5fa' }}>http://localhost:8000/api/v1/auth/oauth/google/callback</code> to Authorized Redirect URIs in your Google Cloud Console.
                </li>
                <li>
                  <strong>Google ("Access blocked: app in testing"):</strong> Add your Gmail address under "Test Users" in Google OAuth Consent Screen.
                </li>
                <li>
                  <strong>GitHub ("redirect_uri mismatch"):</strong> Set Authorization callback URL to <code style={{ color: '#60a5fa' }}>http://localhost:8000/api/v1/auth/oauth/github/callback</code> in GitHub Developer Settings.
                </li>
                <li>
                  <strong>Instant Demo:</strong> Use <strong>⚡ Enter Instantly</strong> above to bypass OAuth setup completely.
                </li>
              </ul>
            </details>

            {(oauthErrorMessage || error) && (
              <p className="auth-gate__error">{oauthErrorMessage || error}</p>
            )}
          </>
        )}

        {phase === 'pending' && (
          <div className="auth-gate__form">
            <div
              style={{
                background: 'rgba(59, 130, 246, 0.08)',
                border: '1px solid rgba(59, 130, 246, 0.25)',
                borderRadius: '10px',
                padding: '1.25rem',
                marginBottom: '1.25rem',
                textAlign: 'center',
              }}
            >
              <span style={{ fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}>📬</span>
              <p style={{ margin: '0 0 0.5rem 0', fontWeight: 600, color: '#f8fafc', fontSize: '1.05rem' }}>
                Check your Email Inbox
              </p>
              <p style={{ margin: 0, color: '#94a3b8', fontSize: '0.9rem', lineHeight: 1.5 }}>
                We sent a sign-in link and verification code to <strong style={{ color: '#60a5fa' }}>{email}</strong>.
                Click the link in your email or enter the code below to complete sign-in.
              </p>
            </div>

            <form
              onSubmit={async (e) => {
                e.preventDefault();
                if (!manualToken) return;
                try {
                  await verify(manualToken.trim());
                } catch {
                  /* error already in context */
                }
              }}
              style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
            >
              <label htmlFor="token-input" style={{ fontSize: '0.85rem', color: '#cbd5e1', fontWeight: 500 }}>
                Verification Code / Token from Email:
              </label>
              <input
                id="token-input"
                type="text"
                placeholder="Paste the code received in your email"
                value={manualToken}
                onChange={(e) => setManualToken(e.target.value)}
                className="auth-gate__input"
                autoFocus
              />
              <button type="submit" className="auth-gate__submit" disabled={!manualToken.trim()}>
                Verify & Sign In
              </button>
            </form>

            {devToken && (
              <details
                style={{
                  marginTop: '1rem',
                  padding: '0.6rem 0.85rem',
                  background: 'rgba(30, 41, 59, 0.6)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  color: '#94a3b8',
                }}
              >
                <summary style={{ cursor: 'pointer', color: '#60a5fa', fontWeight: 500 }}>
                  🔧 Local Dev: show console token
                </summary>
                <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <code style={{ fontSize: '0.75rem', color: '#cbd5e1', wordBreak: 'break-all' }}>{devToken}</code>
                  <button
                    type="button"
                    style={{
                      background: 'rgba(255, 255, 255, 0.1)',
                      border: 'none',
                      color: '#fff',
                      borderRadius: '4px',
                      padding: '0.25rem 0.5rem',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                    onClick={() => setManualToken(devToken)}
                  >
                    Paste to input
                  </button>
                </div>
              </details>
            )}
            <button
              type="button"
              className="auth-gate__link"
              onClick={() => {
                setPhase('request');
                setManualToken('');
              }}
            >
              Use a different email
            </button>
          </div>
        )}

        {phase === 'verifying' && (
          <p className="auth-gate__info">Verifying…</p>
        )}
      </div>
    </div>
  );
};
