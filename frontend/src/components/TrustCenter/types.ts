export type RiskTier = 'low' | 'medium' | 'high' | 'critical';

export interface RiskMatrixTierRule {
  tier: RiskTier;
  score_range: string;
  description: string;
  safeguards: string[];
  requires_human_confirmation: boolean;
  requires_2fa: boolean;
}

export interface RiskMatrixConfig {
  version: string;
  tiers: Record<string, RiskMatrixTierRule>;
  category_weights: Record<string, number>;
  high_risk_actions: string[];
  destructive_sql_patterns: string[];
}

export interface RiskEvaluationResult {
  action_type: string;
  risk_score: number;
  risk_tier: RiskTier;
  requires_human_confirmation: boolean;
  requires_2fa: boolean;
  reasons: string[];
  suggested_safeguards: string[];
  evaluated_at: string;
}

export interface DLPRuleInfo {
  category: string;
  name: string;
  description: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  validation_method: string;
}

export interface DLPMatch {
  category: string;
  matched_value_masked: string;
  start: number;
  end: number;
  confidence: number;
  algorithm_validated: boolean;
  details: string;
}

export interface DLPScanResult {
  has_violations: boolean;
  total_violations: number;
  matches: DLPMatch[];
  sanitized_text: string | null;
  action_recommended: 'allow' | 'warn' | 'block';
}

export interface DLPRedactResult {
  original_length: number;
  redacted_length: number;
  violations_count: number;
  redacted_text: string;
}

export interface ConfirmationChallenge {
  challenge_id: string;
  action_type: string;
  title: string;
  summary: string;
  details: Record<string, any>;
  risk_tier: RiskTier;
  risk_score: number;
  requires_2fa: boolean;
  expires_at: string;
  ttl_seconds: number;
  created_at: string;
  challenge_token: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
}

export interface ConfirmationResolution {
  challenge_id: string;
  decision: 'approved' | 'rejected';
  resolved_at: string;
  status: string;
  audit_signature: string;
}

export interface TrustEvent {
  id: string;
  action_type: string;
  action_name: string;
  tool_id: string | null;
  risk_level: string;
  permission_policy: string;
  execution_status: string;
  verification_status: string;
  success: boolean;
  failure_code: string | null;
  failure_reason: string | null;
  rollback_supported: boolean;
  rollback_status: string;
  external_service: string | null;
  external_reference: string | null;
  created_at: string;
  verified_at: string | null;
}

export interface RecoveryJob {
  id: string;
  action_type: string;
  tool_id: string | null;
  failure_category: string;
  retry_count: number;
  max_retries: number;
  status: string;
  last_error: string | null;
  created_at: string;
}

export interface TrustDimensions {
  total_actions: number;
  action_verification: { rate: number; status: string; verified_count: number; failed_count: number };
  source_quality: { score: number; status: string };
  tool_reliability: { success_rate: number; successful_executions: number; failures: number };
  provider_availability: { uptime_rate: number; status: string };
  permission_compliance: { compliance_rate: number; status: string };
  execution_confidence: { level: string; evidence: string };
}
