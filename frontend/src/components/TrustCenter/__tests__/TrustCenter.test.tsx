import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { TrustCenter } from '../TrustCenter';
import { RiskMatrixPanel } from '../RiskMatrixPanel';
import { DLPScannerPanel } from '../DLPScannerPanel';
import { ConfirmationGatePanel } from '../ConfirmationGatePanel';
import type {
  RiskMatrixConfig,
  RiskEvaluationResult,
  DLPRuleInfo,
  DLPScanResult,
  ConfirmationChallenge,
  ConfirmationResolution,
} from '../types';

// Mock useAuth
vi.mock('../../../auth', () => ({
  useAuth: () => ({
    accessToken: 'mock_jwt_token',
    user: { id: 'usr_trust_test', email: 'tester@roxy.ai' },
  }),
}));

describe('Phase 21: Trust & Safety Center Component Suite', () => {
  const mockConfig: RiskMatrixConfig = {
    version: '2026.10',
    tiers: {
      low: {
        tier: 'low',
        score_range: '0-29',
        description: 'Read-only queries, local telemetry, benign operations.',
        safeguards: ['Logged to append-only audit trail'],
        requires_human_confirmation: false,
        requires_2fa: false,
      },
      medium: {
        tier: 'medium',
        score_range: '30-59',
        description: 'Staging environment edits, rate-limited egress.',
        safeguards: ['Logged to audit trail', 'Idempotency key enforced'],
        requires_human_confirmation: false,
        requires_2fa: false,
      },
      high: {
        tier: 'high',
        score_range: '60-79',
        description: 'Production writes, external messaging, financial outlays.',
        safeguards: ['Explicit human confirmation', 'Verification engine audit'],
        requires_human_confirmation: true,
        requires_2fa: false,
      },
      critical: {
        tier: 'critical',
        score_range: '80-100',
        description: 'Destructive schema drops, shell privilege escalation, large transfers.',
        safeguards: ['Mandatory step-up 2FA confirmation', 'Time-limited approval token'],
        requires_human_confirmation: true,
        requires_2fa: true,
      },
    },
    category_weights: {
      financial: 40,
      destructive_sql: 45,
      shell_command: 50,
      filesystem_destructive: 35,
      external_network: 30,
      permission_escalation: 35,
    },
    high_risk_actions: ['stripe.charge', 'db.execute', 'shell.exec'],
    destructive_sql_patterns: ['drop\\s+table', 'truncate\\s+table'],
  };

  const mockEvaluation: RiskEvaluationResult = {
    action_type: 'db.execute',
    risk_score: 95,
    risk_tier: 'critical',
    requires_human_confirmation: true,
    requires_2fa: true,
    reasons: ['Destructive SQL pattern matched: DROP TABLE', 'Target database environment is production'],
    suggested_safeguards: [
      'Require step-up 2FA confirmation PIN',
      'Create point-in-time database snapshot prior to execution',
    ],
    evaluated_at: new Date().toISOString(),
  };

  const mockRules: DLPRuleInfo[] = [
    {
      category: 'credit_card',
      name: 'Payment Cards (Visa/Mastercard/Amex/Discover)',
      description: 'Validated via mandatory ISO/IEC 7812 Luhn mod-10 algorithm.',
      severity: 'CRITICAL',
      validation_method: 'Regex + Luhn mod-10 checksum',
    },
    {
      category: 'iban',
      name: 'International Bank Account Number (IBAN)',
      description: 'Validated via ISO 7064 mod-97-10 checksum.',
      severity: 'CRITICAL',
      validation_method: 'Regex + ISO 7064 mod-97 algorithm',
    },
    {
      category: 'api_key',
      name: 'API Keys & High-Entropy Tokens',
      description: 'High-entropy cryptographic tokens and vendor-specific prefix signatures.',
      severity: 'CRITICAL',
      validation_method: 'Vendor Prefix + Shannon Entropy',
    },
    {
      category: 'national_id',
      name: 'Pakistani CNIC Numbers',
      description: '13-digit national identity numbers with hyphen formatting.',
      severity: 'HIGH',
      validation_method: 'Regex format matching',
    },
  ];

  const mockScanResult: DLPScanResult = {
    has_violations: true,
    total_violations: 2,
    action_recommended: 'block',
    sanitized_text: 'Billing on test card [REDACTED_CREDIT_CARD]. Connect with [REDACTED_API_KEY].',
    matches: [
      {
        category: 'credit_card',
        matched_value_masked: '4532-****-****-5671',
        start: 16,
        end: 35,
        confidence: 0.99,
        algorithm_validated: true,
        details: 'Valid Visa (ISO/IEC 7812 Luhn passed)',
      },
      {
        category: 'api_key',
        matched_value_masked: 'sk-live-************678',
        start: 50,
        end: 98,
        confidence: 0.95,
        algorithm_validated: false,
        details: 'Stripe Secret API Key',
      },
    ],
  };

  const mockPendingChallenges: ConfirmationChallenge[] = [
    {
      challenge_id: 'ch_test_99182',
      action_type: 'stripe.charge',
      title: 'Disburse $15,000 to International Supplier',
      summary: 'Wire payment to overseas logistics partner for cargo shipment.',
      details: {
        amount: 15000,
        currency: 'USD',
        vendor: 'Apex Freight Ltd',
        iban: 'PK36SCBL0000001123456702',
      },
      risk_tier: 'critical',
      risk_score: 92,
      requires_2fa: true,
      expires_at: new Date(Date.now() + 240000).toISOString(),
      ttl_seconds: 300,
      created_at: new Date().toISOString(),
      challenge_token: 'hmac_sha256_mock_token_abc123',
      status: 'pending',
    },
  ];

  const mockRecentResolutions: ConfirmationResolution[] = [
    {
      challenge_id: 'ch_test_99180',
      decision: 'approved',
      resolved_at: new Date().toISOString(),
      status: 'approved',
      audit_signature: 'hmac_sha256_audit_sig_9921820491820481204812',
    },
  ];

  describe('TrustCenter Main Dashboard', () => {
    it('renders the header, title, and all 5 command tabs', () => {
      const html = renderToString(<TrustCenter accessToken="mock_jwt_token" />);

      expect(html).toContain('Trust &amp; Safety Command Center');
      expect(html).toContain('Risk Matrix &amp; Posture');
      expect(html).toContain('DLP Protections &amp; Scanner');
      expect(html).toContain('Confirmations Gate');
      expect(html).toContain('Action History');
      expect(html).toContain('Recovery Queue');
    });

    it('renders the back button when onBack callback is passed', () => {
      const html = renderToString(
        <TrustCenter accessToken="mock_jwt_token" onBack={() => {}} />
      );
      expect(html).toContain('trust-back-btn');
      expect(html).toContain('Back');
    });
  });

  describe('RiskMatrixPanel', () => {
    it('renders the panel heading, evaluator sandbox, and presets', () => {
      const html = renderToString(<RiskMatrixPanel accessToken="mock_jwt_token" />);

      expect(html).toContain('Dynamic Multi-Dimensional Risk Matrix');
      expect(html).toContain('Live Action Risk Evaluator Sandbox');
      expect(html).toContain('Action Type');
      expect(html).toContain('Action Payload (JSON)');
      expect(html).toContain('Evaluate Operation Risk');
      expect(html).toContain('Drop Users Table (Critical)');
    });

    it('renders tiers and dimension weights when initialConfig is provided', () => {
      const html = renderToString(
        <RiskMatrixPanel accessToken="mock_jwt_token" initialConfig={mockConfig} />
      );

      expect(html).toContain('CRITICAL');
      expect(html).toContain('0-29');
      expect(html).toContain('80-100');
      expect(html).toContain('Destructive schema drops');
      expect(html).toContain('Risk Dimension Weights');
      expect(html).toContain('40');
      expect(html).toContain('pts');
    });

    it('renders risk evaluation score gauge and flags when initialEvaluation is provided', () => {
      const html = renderToString(
        <RiskMatrixPanel
          accessToken="mock_jwt_token"
          initialConfig={mockConfig}
          initialEvaluation={mockEvaluation}
        />
      );

      expect(html).toContain('95');
      expect(html).toContain('/ 100');
      expect(html).toContain('CRITICAL');
      expect(html).toContain('RISK');
      expect(html).toContain('Human Confirmation Required');
      expect(html).toContain('Step-Up 2FA Challenge Enforced');
      expect(html).toContain('Destructive SQL pattern matched: DROP TABLE');
    });
  });

  describe('DLPScannerPanel', () => {
    it('renders the algorithmic DLP header and scanner sandbox controls', () => {
      const html = renderToString(<DLPScannerPanel accessToken="mock_jwt_token" />);

      expect(html).toContain('Algorithmic Data Loss Prevention (DLP) Protections');
      expect(html).toContain('Live DLP Inspection &amp; Redaction Sandbox');
      expect(html).toContain('Scan &amp; Redact Sensitive Content');
      expect(html).toContain('Redaction Format');
      expect(html).toContain('Category Tag');
      expect(html).toContain('Masked Suffix');
    });

    it('renders active algorithmic protection rules when initialRules is passed', () => {
      const html = renderToString(
        <DLPScannerPanel accessToken="mock_jwt_token" initialRules={mockRules} />
      );

      expect(html).toContain('Payment Cards (Visa/Mastercard/Amex/Discover)');
      expect(html).toContain('International Bank Account Number (IBAN)');
      expect(html).toContain('API Keys &amp; High-Entropy Tokens');
      expect(html).toContain('Regex + Luhn mod-10 checksum');
      expect(html).toContain('CRITICAL');
    });

    it('renders violations breakdown, recommendation banner, and sanitized output when initialScanResult is passed', () => {
      const html = renderToString(
        <DLPScannerPanel
          accessToken="mock_jwt_token"
          initialRules={mockRules}
          initialScanResult={mockScanResult}
        />
      );

      expect(html).toContain('EGRESS BLOCKED (Critical Secrets Detected)');
      expect(html).toContain('4532-****-****-5671');
      expect(html).toContain('Checksum Verified');
      expect(html).toContain('Valid Visa (ISO/IEC 7812 Luhn passed)');
      expect(html).toContain('[REDACTED_CREDIT_CARD]');
    });
  });

  describe('ConfirmationGatePanel', () => {
    it('renders the confirmation gatekeeper header and simulator bar', () => {
      const html = renderToString(<ConfirmationGatePanel accessToken="mock_jwt_token" />);

      expect(html).toContain('Human-in-the-Loop Confirmation Gatekeeper');
      expect(html).toContain('Active Pending Approval Queue');
      expect(html).toContain('Simulate Challenge');
    });

    it('renders empty state when there are zero pending challenges', () => {
      const html = renderToString(
        <ConfirmationGatePanel accessToken="mock_jwt_token" initialChallenges={[]} />
      );

      expect(html).toContain('No Pending Approval Challenges');
    });

    it('renders pending challenge card with risk badges, countdown, 2FA PIN input, and approve/reject actions', () => {
      const html = renderToString(
        <ConfirmationGatePanel
          accessToken="mock_jwt_token"
          initialChallenges={mockPendingChallenges}
          initialResolutions={mockRecentResolutions}
        />
      );

      expect(html).toContain('Disburse $15,000 to International Supplier');
      expect(html).toContain('CRITICAL');
      expect(html).toContain('RISK');
      expect(html).toContain('Score:');
      expect(html).toContain('92');
      expect(html).toContain('Step-Up 2FA Challenge Enforced');
      expect(html).toContain('849201');
      expect(html).toContain('Reject &amp; Block');
      expect(html).toContain('Approve &amp; Execute');
      expect(html).toContain('Recent Cryptographically Signed Confirmations');
      expect(html).toContain('hmac_sha256_audit_sig_9921820491820481204812');
    });
  });
});
