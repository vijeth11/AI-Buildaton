export interface AuditEvent {
  event_type: string;
  actor: string;
  created_at: string;
  details: Record<string, unknown>;
}

export interface DecisionCheck {
  check: string;
  passed: boolean;
  reason: string;
  score?: number | null;
  threshold?: number;
  calculated_amount?: number;
}

export interface ClaimPhoto {
  photo_id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface ClaimDocument {
  document_id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  extraction_status: string;
  document_type: string;
  extracted_text?: string;
  extracted_fields: Record<string, string | number>;
}

export interface AgentStep {
  agent: string;
  status: string;
  detail: string;
  duration_ms: number;
  tokens_used: number;
  error_count: number;
}

export interface EvidenceCheck {
  check: string;
  status: string;
  detail: string;
  previous_claim_count?: number;
}

export interface AgentAssessment {
  status: 'completed' | 'unavailable' | 'error';
  error?: string | null;
  summary?: string;
  missing_or_ambiguous_fields?: string[];
  inconsistencies?: string[];
  extracted_facts?: Record<string, string>;
  risk_indicators?: string[];
  fraud_indicators?: string[];
  recommended_review?: boolean;
  rationale?: string;
  coverage_interpretation?: string;
  potentially_applicable_clauses?: string[];
  supporting_facts?: string[];
  unresolved_questions?: string[];
  advisory_recommendation?: string;
  confidence?: string;
}

export interface PolicySummary {
  policy_number: string;
  policyholder_name: string;
  vehicle_make: string;
  vehicle_model: string;
  vehicle_registration: string;
  coverage_summary: string;
  deductible: number;
  coverage_limit: number;
  active: boolean;
  fictional: true;
}

export interface ClaimRecord {
  claim_id: string;
  claimant_name: string;
  policy_number: string;
  loss_type: string;
  requested_amount: number;
  currency?: string;
  status: string;
  created_at?: string;
  incident_date?: string;
  incident_pincode?: string;
  incident_location?: string;
  loss_description?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  vehicle_registration?: string;
  coverage_summary?: string;
  route_category?: string;
  evidence: Array<{ kind: string; text: string }>;
  photos?: ClaimPhoto[];
  documents?: ClaimDocument[];
  agent_steps?: AgentStep[];
  evidence_checks?: EvidenceCheck[];
  adjudication?: {
    recommendation: string;
    rationale: string;
    risk_score: number | null;
    risk_threshold: number;
    fraud_score: number | null;
    fraud_threshold: number;
    estimated_settlement: number;
    automatic_payment_authorized: boolean;
    review_flags: string[];
    checks: DecisionCheck[];
    citations: Array<{ source_id: string; kind: string; snippet: string }>;
    reviewer_summary: string | null;
    confidence: string;
    settlement_calculations: Array<{ label: string; amount: number; operation: string }>;
    policy_clauses: Array<{ clause_id: string; title: string; summary: string }>;
    evidence_checks: EvidenceCheck[];
    orchestration_route: string;
    agent_assessments: {
      intake_agent?: AgentAssessment;
      fraud_risk_agent?: AgentAssessment;
      adjudication_agent?: AgentAssessment;
    };
  };
  payment: {
    payment_id: string;
    amount: number;
    currency: string;
    status: string;
    created_at: string;
  } | null;
  audit_events?: AuditEvent[];
}

export interface ClaimSubmission {
  policy_number: string;
  loss_type: string;
  loss_description: string;
  incident_date: string;
  incident_pincode: string;
  incident_location: string;
  garage_estimate: number;
  currency: 'INR';
  fictional: true;
}

export interface Metrics {
  period: 'today' | 'last_7_days';
  total_claims: number;
  status_counts: Record<string, number>;
  route_counts: Record<string, number>;
  review_queue_count: number;
  synthetic_payment_count: number;
  synthetic_payment_total: number;
  claim_runs: number;
  success_rate: number;
  p95_end_to_end_ms: number;
  tokens_used: number;
  average_tokens_per_claim: number;
  estimated_model_cost_usd: number | null;
  model_cost_pricing_configured: boolean;
  model_name: string;
  llm_agent_calls: number;
  llm_agent_unavailable: number;
  agent_performance: Array<{
    agent: string;
    runs: number;
    success_rate: number;
    p95_latency_ms: number;
    average_tokens: number;
    errors: number;
  }>;
  api_health: Array<{ name: string; status: string; detail: string }>;
}
