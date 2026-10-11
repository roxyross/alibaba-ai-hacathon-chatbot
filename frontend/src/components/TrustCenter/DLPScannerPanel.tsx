import React, { useState, useEffect } from 'react';
import {
  FileLock2,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Copy,
  Check,
  Sparkles,
  Binary,
} from 'lucide-react';
import type {
  DLPRuleInfo,
  DLPScanResult,
  DLPMatch,
} from './types';

interface DLPScannerPanelProps {
  accessToken?: string | null;
  initialRules?: DLPRuleInfo[];
  initialScanResult?: DLPScanResult;
}

const DLP_PRESETS = [
  {
    name: 'Payment Card & Database URI',
    text: 'Client renewal on test card 4532-0150-1234-5671. Connect to postgres://superadmin:ProdSecret99!@db.internal:5432/roxy_core with API key sk-live-abc123def456ghi789jkl012mno345pqr678.',
  },
  {
    name: 'National ID & Personal Contact',
    text: 'Registered employee profile: National CNIC 42101-1234567-1, primary contact email roxy.support@acme.corp, phone +92-300-1234567.',
  },
  {
    name: 'IBAN Wire & SSH Private Key',
    text: 'Disbursement target: IBAN PK36SCBL0000001123456702.\nHost credential:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y3r...\n-----END RSA PRIVATE KEY-----',
  },
];

export const DLPScannerPanel: React.FC<DLPScannerPanelProps> = ({
  accessToken,
  initialRules,
  initialScanResult,
}) => {
  const [rules, setRules] = useState<DLPRuleInfo[]>(initialRules || []);
  const [loadingRules, setLoadingRules] = useState<boolean>(!initialRules);

  // Scanner State
  const [inputText, setInputText] = useState<string>(DLP_PRESETS[0].text);
  const [maskStyle, setMaskStyle] = useState<'tag' | 'mask'>('tag');
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanResult, setScanResult] = useState<DLPScanResult | null>(initialScanResult || null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    fetchRules();
  }, [accessToken]);

  const fetchRules = async () => {
    setLoadingRules(true);
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

      const res = await fetch('/api/v1/trust/dlp/rules', { headers });
      if (res.ok) {
        const data = await res.json();
        setRules(data);
      }
    } catch (err) {
      console.error('Failed to load DLP rules', err);
    } finally {
      setLoadingRules(false);
    }
  };

  const handleScan = async () => {
    if (!inputText.trim()) return;
    setScanError(null);
    setScanning(true);

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

      const res = await fetch('/api/v1/trust/dlp/scan', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          text: inputText,
          mask_style: maskStyle,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Scan failed with status ${res.status}`);
      }

      const result: DLPScanResult = await res.json();
      setScanResult(result);
    } catch (err: any) {
      setScanError(err.message || 'Error executing DLP scan');
    } finally {
      setScanning(false);
    }
  };

  const handleCopySanitized = () => {
    if (scanResult?.sanitized_text) {
      navigator.clipboard.writeText(scanResult.sanitized_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getSeverityColor = (sev: string) => {
    switch (sev.toUpperCase()) {
      case 'CRITICAL':
        return '#ef4444';
      case 'HIGH':
        return '#f97316';
      case 'MEDIUM':
        return '#eab308';
      default:
        return '#3b82f6';
    }
  };

  return (
    <div className="dlp-scanner-panel" role="region" aria-label="Data Loss Prevention Protections">
      {/* Header Info */}
      <div className="panel-subhead">
        <div>
          <h2>Algorithmic Data Loss Prevention (DLP) Protections</h2>
          <p className="panel-desc">
            Autonomous detection and redaction of payment cards (ISO/IEC 7812 Luhn mod-10), bank accounts (ISO 7064 mod-97 IBAN), API keys with Shannon entropy verification, cryptographic private keys, database URIs, and PII.
          </p>
        </div>
      </div>

      {/* Active Rules Grid */}
      <div className="dlp-rules-section">
        <div className="rules-section-title">
          <FileLock2 size={18} />
          <h3>Active Algorithmic Protection Rules ({rules.length})</h3>
        </div>

        {loadingRules ? (
          <div className="loading-state">Loading active DLP rules...</div>
        ) : (
          <div className="dlp-rules-grid">
            {rules.map((rule) => {
              const color = getSeverityColor(rule.severity);
              return (
                <div key={rule.category} className="dlp-rule-card">
                  <div className="rule-card-head">
                    <span className="rule-name">{rule.name}</span>
                    <span
                      className="rule-sev-badge"
                      style={{ backgroundColor: `${color}20`, color }}
                    >
                      {rule.severity}
                    </span>
                  </div>
                  <p className="rule-desc">{rule.description}</p>
                  <div className="rule-footer">
                    <span className="rule-method">
                      <Binary size={12} />
                      {rule.validation_method}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Interactive DLP Scanner Sandbox */}
      <div className="sandbox-card">
        <div className="sandbox-head">
          <div className="sandbox-head-title">
            <Sparkles size={18} className="sparkle-icon" />
            <h3>Live DLP Inspection & Redaction Sandbox</h3>
          </div>
          <span className="sandbox-badge">Real-Time Data Sanitizer</span>
        </div>

        {/* Preset Selection */}
        <div className="presets-row">
          <span className="presets-label">Test Samples:</span>
          <div className="presets-buttons">
            {DLP_PRESETS.map((p, idx) => (
              <button
                key={idx}
                type="button"
                className="preset-btn"
                onClick={() => {
                  setInputText(p.text);
                  setScanResult(null);
                  setScanError(null);
                }}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Controls Row */}
        <div className="dlp-controls-row">
          <div className="mask-style-selector">
            <span className="style-label">Redaction Format:</span>
            <label className="radio-label">
              <input
                type="radio"
                name="maskStyle"
                value="tag"
                checked={maskStyle === 'tag'}
                onChange={() => setMaskStyle('tag')}
              />
              Category Tag <code>[REDACTED_CREDIT_CARD]</code>
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="maskStyle"
                value="mask"
                checked={maskStyle === 'mask'}
                onChange={() => setMaskStyle('mask')}
              />
              Masked Suffix <code>************5671</code>
            </label>
          </div>
        </div>

        {/* Text Area */}
        <div className="form-group full-width">
          <label htmlFor="dlp-input-text">Unsanitized Input Text</label>
          <textarea
            id="dlp-input-text"
            rows={5}
            className="eval-textarea"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Type or paste payload, configuration files, SQL queries, or communication messages..."
          />
        </div>

        {scanError && <div className="eval-error">{scanError}</div>}

        <div className="evaluator-actions">
          <button
            type="button"
            className="evaluate-btn"
            disabled={scanning || !inputText.trim()}
            onClick={handleScan}
          >
            <FileLock2 size={16} />
            {scanning ? 'Inspecting Tokens & Checksums...' : 'Scan & Redact Sensitive Content'}
          </button>
        </div>

        {/* Scan Results */}
        {scanResult && (
          <div className="dlp-results-container">
            {/* Status Recommendation Banner */}
            <div className={`recommendation-banner rec-${scanResult.action_recommended}`}>
              <div className="banner-left">
                {scanResult.action_recommended === 'block' && <ShieldAlert size={22} />}
                {scanResult.action_recommended === 'warn' && <AlertTriangle size={22} />}
                {scanResult.action_recommended === 'allow' && <ShieldCheck size={22} />}
                <div>
                  <h4>
                    Policy Decision:{' '}
                    {scanResult.action_recommended === 'block' && 'EGRESS BLOCKED (Critical Secrets Detected)'}
                    {scanResult.action_recommended === 'warn' && 'WARNING: SENSITIVE PII DETECTED'}
                    {scanResult.action_recommended === 'allow' && 'PASSED: NO SENSITIVE DATA DETECTED'}
                  </h4>
                  <p>
                    Found {scanResult.total_violations} sensitive item(s).{' '}
                    {scanResult.action_recommended === 'block'
                      ? 'Payment instruments, private keys, or credentials must never leave trusted boundaries.'
                      : scanResult.action_recommended === 'warn'
                      ? 'Personally Identifiable Information detected and sanitized.'
                      : 'Zero data governance violations detected.'}
                  </p>
                </div>
              </div>
              <span className="violations-pill">
                {scanResult.total_violations} Violation{scanResult.total_violations === 1 ? '' : 's'}
              </span>
            </div>

            {/* Violations List */}
            {scanResult.matches.length > 0 && (
              <div className="violations-breakdown">
                <span className="breakdown-title">Algorithmic Violations Detected:</span>
                <div className="violations-table-wrapper">
                  <table className="violations-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Masked Pattern</th>
                        <th>Validation Check</th>
                        <th>Confidence</th>
                        <th>Position</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scanResult.matches.map((m: DLPMatch, idx: number) => (
                        <tr key={idx}>
                          <td>
                            <span className="violation-cat-badge">{m.category}</span>
                          </td>
                          <td className="code-cell">
                            <code>{m.matched_value_masked}</code>
                          </td>
                          <td>
                            {m.algorithm_validated ? (
                              <span className="algo-badge algo-valid">
                                <Check size={11} /> Checksum Verified
                              </span>
                            ) : (
                              <span className="algo-badge algo-regex">Pattern Match</span>
                            )}
                          </td>
                          <td>
                            <strong>{Math.round(m.confidence * 100)}%</strong>
                          </td>
                          <td className="pos-cell">
                            [{m.start}:{m.end}]
                          </td>
                          <td className="details-cell">{m.details}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Sanitized Text Preview */}
            {scanResult.sanitized_text && (
              <div className="sanitized-preview-box">
                <div className="preview-head">
                  <span className="preview-title">Sanitized Redacted Output:</span>
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={handleCopySanitized}
                    title="Copy Sanitized Text"
                  >
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                    {copied ? 'Copied!' : 'Copy Sanitized'}
                  </button>
                </div>
                <pre className="sanitized-text-content">{scanResult.sanitized_text}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
