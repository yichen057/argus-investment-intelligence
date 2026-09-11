import {
  Activity,
  AlertCircle,
  ChevronDown,
  Database,
  ExternalLink,
  FileSearch,
  FileText,
  Loader2,
  PieChart,
  PiggyBank,
  RefreshCw,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Upload,
  UserRound
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type HealthState =
  | { status: "checking" }
  | { status: "ok"; detail: string }
  | { status: "error"; detail: string };

type EtfSelectionEngine = "deterministic" | "model";

type NavItem = {
  id: string;
  label: string;
  icon: typeof FileSearch;
};

type DocumentSummary = {
  id: number;
  source_uri: string;
  source_type: string;
  title: string;
  content_hash: string;
  access_scope: string;
  parser_version: string;
  metadata: Record<string, unknown>;
};

type DocumentIngestResponse = {
  document_id: number;
  content_hash: string;
  created: boolean;
  evidence_count: number;
  chunk_count: number;
};

type DocumentPurgeResponse = {
  documents_deleted: number;
  upload_files_deleted: number;
  runs_deleted: number;
  reports_deleted: number;
};

type ChatQueryResponse = {
  run_id: number;
  run_key: string;
  status: string;
  answer: string;
  evidence_ids: number[];
  sources: ChatSource[];
  claims: ChatClaim[];
  critic: ChatCriticReview;
  iterations: number;
  total_tokens: number;
  total_estimated_cost_usd: number;
  selected_model: string | null;
  deployment: "local" | "cloud";
  prompt_tokens: number;
  completion_tokens: number;
  provider_tokens: number;
  execution_outcome: string;
  answer_generated: boolean;
  execution_message: string;
  evidence_scope: "indexed" | "web" | "hybrid";
  grounding_method: string;
  web_sources: Array<{
    citation_id: string;
    evidence_key: string;
    title: string;
    url: string;
    author: string | null;
    published_at: string | null;
    retrieved_at: string;
    excerpt: string;
  }>;
  style_pack_id: string;
  style_pack_name: string;
  method_document_id: number | null;
  method_document_name: string | null;
  method_document_ids: number[];
  method_document_names: string[];
  search: {
    mode?: "fast" | "standard" | "deep";
    complexity_score?: number;
    complexity_reasons?: string[];
    query_evidence_rubric?: string[];
    method_evidence_hints?: string[];
    agent_search_triggered?: boolean;
    answer_evidence_accepted?: boolean;
    accepted_evidence_ids?: number[];
    stop_reason?: string;
    evidence_gate?: {
      decision: "supported" | "gap" | "refuse";
      accepted_evidence_ids: number[];
      material_gaps: string[];
      follow_up_query: string | null;
      report_eligible: boolean;
      reasons: string[];
      evaluated_candidate_count: number;
    };
    queries?: Array<{
      round: number;
      query: string;
      target_slot: string;
      provider?: string;
      request_id?: string | null;
      search_type?: string;
      result_count?: number;
      result_urls?: string[];
      estimated_cost_usd?: number;
      channel_counts?: Record<string, number>;
      result_chunk_ids?: number[];
    }>;
  };
  search_provider: string | null;
  search_calls: number;
  search_estimated_cost_usd: number;
  answer_model_estimated_cost_usd: number;
  error_code: string | null;
};

type StylePackResponse = {
  builtin: boolean;
  definition: {
    schema_version: 1;
    id: string;
    name: string;
    description: string;
    research_lenses: string[];
    portfolio_priorities: string[];
    product_preferences: string[];
    report_section_order: string[];
    allocation_policy: Record<string, number>;
    references: Array<{
      institution: string;
      title: string;
      principle: string;
      url: string;
    }>;
    required_evidence_slots: Array<{
      id: string;
      description: string;
      search_terms: string[];
      query_template: string;
      minimum_items: number;
      minimum_distinct_sources: number;
      freshness_days: number | null;
      required: boolean;
    }>;
  };
};

type MethodDocumentResponse = {
  id: number;
  name: string;
  file_name: string;
  source_type: "markdown" | "text" | "pdf" | "csv" | "word";
  content_hash: string;
  character_count: number;
  checklist_items: string[];
  detected_lenses: string[];
  focus_terms: string[];
  warnings: string[];
};

type ChatModelOption = {
  id: string;
  label: string;
  deployment: "local" | "cloud";
  available: boolean;
  unavailable_reason: string | null;
  input_cost_per_million: number;
  output_cost_per_million: number;
  supports_market_search: boolean;
  supports_independent_web_search: boolean;
};

type ChatClaim = {
  claim_id: number | null;
  claim_key: string;
  claim_text: string;
  citation_ids: string[];
  evidence_ids: number[];
  relations: Record<string, string>;
  confidence: number;
  source_names: string[];
  verification_status: string;
  verification_findings: string[];
  verification_term_overlap: number;
};

type ChatCriticReview = {
  status: string;
  findings: ChatCriticFinding[];
};

type ChatCriticFinding = {
  code: string;
  severity: string;
  message: string;
};

type ChatSource = {
  evidence_id: number;
  display_name: string;
  source_uri: string;
  source_type: string;
  title: string;
  page_or_section: string | null;
};

type ReportResponse = {
  report_id: number;
  title: string;
  report_type: string;
  status: string;
  run_id: number;
  html_url: string;
  report_json: {
    schema_version: string;
    sections: Array<{ heading: string; body: string; evidence_ids: number[] }>;
    claims: Array<{ claim_text: string; evidence_ids: number[] }>;
    charts?: Array<{
      title: string;
      data?: Array<unknown>;
      series?: Array<unknown>;
    }>;
  };
};

type PortfolioSummaryResponse = {
  total_value: number;
  as_of_date: string | null;
  positions: PortfolioPosition[];
  allocation: AllocationSlice[];
  concentration_flags: ConcentrationFlag[];
  scenarios: ScenarioSuggestion[];
  rebalance_actions: RebalanceAction[];
  rebalance_scenarios: RebalanceScenario[];
  coverage_gaps: CoverageGap[];
  dca_suggestions: DcaSuggestion[];
  sector_candidates: InvestmentCandidate[];
  recommendation_context: RecommendationContext;
  cash_plan: CashPlan;
  retirement_plan: RetirementFundingPlan;
};

type RetirementFundingPlan = {
  status: string;
  current_age: number | null;
  retirement_age: number | null;
  plan_through_age: number;
  years_to_retirement: number | null;
  retirement_years: number | null;
  monthly_spending_today: number | null;
  monthly_reliable_income_today: number;
  monthly_reliable_income_after_tax: number | null;
  monthly_spending_gap: number | null;
  gross_monthly_portfolio_withdrawal: number | null;
  current_invested_assets: number;
  current_retirement_savings: number;
  current_savings_source: string;
  target_assets_at_retirement_today_dollars: number | null;
  target_assets_at_retirement: number | null;
  projected_current_assets_at_retirement: number | null;
  required_monthly_investment: number | null;
  estimated_monthly_take_home_cost: number | null;
  planned_monthly_investment: number;
  monthly_investment_gap: number | null;
  inflation_rate: number;
  annual_return: number;
  real_annual_return: number;
  accumulation_real_return: number;
  retirement_real_return: number;
  current_tax_rate: number | null;
  retirement_tax_rate: number | null;
  income_taxable: boolean;
  account_type: string | null;
  taxable_withdrawal_share: number | null;
  adjust_contributions_for_inflation: boolean;
  ending_balance_target: number;
  warnings: string[];
  guidance: string[];
  method: string;
};

type PortfolioUploadResponse = {
  import_id: string;
  positions_count: number;
  as_of_date: string;
  as_of_date_source: string;
  summary: PortfolioSummaryResponse;
};

type MarketMapTile = {
  symbol: string;
  name: string;
  group: string;
  exposure_key: string;
  latest_price: number | null;
  previous_close: number | null;
  previous_close_date: string | null;
  percent_change: number | null;
  volume: number | null;
  dollar_volume: number | null;
  volume_z_score: number | null;
  volume_activity: string;
  volume_observation_date: string | null;
  volume_reference_start: string | null;
  volume_reference_end: string | null;
  volume_reference_sessions: number;
  volume_observation_value: number | null;
  volume_reference_median: number | null;
  volume_reference_log_mad: number | null;
  volume_method: string;
  volume_quality: string;
  quote_observed_at: string | null;
  quote_status: string;
  directly_held: boolean;
  related_holdings: string[];
};

type MarketMapResponse = {
  provider_code: string;
  provider_key: string;
  provider_name: string;
  configured_provider_code: string;
  configured_provider_key: string;
  configured_provider_name: string;
  external_data_enabled: boolean;
  heatmap_enabled: boolean;
  unified_universe_enabled: boolean;
  is_live: boolean;
  is_delayed: boolean;
  status: string;
  message: string;
  generated_at: string;
  tiles: MarketMapTile[];
  portfolio_summary: PortfolioSummaryResponse;
};

type AlertSettings = {
  enabled: boolean;
  delivery_mode: "preview_only";
  scope: "holdings";
  sensitivity: "conservative" | "standard" | "active";
  timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  policy_version: number;
  telegram_available: boolean;
};

type MarketAlertPreview = {
  id: number;
  symbol: string;
  direction: "buy" | "reduce";
  severity: string;
  score: number;
  policy_version: number;
  status: string;
  holding_quantity: number;
  portfolio_weight: number;
  latest_close: number;
  market_as_of_date: string;
  holdings_as_of_date: string;
  reasons: string[];
  counter_evidence: string[];
  invalidation_conditions: string[];
  warnings: string[];
  metrics: Record<string, unknown>;
  feedback: "useful" | "noise" | "too_late" | "incorrect" | null;
  feedback_action: string | null;
  created_at: string;
};

type AlertListResponse = {
  settings: AlertSettings;
  alerts: MarketAlertPreview[];
};

type AlertEvaluationResponse = {
  created_count: number;
  suppressed_count: number;
  evaluated_symbols: number;
  alerts: MarketAlertPreview[];
};

type PortfolioPosition = {
  symbol: string;
  name: string;
  asset_class: string;
  quantity: number;
  price: number;
  market_value: number;
  cost_basis: number | null;
  account: string | null;
  source_key: string;
  source_scope: string;
  as_of_date: string;
  weight: number;
};

type AllocationSlice = {
  asset_class: string;
  market_value: number;
  weight: number;
};

type ConcentrationFlag = {
  code: string;
  severity: string;
  message: string;
  symbol: string | null;
  asset_class: string | null;
  weight: number | null;
  threshold: number | null;
  excess_percentage_points: number | null;
};

type ScenarioSuggestion = {
  scenario: string;
  rationale: string;
};

type InvestmentCandidate = {
  symbol: string;
  name: string;
  instrument_type: string;
  asset_class: string;
  portfolio_role: string;
  rationale: string;
  source_name: string;
  source_url: string;
  dca_eligible: boolean;
  satellite: boolean;
  candidate_category: string;
  issuer: string;
  exposure_key: string;
  related_holdings: string[];
  source_link_kind: "official_profile" | "issuer_directory";
  source_link_note: string;
  source_checked_at: string | null;
};

type RebalanceAction = {
  action: string;
  asset_class: string;
  symbol: string | null;
  name: string | null;
  amount: number;
  estimated_shares: number | null;
  reference_price: number | null;
  price_as_of_date: string | null;
  current_weight: number;
  target_weight: number;
  drift: number;
  reference_kind: string;
  reference_label: string;
  rationale: string;
  warnings: string[];
  asset_description: string;
  asset_url: string | null;
  asset_source: string | null;
};

type ScenarioAllocation = {
  asset_class: string;
  market_value: number;
  weight: number;
};

type ScenarioTrade = {
  action: string;
  asset_class: string;
  symbol: string | null;
  name: string | null;
  amount: number;
  estimated_shares: number | null;
  reference_price: number | null;
  price_as_of_date: string | null;
};

type RebalanceScenario = {
  code: string;
  title: string;
  description: string;
  rebalancing_amount: number;
  projected_total_value: number;
  projected_allocation: ScenarioAllocation[];
  trades: ScenarioTrade[];
  limitations: string[];
};

type CoverageGap = {
  asset_class: string;
  current_weight: number;
  target_weight: number | null;
  gap_amount: number | null;
  rationale: string;
  candidates: InvestmentCandidate[];
};

type DcaSuggestion = {
  asset_class: string;
  symbol: string | null;
  name: string | null;
  monthly_amount: number;
  estimated_shares: number | null;
  reference_price: number | null;
  price_as_of_date: string | null;
  rationale: string;
  warnings: string[];
  asset_description: string;
  asset_url: string | null;
  asset_source: string | null;
};

type CashGoal = {
  code: string;
  title: string;
  target_amount: number;
  allocated_current_savings: number;
  remaining_gap: number;
  months_remaining: number;
  monthly_required: number;
  deadline_label: string;
  rationale: string;
  priority: string;
  funding_status: "funded" | "partially_funded" | "not_funded";
};

type CashPlan = {
  status: string;
  as_of_date: string;
  current_cash_savings: number;
  total_target: number;
  remaining_gap: number;
  monthly_required: number;
  monthly_net_income: number | null;
  monthly_total_expenses: number | null;
  monthly_investment: number;
  monthly_capacity_for_cash_goals: number | null;
  monthly_shortfall: number | null;
  feasibility_status: string;
  primary_financial_priority: string | null;
  goals: CashGoal[];
  warnings: string[];
  guidance: string[];
  method: string;
};

type PlannedCashGoal = {
  goal_type: CashGoalType;
  target_amount: number | null;
  months_until_needed: number | null;
  priority: CashGoalPriority;
};

type CashGoalType =
  | "medical_care"
  | "home_or_appliance"
  | "vehicle"
  | "travel"
  | "tuition"
  | "insurance_or_tax"
  | "family_support"
  | "major_purchase";

type CashGoalPriority = "urgent" | "important" | "flexible";

type CashGoalFormItem = {
  goalType: CashGoalType;
  targetAmount: string;
  monthsUntilNeeded: string;
  priority: CashGoalPriority;
};

type MarketAnalysisResponse = {
  run_id: number;
  provider: string;
  model: string;
  generated_at: string;
  content: string;
  sources: Array<{ citation_id: string; title: string; url: string; retrieved_at: string }>;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  source_method: string;
  search_provider: string;
  search_calls: number;
  search_estimated_cost_usd: number;
  answer_model_estimated_cost_usd: number;
  answer_model_calls: number;
  style_pack_id: string;
  style_pack_name: string;
  method_document_id: number | null;
  method_document_name: string | null;
  method_document_ids: number[];
  method_document_names: string[];
  source_count: number;
  domain_count: number;
  limitations: string[];
  retrieved_result_count: number;
  retrieved_domain_count: number;
  gate_rejected_result_count: number;
  evidence_snapshot_id: string;
  candidate_parse_status: string;
  raw_candidate_count: number;
  candidate_audit: MarketCandidateAudit[];
  selection_engine: "deterministic" | "model";
  selection_version: string;
  auditor_version: string;
  audit_status: string;
  audit_codes: string[];
  watchlist: Array<{
    symbol: string;
    name: string;
    category: string;
    rationale: string;
    counter_evidence: string;
    invalidation_signal: string;
    overlap_risk: string;
    dca_guidance: string;
    dca_suitable: boolean;
    dca_monthly_amount: number;
    citation_ids: string[];
    recommendation_mode:
      | "new_exposure"
      | "diversifying_replacement"
      | "existing_holding_review";
  }>;
};

type MarketCandidateAudit = {
  index: number;
  symbol: string | null;
  requested_mode: string | null;
  expected_mode: string | null;
  supplied_citation_ids: string[];
  accepted_citation_ids: string[];
  present_fields: string[];
  accepted: boolean;
  validation_codes: string[];
  selection_source: string;
  eligible: boolean | null;
  rank: number | null;
  total_score: number | null;
  score_components: Record<string, number>;
  penalties: Record<string, number>;
  market_signal_as_of: string | null;
};

type CandidateAuditGroup = {
  key: string;
  decision: "selected" | "eligible_not_selected" | "ineligible";
  validationCodes: string[];
  outcomes: MarketCandidateAudit[];
};

type RecommendationContext = {
  status: string;
  portfolio_as_of_date: string | null;
  price_source: string;
  generated_at: string;
  live_market_data: boolean;
  analysis_method: string;
  analysis_method_description: string;
  policy: string;
  disclaimer: string;
};

type ProfileResponse = {
  id: number;
  risk_tolerance: string;
  life_stage: string | null;
  investment_horizon: string | null;
  investing_experience: string | null;
  income_stability: string | null;
  liquidity_needs: string | null;
  preferred_style: string | null;
  preferred_method_document_id: number | null;
  preferred_method_document_name: string | null;
  preferred_method_document_ids: number[];
  preferred_method_document_names: string[];
  target_allocation: Record<string, number>;
  monthly_net_income: number | null;
  monthly_contribution: number | null;
  monthly_sector_satellite_budget: number | null;
  monthly_total_expenses: number | null;
  primary_financial_priority: string | null;
  current_age: number | null;
  planned_retirement_age: number | null;
  retirement_planning_age: number;
  retirement_monthly_spending: number | null;
  retirement_monthly_income: number | null;
  retirement_current_savings: number | null;
  retirement_income_taxable: boolean;
  retirement_inflation_rate: number;
  retirement_current_tax_rate: number | null;
  retirement_tax_rate: number | null;
  retirement_annual_return: number;
  retirement_account_type: string | null;
  retirement_taxable_withdrawal_share: number | null;
  retirement_adjust_contributions_for_inflation: boolean;
  monthly_essential_expenses: number | null;
  current_cash_savings: number | null;
  emergency_fund_months: number;
  emergency_fund_target_amount: number | null;
  emergency_fund_build_months: number;
  education_plan: string;
  education_target_year: number | null;
  education_target_amount: number | null;
  near_term_goal_name: string | null;
  near_term_goal_amount: number | null;
  near_term_goal_months: number | null;
  cash_goals: PlannedCashGoal[];
  retirement_cash_months: number;
  calculated_retirement_cash_target: number | null;
  retirement_cash_target: number | null;
  rebalance_threshold: number;
  allow_fractional_shares: boolean;
  rebalance_preference: string;
  is_active: boolean;
};

type ProfileGuidanceResponse = {
  target_allocation: Record<string, number>;
  rationale: string[];
  warnings: string[];
  contribution_rate: number | null;
  method: string;
  method_summary: string;
  references: Array<{
    institution: string;
    title: string;
    principle: string;
    url: string;
  }>;
  disclaimer: string;
};

type ProfileFormState = {
  riskTolerance: string;
  lifeStage: string;
  investmentHorizon: string;
  investingExperience: string;
  incomeStability: string;
  liquidityNeeds: string;
  preferredStyle: string;
  preferredMethodDocumentIds: number[];
  equityTarget: string;
  bondTarget: string;
  commodityTarget: string;
  internationalEquityTarget: string;
  alternativesTarget: string;
  monthlyNetIncome: string;
  monthlyContribution: string;
  monthlySectorSatelliteBudget: string;
  monthlyTotalExpenses: string;
  primaryFinancialPriority: string;
  currentAge: string;
  plannedRetirementAge: string;
  monthlyEssentialExpenses: string;
  currentCashSavings: string;
  emergencyFundEnabled: boolean;
  emergencyFundMonths: string;
  emergencyFundTargetAmount: string;
  emergencyFundBuildMonths: string;
  educationPlan: string;
  educationTargetYear: string;
  educationTargetAmount: string;
  cashGoals: CashGoalFormItem[];
  retirementPlanningAge: string;
  retirementMonthlySpending: string;
  retirementMonthlyIncome: string;
  retirementCurrentSavings: string;
  retirementIncomeTaxable: boolean;
  retirementInflationRate: string;
  retirementCurrentTaxRate: string;
  retirementTaxRate: string;
  retirementAnnualReturn: string;
  retirementAccountType: string;
  retirementTaxableWithdrawalShare: string;
  retirementAdjustContributionsForInflation: boolean;
  rebalanceThreshold: string;
  allowFractionalShares: boolean;
  rebalancePreference: string;
};

type RunsDashboardResponse = {
  total_runs: number;
  total_tokens: number;
  total_estimated_cost_usd: number;
  failed_runs: number;
  model_call_count: number;
  tool_call_count: number;
  model_breakdown: ModelBreakdown[];
  retained_run_usage: UsageSummary;
  historical_api_usage: UsageSummary;
  historical_model_breakdown: ModelBreakdown[];
  provider_billing_snapshots: ProviderBillingSnapshot[];
  provider_account_snapshots: ProviderAccountSnapshot[];
  historical_usage_scope_note: string;
  event_pipeline: EventPipelineSummary;
  recent_runs: RunSummary[];
  limit: number;
  offset: number;
  has_more: boolean;
};

type EventPipelineEvent = {
  event_id: string;
  event_type: string;
  aggregate_id: string;
  status: string;
  attempt_count: number;
  duplicate_count: number;
  topic: string;
  partition: number | null;
  message_offset: number | null;
  occurred_at: string | null;
  processed_at: string;
  error_code: string | null;
  failure_code: string | null;
  run_status: string | null;
  execution_outcome: string | null;
  answer_generated: boolean | null;
  provider: string | null;
  model: string | null;
  failure_stage: string | null;
};

type EventPipelineSummary = {
  configured: boolean;
  transport: string;
  consumer_group: string;
  consumer_status: string;
  last_heartbeat_at: string | null;
  last_error_code: string | null;
  processed_count: number;
  completed_count: number;
  answer_generated_count: number;
  safe_stop_count: number;
  failed_count: number;
  duplicate_count: number;
  dlq_count: number;
  recent_events: EventPipelineEvent[];
  scope_note: string;
};

type RunSummary = {
  id: number;
  run_key: string;
  role: string;
  objective: string;
  status: string;
  sensitivity: string;
  as_of_date: string | null;
  selection_mode: string;
  selected_model: string | null;
  selection_reason: string | null;
  total_tokens: number;
  total_estimated_cost_usd: number;
  model_call_count: number;
  tool_call_count: number;
  created_at: string;
};

type ModelBreakdown = {
  provider: string;
  model: string;
  deployment: string;
  call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_estimated_cost_usd: number;
  avg_latency_ms: number | null;
  input_cost_per_million_usd: number | null;
  output_cost_per_million_usd: number | null;
};

type UsageSummary = {
  call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_estimated_cost_usd: number;
  first_recorded_at: string | null;
  last_recorded_at: string | null;
};

type ProviderBillingSnapshot = {
  id: number;
  provider: string;
  period_start: string;
  period_end: string;
  currency: string;
  actual_cost: number;
  total_tokens: number | null;
  request_count: number | null;
  source_reference: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

type ProviderAccountSnapshot = {
  id: number;
  provider: string;
  billing_tier: string | null;
  billing_status: string;
  currency: string | null;
  available_balance: number | null;
  paid_balance: number | null;
  promotional_balance: number | null;
  source_reference: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

type ProviderBalanceRefreshItem = {
  provider: string;
  status: "updated" | "not_configured" | "failed";
  message: string;
  snapshot: ProviderAccountSnapshot | null;
};

type ProviderBalanceRefreshResponse = {
  refreshed_at: string;
  updated_count: number;
  results: ProviderBalanceRefreshItem[];
};

type KafkaSortKey = "event_type" | "processed_at";
type SortDirection = "asc" | "desc";

type RunDetailResponse = {
  run: RunSummary;
  model_calls: ModelCallRecord[];
  tool_calls: ToolCallRecord[];
  decision_trace: PortfolioDecisionTrace | null;
};

type PortfolioDecisionTrace = {
  schema_version?: string;
  status?: string;
  failure_code?: string;
  selection_engine?: string;
  selection_engine_limitation?: string;
  selection_version?: string;
  auditor_version?: string;
  audit_status?: string;
  audit_codes?: string[];
  evidence_snapshot_id?: string;
  candidate_parse_status?: string;
  raw_candidate_count?: number;
  accepted_candidate_count?: number;
  rejected_candidate_count?: number;
  accepted_candidate_symbols?: string[];
  candidate_outcomes?: MarketCandidateAudit[];
  retention?: { role_limit?: number; max_age_days?: number; cache_used?: boolean };
};

type ModelCallRecord = {
  id: number;
  provider: string;
  model: string;
  deployment: string;
  serving_engine: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  latency_ms: number | null;
  success: boolean;
  created_at: string;
};

type ToolCallRecord = {
  id: number;
  call_id: string;
  tool_name: string;
  status: string;
  arguments: Record<string, unknown>;
  output: Record<string, unknown>;
  error_code: string | null;
  latency_ms: number | null;
  created_at: string;
};

type RequestState =
  | { status: "idle" }
  | { status: "loading"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

type QueryFailure = {
  code: string | null;
  runId: number | null;
  message: string;
};

class ApiRequestError extends Error {
  code: string | null;
  runId: number | null;

  constructor(message: string, code: string | null = null, runId: number | null = null) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.runId = runId;
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const MAX_METHOD_PANEL_DOCUMENTS = 5;

const navItems: NavItem[] = [
  { id: "research", label: "Research", icon: FileSearch },
  { id: "profile", label: "Profile", icon: UserRound },
  { id: "invest", label: "Invest Suggestions", icon: PieChart },
  { id: "planning", label: "Money Planning", icon: PiggyBank },
  { id: "runs", label: "Runs Management", icon: Activity }
];

const defaultProfileForm: ProfileFormState = {
  riskTolerance: "",
  lifeStage: "",
  investmentHorizon: "",
  investingExperience: "",
  incomeStability: "",
  liquidityNeeds: "",
  preferredStyle: "strategic_index",
  preferredMethodDocumentIds: [],
  equityTarget: "48",
  bondTarget: "32.5",
  commodityTarget: "7.5",
  internationalEquityTarget: "12",
  alternativesTarget: "0",
  monthlyNetIncome: "",
  monthlyContribution: "",
  monthlySectorSatelliteBudget: "",
  monthlyTotalExpenses: "",
  primaryFinancialPriority: "",
  currentAge: "",
  plannedRetirementAge: "",
  monthlyEssentialExpenses: "",
  currentCashSavings: "",
  emergencyFundEnabled: false,
  emergencyFundMonths: "0",
  emergencyFundTargetAmount: "",
  emergencyFundBuildMonths: "",
  educationPlan: "none",
  educationTargetYear: "",
  educationTargetAmount: "",
  cashGoals: [],
  retirementPlanningAge: "100",
  retirementMonthlySpending: "",
  retirementMonthlyIncome: "",
  retirementCurrentSavings: "",
  retirementIncomeTaxable: true,
  retirementInflationRate: "2.5",
  retirementCurrentTaxRate: "",
  retirementTaxRate: "",
  retirementAnnualReturn: "5",
  retirementAccountType: "",
  retirementTaxableWithdrawalShare: "",
  retirementAdjustContributionsForInflation: false,
  rebalanceThreshold: "5",
  allowFractionalShares: false,
  rebalancePreference: "contributions_first"
};

const lifeStageOptions = [
  "Student",
  "Early career, single",
  "Early career, partnered / family forming",
  "Mid career, married / partnered, no children",
  "Mid career, children at home",
  "Full-time caregiver / homemaker",
  "Peak earning years, children near or in college",
  "Pre-retirement",
  "Retired, financially supporting family",
  "Retired, independent / no dependents"
];

const investmentHorizonOptions = [
  "Under 3 years",
  "3-10 years",
  "10+ years"
];

const investingExperienceOptions = [
  "No experience",
  "Under 1 year",
  "1-3 years",
  "3-7 years",
  "7+ years"
];

const incomeStabilityOptions = [
  "Low",
  "Moderate",
  "High"
];

const cashGoalOptions: Array<{
  goalType: CashGoalType;
  label: string;
  description: string;
}> = [
  {
    goalType: "medical_care",
    label: "Planned medical / dental care",
    description: "Known bill, deductible, procedure, therapy, or dental expense."
  },
  {
    goalType: "home_or_appliance",
    label: "Home / appliance repair or replacement",
    description: "Move, repair, renovation, appliance, or housing-related need."
  },
  {
    goalType: "vehicle",
    label: "Vehicle purchase or major repair",
    description: "Down payment, replacement vehicle, or significant repair."
  },
  {
    goalType: "travel",
    label: "Travel",
    description: "A planned trip funded outside the investment portfolio."
  },
  {
    goalType: "tuition",
    label: "Tuition / education",
    description: "Near-term tuition, course, certificate, or school deposit."
  },
  {
    goalType: "insurance_or_tax",
    label: "Annual insurance / tax bill",
    description: "Predictable non-monthly premium, tax, or annual bill."
  },
  {
    goalType: "family_support",
    label: "Family support / caregiving",
    description: "Planned support for relatives, caregiving, or family formation."
  },
  {
    goalType: "major_purchase",
    label: "Other major purchase",
    description: "A known large purchase outside the preset categories."
  }
];

const liquidityNeedOptions = [
  "Low",
  "Moderate",
  "High",
  "High medical or care expenses"
];

function App() {
  const [activeNav, setActiveNav] = useState(navItems[0].id);
  const [health, setHealth] = useState<HealthState>({ status: "checking" });
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [query, setQuery] = useState("");
  const [reportTopic, setReportTopic] = useState("");
  const [asOfDate, setAsOfDate] = useState("");
  const [modelChoice, setModelChoice] = useState("");
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [evidenceScope, setEvidenceScope] =
    useState<"indexed" | "web" | "hybrid">("indexed");
  const [stylePacks, setStylePacks] = useState<StylePackResponse[]>([]);
  const [researchStyleId, setResearchStyleId] = useState("");
  const [methodDocuments, setMethodDocuments] = useState<MethodDocumentResponse[]>([]);
  const [methodDocumentIds, setMethodDocumentIds] = useState<number[]>([]);
  const [methodDocumentFile, setMethodDocumentFile] = useState<File | null>(null);
  const [methodDocumentState, setMethodDocumentState] =
    useState<RequestState>({ status: "idle" });
  const [ingestState, setIngestState] = useState<RequestState>({ status: "idle" });
  const [queryState, setQueryState] = useState<RequestState>({ status: "idle" });
  const [queryFailure, setQueryFailure] = useState<QueryFailure | null>(null);
  const [reportState, setReportState] = useState<RequestState>({ status: "idle" });
  const [chatResult, setChatResult] = useState<ChatQueryResponse | null>(null);
  const [reportResult, setReportResult] = useState<ReportResponse | null>(null);
  const [portfolioFile, setPortfolioFile] = useState<File | null>(null);
  const [portfolioAsOfDate, setPortfolioAsOfDate] = useState(todayInputValue());
  const [portfolioState, setPortfolioState] = useState<RequestState>({ status: "idle" });
  const [robinhoodSyncState, setRobinhoodSyncState] =
    useState<RequestState>({ status: "idle" });
  const [robinhoodEnabled, setRobinhoodEnabled] = useState(false);
  const [robinhoodSidecarConfigured, setRobinhoodSidecarConfigured] = useState(false);
  const [portfolioSummary, setPortfolioSummary] =
    useState<PortfolioSummaryResponse | null>(null);
  const [marketMap, setMarketMap] = useState<MarketMapResponse | null>(null);
  const [marketAnalysis, setMarketAnalysis] =
    useState<MarketAnalysisResponse | null>(null);
  const [marketAnalysisModel, setMarketAnalysisModel] = useState("");
  const [etfSelectionEngine, setEtfSelectionEngine] =
    useState<EtfSelectionEngine | null>(null);
  const [marketAnalysisState, setMarketAnalysisState] =
    useState<RequestState>({ status: "idle" });
  const [alertSettings, setAlertSettings] = useState<AlertSettings | null>(null);
  const [marketAlerts, setMarketAlerts] = useState<MarketAlertPreview[]>([]);
  const [alertState, setAlertState] =
    useState<RequestState>({ status: "idle" });
  const [profileState, setProfileState] = useState<RequestState>({ status: "idle" });
  const [profileForm, setProfileForm] =
    useState<ProfileFormState>(defaultProfileForm);
  const [profileResult, setProfileResult] = useState<ProfileResponse | null>(null);
  const [profileGuidance, setProfileGuidance] =
    useState<ProfileGuidanceResponse | null>(null);
  const [profileGuidanceState, setProfileGuidanceState] =
    useState<RequestState>({ status: "idle" });
  const [runsDashboard, setRunsDashboard] =
    useState<RunsDashboardResponse | null>(null);
  const [runsState, setRunsState] = useState<RequestState>({ status: "idle" });
  const [runDetail, setRunDetail] = useState<RunDetailResponse | null>(null);
  const [runDetailState, setRunDetailState] = useState<RequestState>({
    status: "idle"
  });
  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl}/health`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = (await response.json()) as {
          status: string;
          service: string;
          version: string;
          etf_selection_engine: EtfSelectionEngine;
          robinhood_enabled: boolean;
          robinhood_sidecar_configured: boolean;
        };
        setEtfSelectionEngine(payload.etf_selection_engine);
        setRobinhoodEnabled(payload.robinhood_enabled);
        setRobinhoodSidecarConfigured(payload.robinhood_sidecar_configured);
        setHealth({
          status: "ok",
          detail: `${payload.service} ${payload.version}`
        });
      })
      .catch((error: Error) => {
        if (error.name === "AbortError") {
          return;
        }
        setHealth({ status: "error", detail: error.message });
      });

    return () => controller.abort();
  }, []);

  const refreshDocuments = async () => {
    const payload = await fetchJson<DocumentSummary[]>("/documents");
    setDocuments(payload);
    setActiveDocumentId((current) => {
      if (current !== null && payload.some((document) => document.id === current)) {
        return current;
      }
      return null;
    });
  };

  const refreshStylePacks = async () => {
    const payload = await fetchJson<StylePackResponse[]>("/styles");
    setStylePacks(payload);
    setResearchStyleId((current) => (
      payload.some((pack) => pack.definition.id === current)
        ? current
        : ""
    ));
  };

  const refreshMethodDocuments = async () => {
    const payload = await fetchJson<MethodDocumentResponse[]>("/styles/method-documents");
    setMethodDocuments(payload);
    setMethodDocumentIds((current) => current.filter(
      (documentId) => payload.some((document) => document.id === documentId)
    ));
  };

  useEffect(() => {
    refreshDocuments().catch((error: Error) => {
      setIngestState({ status: "error", message: error.message });
    });
    fetchJson<ChatModelOption[]>("/chat/models")
      .then((options) => {
        setModelOptions(options);
        setModelChoice((current) => (
          options.some((option) => option.id === current && option.available)
            ? current
            : ""
        ));
        setMarketAnalysisModel((current) => (
          options.some((option) => option.id === current && option.supports_market_search)
            ? current
            : ""
        ));
      })
      .catch(() => setModelOptions([]));
    refreshStylePacks().catch(() => setStylePacks([]));
    refreshMethodDocuments().catch(() => setMethodDocuments([]));
  }, []);

  const refreshPortfolioSummary = async () => {
    const payload = await fetchJson<PortfolioSummaryResponse>("/portfolio/summary");
    setPortfolioSummary(payload);
  };

  const refreshMarketMap = async (refreshHistoricals = false) => {
    const suffix = refreshHistoricals ? "?refresh_historicals=true" : "";
    const payload = await fetchJson<MarketMapResponse>(`/portfolio/market-map${suffix}`);
    setMarketMap(payload);
    setPortfolioSummary(payload.portfolio_summary);
  };

  const refreshMarketAlerts = async () => {
    const payload = await fetchJson<AlertListResponse>("/portfolio/alerts");
    setAlertSettings(payload.settings);
    setMarketAlerts(payload.alerts);
  };

  useEffect(() => {
    refreshMarketMap().catch(() => {
      setMarketMap(null);
      refreshPortfolioSummary().catch(() => {
        setPortfolioSummary(null);
      });
    });
    fetchJson<ProfileResponse>("/profile")
      .then((payload) => {
        setProfileResult(payload);
        setProfileForm(profileFormFromResponse(payload));
        setMethodDocumentIds(payload.preferred_method_document_ids);
      })
      .catch(() => {
        setProfileResult(null);
      });
    refreshMarketAlerts().catch(() => {
      setAlertSettings(null);
      setMarketAlerts([]);
    });
  }, []);

  const refreshRuns = async (offset = 0) => {
    setRunsState({ status: "loading", message: "Loading runs" });
    try {
      const payload = await fetchJson<RunsDashboardResponse>(`/runs?limit=20&offset=${offset}`);
      setRunsDashboard(payload);
      setRunsState({ status: "success", message: "Runs loaded." });
      if (payload.recent_runs.length > 0 && runDetail === null) {
        await loadRunDetail(payload.recent_runs[0].id);
      }
    } catch (error) {
      setRunsState({
        status: "error",
        message: error instanceof Error ? error.message : "Runs load failed."
      });
    }
  };

  useEffect(() => {
    refreshRuns().catch(() => {
      setRunsDashboard(null);
    });
  }, []);

  const resetResearchResults = () => {
    setChatResult(null);
    setQueryFailure(null);
    setReportResult(null);
    setQueryState({ status: "idle" });
    setReportState({ status: "idle" });
  };

  const handleQueryChange = (value: string) => {
    setQuery(value);
    resetResearchResults();
  };

  const handleAsOfDateChange = (value: string) => {
    setAsOfDate(value);
    resetResearchResults();
  };

  const handleModelChoiceChange = (value: string) => {
    setModelChoice(value);
    resetResearchResults();
  };

  const handleEvidenceScopeChange = (value: "indexed" | "web" | "hybrid") => {
    setEvidenceScope(value);
    if (value !== "indexed") {
      const selected = modelOptions.find((option) => option.id === modelChoice);
      if (!selected?.supports_independent_web_search) {
        setModelChoice("");
      }
    }
    resetResearchResults();
  };

  const handleResearchStyleChange = (value: string) => {
    setResearchStyleId(value);
    resetResearchResults();
  };

  const handleMethodDocumentChange = (value: number[]) => {
    setMethodDocumentIds(value.slice(0, MAX_METHOD_PANEL_DOCUMENTS));
    resetResearchResults();
  };

  const uploadMethodDocument = async (file: File | null = methodDocumentFile) => {
    if (!file) {
      setMethodDocumentState({
        status: "error",
        message: "Choose a Markdown, TXT, Word DOC/DOCX, text-based PDF, or research CSV method document."
      });
      return;
    }
    setMethodDocumentState({ status: "loading", message: "Compiling safe method add-on" });
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch(`${apiBaseUrl}/styles/method-documents/upload`, {
        method: "POST",
        body: formData
      });
      const payload = await response.json() as MethodDocumentResponse | { detail: unknown };
      if (!response.ok) {
        throw new Error(
          typeof payload === "object" && payload !== null && "detail" in payload
            ? formatApiDetail(payload.detail)
            : `HTTP ${response.status}`
        );
      }
      const uploaded = payload as MethodDocumentResponse;
      await refreshMethodDocuments();
      setMethodDocumentFile(null);
      setMethodDocumentIds((current) => (
        current.includes(uploaded.id)
          ? current
          : [...current, uploaded.id].slice(-MAX_METHOD_PANEL_DOCUMENTS)
      ));
      setProfileForm((current) => ({
        ...current,
        preferredMethodDocumentIds: current.preferredMethodDocumentIds.includes(uploaded.id)
          ? current.preferredMethodDocumentIds
          : [...current.preferredMethodDocumentIds, uploaded.id].slice(
              -MAX_METHOD_PANEL_DOCUMENTS
            )
      }));
      resetResearchResults();
      setMethodDocumentState({
        status: "success",
        message: `${uploaded.file_name} compiled and added to the optional expert method panel.`
      });
    } catch (error) {
      setMethodDocumentFile(null);
      setMethodDocumentState({
        status: "error",
        message: error instanceof Error ? error.message : "Method document upload failed."
      });
    }
  };

  const deleteMethodDocument = async (documentId: number) => {
    setMethodDocumentState({ status: "loading", message: "Deleting method add-on" });
    try {
      await fetchNoContent(`/styles/method-documents/${documentId}`, { method: "DELETE" });
      setMethodDocumentIds((current) => current.filter((value) => value !== documentId));
      setProfileForm((current) => ({
        ...current,
        preferredMethodDocumentIds: current.preferredMethodDocumentIds.filter(
          (value) => value !== documentId
        )
      }));
      await Promise.all([refreshMethodDocuments(), refreshRuns()]);
      setRunDetail(null);
      resetResearchResults();
      setMethodDocumentState({ status: "success", message: "Expert method add-on deleted." });
    } catch (error) {
      setMethodDocumentState({
        status: "error",
        message: error instanceof Error ? error.message : "Method add-on deletion failed."
      });
    }
  };

  const handleResearchScopeChange = (documentId: number | null) => {
    setActiveDocumentId(documentId);
    resetResearchResults();
  };

  const handleReportTopicChange = (value: string) => {
    setReportTopic(value);
    setReportResult(null);
    setReportState({ status: "idle" });
  };

  const loadRunDetail = async (runId: number) => {
    setRunDetailState({ status: "loading", message: "Loading trace" });
    try {
      const payload = await fetchJson<RunDetailResponse>(`/runs/${runId}`);
      setRunDetail(payload);
      setRunDetailState({ status: "success", message: "Trace loaded." });
    } catch (error) {
      setRunDetailState({
        status: "error",
        message: error instanceof Error ? error.message : "Trace load failed."
      });
    }
  };

  const uploadDocument = async (file: File | null = sourceFile) => {
    if (file === null) {
      setIngestState({ status: "error", message: "Choose a source file." });
      return;
    }
    setIngestState({
      status: "loading",
      message: `Uploading ${file.name}`
    });
    try {
      const response = await fetch(`${apiBaseUrl}/documents/upload`, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Argus-Filename": encodeURIComponent(file.name)
        },
        body: file
      });
      const payload = (await response.json()) as DocumentIngestResponse | {
        detail: string | {
          code?: string;
          message?: string;
          stage?: string;
          observed?: number;
          limit?: number;
          next_action?: string;
        };
      };
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        if (typeof payload === "object" && payload !== null && "detail" in payload) {
          if (typeof payload.detail === "object" && payload.detail?.message) {
            message = formatDocumentResourceError(payload.detail);
          } else {
            message = String(payload.detail);
          }
        }
        throw new Error(`${file.name}: ${message}`);
      }
      await refreshDocuments();
      const uploaded = payload as DocumentIngestResponse;
      setSourceFile(null);
      setActiveDocumentId(uploaded.document_id);
      resetResearchResults();
      setIngestState({ status: "idle" });
    } catch (error) {
      setSourceFile(null);
      setIngestState({
        status: "error",
        message: error instanceof Error
          ? error.message
          : "Upload failed."
      });
    }
  };

  const deleteDocument = async (document: DocumentSummary) => {
    setIngestState({ status: "loading", message: "Deleting indexed source" });
    try {
      await fetchNoContent(`/documents/${document.id}`, { method: "DELETE" });
      await Promise.all([refreshDocuments(), refreshRuns()]);
      setRunDetail(null);
      resetResearchResults();
      setIngestState({ status: "idle" });
    } catch (error) {
      setIngestState({
        status: "error",
        message: error instanceof Error ? error.message : "Source deletion failed."
      });
    }
  };

  const deleteAllDocuments = async () => {
    setIngestState({ status: "loading", message: "Clearing all uploaded evidence" });
    try {
      const payload = await fetchJson<DocumentPurgeResponse>("/documents", {
        method: "DELETE"
      });
      await Promise.all([refreshDocuments(), refreshRuns()]);
      setActiveDocumentId(null);
      setRunDetail(null);
      resetResearchResults();
      setIngestState({
        status: "success",
        message: `Cleared ${payload.documents_deleted} evidence source(s), ${payload.upload_files_deleted} managed upload file(s), ${payload.runs_deleted} dependent Run(s), and ${payload.reports_deleted} Report(s).`
      });
    } catch (error) {
      setIngestState({
        status: "error",
        message: error instanceof Error ? error.message : "Evidence cleanup failed."
      });
    }
  };

  const askQuestion = async () => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setQueryState({ status: "error", message: "Enter a research question." });
      return;
    }
    if (evidenceScope !== "web" && documents.length === 0) {
      setQueryState({
        status: "error",
        message: "Indexed or combined research needs at least one uploaded source."
      });
      return;
    }
    setReportResult(null);
    setQueryFailure(null);
    setReportState({ status: "idle" });
    const selectedModel = modelOptions.find((option) => option.id === modelChoice);
    if (!selectedModel?.available) {
      setQueryState({
        status: "error",
        message: "Select an available answer model before asking. Argus does not choose one automatically."
      });
      return;
    }
    const usesExternalAi = selectedModel?.deployment === "cloud";
    if (evidenceScope !== "indexed" && !selectedModel?.supports_independent_web_search) {
      setQueryState({
        status: "error",
        message: "Select an available answer model that supports independent web research."
      });
      return;
    }
    setQueryState({
      status: "loading",
      message: evidenceScope === "web"
        ? "Searching cited public web sources"
        : evidenceScope === "hybrid"
          ? "Searching indexed evidence and cited public web sources"
        : usesExternalAi
        ? "Searching local evidence before external analysis"
        : "Searching local evidence"
    });
    try {
      const payload = await fetchJson<ChatQueryResponse>("/chat/query", {
        method: "POST",
        body: JSON.stringify({
          query: trimmedQuery,
          as_of_date: asOfDate || null,
          document_id: activeDocumentId,
          sensitivity: usesExternalAi ? "public" : "internal",
          selection_mode: "manual",
          requested_model: modelChoice,
          evidence_scope: evidenceScope,
          style_pack_id: researchStyleId || null,
          method_document_ids: methodDocumentIds
        })
      });
      if (payload.status !== "complete") {
        const message = payload.error_code === "provider_quota_exhausted"
          ? providerQuotaMessage(payload.selected_model ?? modelChoice)
          : `Research run failed: ${payload.error_code ?? payload.status}`;
        throw new Error(message);
      }
      setChatResult(payload);
      setQueryState({
        status: payload.answer_generated ? "success" : "error",
        message: payload.execution_outcome === "cloud_skipped_no_evidence"
          ? "No sufficiently relevant indexed passage was found; the external model call was skipped."
          : payload.execution_outcome === "cloud_declined_unsupported"
            ? "The external model ran, but the retrieved passages did not directly support an answer."
          : payload.execution_outcome === "web_skipped_no_supported_evidence"
            ? "No answer was generated. The Evidence Gate stopped before calling the selected answer model because it could not accept direct support."
          : payload.evidence_scope === "indexed"
            ? "Indexed answer ready."
            : "Cited web research ready. Open the returned URLs to verify important claims."
      });
    } catch (error) {
      setChatResult(null);
      if (error instanceof ApiRequestError && error.code !== null) {
        setQueryFailure({
          code: error.code,
          runId: error.runId,
          message: error.message
        });
      } else {
        setQueryFailure(null);
      }
      setQueryState({
        status: "error",
        message: error instanceof Error ? error.message : "Query failed."
      });
    }
  };

  const generateReport = async () => {
    const trimmedQuery = query.trim();
    const trimmedTopic = reportTopic.trim() || deriveReportTopic(trimmedQuery);
    if (chatResult === null || !isReportableChatResult(chatResult)) {
      setReportResult(null);
      setReportState({
        status: "error",
        message: "Ask first and get a source-backed answer before generating a report."
      });
      return;
    }
    if (!trimmedQuery && !trimmedTopic) {
      setReportState({
        status: "error",
        message: "Enter a question before generating a report."
      });
      return;
    }
    const sourceRunId = chatResult.run_id;
    setReportState({
      status: "loading",
      message: `Generating report from Trace ID ${sourceRunId}`
    });
    try {
      const payload = await fetchJson<ReportResponse>("/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          topic: trimmedTopic,
          question: trimmedQuery || null,
          source_run_id: sourceRunId
        })
      });
      setReportResult(payload);
      setReportState({ status: "success", message: "Report ready." });
    } catch (error) {
      setReportState({
        status: "error",
        message: error instanceof Error ? error.message : "Report generation failed."
      });
    }
  };

  const uploadPortfolio = async () => {
    if (!portfolioFile) {
      setPortfolioState({ status: "error", message: "Choose a CSV or Excel holdings file." });
      return;
    }
    setPortfolioState({ status: "loading", message: "Importing holdings" });
    try {
      const formData = new FormData();
      formData.append("file", portfolioFile);
      if (portfolioAsOfDate) {
        formData.append("as_of_date", portfolioAsOfDate);
      }
      const response = await fetch(`${apiBaseUrl}/portfolio/upload-file`, {
        method: "POST",
        body: formData
      });
      const payload = (await response.json()) as PortfolioUploadResponse | { detail?: string };
      if (!response.ok) {
        const detail =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? String(payload.detail)
            : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      const imported = payload as PortfolioUploadResponse;
      setPortfolioSummary(imported.summary);
      await refreshMarketMap();
      setPortfolioState({
        status: "success",
        message: `${imported.positions_count} position(s) imported.`
      });
    } catch (error) {
      setPortfolioState({
        status: "error",
        message: error instanceof Error ? error.message : "Portfolio upload failed."
      });
    }
  };

  const syncRobinhood = async () => {
    setRobinhoodSyncState({ status: "loading", message: "Reading positions" });
    try {
      const response = await fetch(`${apiBaseUrl}/portfolio/sync-robinhood`, {
        method: "POST"
      });
      const payload = (await response.json()) as PortfolioUploadResponse | { detail?: string };
      if (!response.ok) {
        const detail =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? String(payload.detail)
            : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      const synced = payload as PortfolioUploadResponse;
      setPortfolioSummary(synced.summary);
      await refreshMarketMap();
      setRobinhoodSyncState({
        status: "success",
        message: `${synced.positions_count} Robinhood position(s) refreshed.`
      });
    } catch (error) {
      setRobinhoodSyncState({
        status: "error",
        message: error instanceof Error ? error.message : "Robinhood refresh failed."
      });
    }
  };

  const evaluateMarketAlerts = async () => {
    setAlertState({ status: "loading", message: "Evaluating completed-session market data" });
    try {
      const payload = await fetchJson<AlertEvaluationResponse>("/portfolio/alerts/evaluate", {
        method: "POST"
      });
      await refreshMarketAlerts();
      setAlertState({
        status: "success",
        message: `${payload.evaluated_symbols} symbol(s) evaluated · ${payload.created_count} new preview(s) · ${payload.suppressed_count} cooled down.`
      });
    } catch (error) {
      setAlertState({
        status: "error",
        message: error instanceof Error ? error.message : "Alert preview failed."
      });
    }
  };

  const saveAlertSettings = async (value: AlertSettings) => {
    setAlertState({ status: "loading", message: "Saving alert settings" });
    try {
      const payload = await fetchJson<AlertSettings>("/portfolio/alerts/settings", {
        method: "PUT",
        body: JSON.stringify({
          enabled: value.enabled,
          delivery_mode: "preview_only",
          scope: "holdings",
          sensitivity: value.sensitivity,
          timezone: value.timezone,
          quiet_hours_start: value.quiet_hours_start,
          quiet_hours_end: value.quiet_hours_end
        })
      });
      setAlertSettings(payload);
      setAlertState({ status: "success", message: `Settings saved as policy v${payload.policy_version}.` });
    } catch (error) {
      setAlertState({
        status: "error",
        message: error instanceof Error ? error.message : "Settings save failed."
      });
    }
  };

  const submitAlertFeedback = async (
    alertId: number,
    feedback: "useful" | "noise" | "too_late" | "incorrect"
  ) => {
    try {
      const payload = await fetchJson<MarketAlertPreview>(
        `/portfolio/alerts/${alertId}/feedback`,
        { method: "POST", body: JSON.stringify({ feedback }) }
      );
      setMarketAlerts((current) => current.map((item) => item.id === alertId ? payload : item));
    } catch (error) {
      setAlertState({
        status: "error",
        message: error instanceof Error ? error.message : "Feedback save failed."
      });
    }
  };

  const generateMarketAnalysis = async () => {
    if (!marketAnalysisModel) {
      setMarketAnalysisState({
        status: "error",
        message: "Select an available answer model first."
      });
      return;
    }
    setMarketAnalysisState({ status: "loading", message: "Researching current market context" });
    setMarketAnalysis(null);
    try {
      const payload = await fetchJson<MarketAnalysisResponse>("/portfolio/market-analysis", {
        method: "POST",
        body: JSON.stringify({ requested_model: marketAnalysisModel })
      });
      setMarketAnalysis(payload);
      setMarketAnalysisState({ status: "success", message: "Market analysis ready." });
    } catch (error) {
      setMarketAnalysisState({
        status: "error",
        message: error instanceof Error ? error.message : "Market analysis failed."
      });
    }
  };

  const saveProfile = async () => {
    if (!profileForm.riskTolerance) {
      setProfileState({
        status: "error",
        message: "Select a risk tolerance before saving the profile."
      });
      return;
    }
    setProfileState({ status: "loading", message: "Saving profile" });
    try {
      const payload = await fetchJson<ProfileResponse>("/profile", {
        method: "POST",
        body: JSON.stringify(profilePayload(profileForm))
      });
      setProfileResult(payload);
      setProfileForm(profileFormFromResponse(payload));
      setMethodDocumentIds(payload.preferred_method_document_ids);
      await refreshPortfolioSummary();
      setProfileState({ status: "success", message: "Profile saved." });
    } catch (error) {
      setProfileState({
        status: "error",
        message: error instanceof Error ? error.message : "Profile save failed."
      });
    }
  };

  const generateProfileGuidance = async () => {
    if (!profileForm.riskTolerance) {
      setProfileGuidanceState({
        status: "error",
        message: "Select a risk tolerance before generating an allocation guide."
      });
      return;
    }
    setProfileGuidanceState({ status: "loading", message: "Building allocation guidance" });
    try {
      const payload = await fetchJson<ProfileGuidanceResponse>("/profile/guidance", {
        method: "POST",
        body: JSON.stringify(profileGuidancePayload(profileForm))
      });
      setProfileGuidance(payload);
      setProfileForm((current) => profileFormWithAllocation(current, payload.target_allocation));
      setProfileGuidanceState({
        status: "success",
        message: "Suggested percentages applied to the form but not saved. Review and edit them first."
      });
    } catch (error) {
      setProfileGuidanceState({
        status: "error",
        message: error instanceof Error ? error.message : "Allocation guidance failed."
      });
    }
  };

  const clearProfile = async () => {
    setProfileState({ status: "loading", message: "Clearing saved profile" });
    try {
      await fetchNoContent("/profile", { method: "DELETE" });
      setProfileResult(null);
      setProfileForm({ ...defaultProfileForm });
      setMethodDocumentIds([]);
      setProfileGuidance(null);
      setProfileGuidanceState({ status: "idle" });
      await refreshPortfolioSummary();
      setProfileState({
        status: "success",
        message: "Saved profile cleared. Example defaults restored; review and save them to make them active."
      });
    } catch (error) {
      setProfileState({
        status: "error",
        message: error instanceof Error ? error.message : "Profile clear failed."
      });
    }
  };

  const activeItem = useMemo(
    () => navItems.find((item) => item.id === activeNav) ?? navItems[0],
    [activeNav]
  );
  const ActiveIcon = activeItem.icon;
  const canGenerateReport = isReportableChatResult(chatResult);
  const activeDocument =
    documents.find((document) => document.id === activeDocumentId) ?? null;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>Argus</strong>
            <span>Local V1.1</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={item.id === activeNav ? "active" : ""}
                type="button"
                onClick={() => setActiveNav(item.id)}
              >
                <Icon aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="workspace" aria-labelledby="workspace-title">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">Development workspace</span>
            <h1 id="workspace-title">{activeItem.label}</h1>
          </div>
          <div className={`health-pill ${health.status}`}>
            <Database aria-hidden="true" />
            <span>
              {health.status === "checking" ? "Checking API" : health.detail}
            </span>
          </div>
        </header>

        <div className={`content-grid ${activeItem.id === "research" ? "" : "single-panel"}`}>
          <section className="primary-panel" aria-label={`${activeItem.label} panel`}>
            {activeItem.id === "research" ? (
              <ResearchWorkspace
                asOfDate={asOfDate}
                activeDocument={activeDocument}
                chatResult={chatResult}
                queryFailure={queryFailure}
                indexedSourceCount={documents.length}
                ingestState={ingestState}
                selectedFile={sourceFile}
                query={query}
                queryState={queryState}
                reportResult={reportResult}
                reportState={reportState}
                reportTopic={reportTopic}
                canGenerateReport={canGenerateReport}
                modelChoice={modelChoice}
                modelOptions={modelOptions}
                evidenceScope={evidenceScope}
                researchStyleId={researchStyleId}
                stylePacks={stylePacks}
                methodDocuments={methodDocuments}
                methodDocumentIds={methodDocumentIds}
                methodDocumentFile={methodDocumentFile}
                methodDocumentState={methodDocumentState}
                onAsOfDateChange={handleAsOfDateChange}
                onEvidenceScopeChange={handleEvidenceScopeChange}
                onModelChoiceChange={handleModelChoiceChange}
                onResearchStyleChange={handleResearchStyleChange}
                onMethodDocumentChange={handleMethodDocumentChange}
                onMethodDocumentFileChange={setMethodDocumentFile}
                onUploadMethodDocument={uploadMethodDocument}
                onGenerateReport={generateReport}
                onSelectedFileChange={setSourceFile}
                onUploadFile={uploadDocument}
                onQueryChange={handleQueryChange}
                onReportTopicChange={handleReportTopicChange}
                onSubmitQuery={askQuestion}
              />
            ) : activeItem.id === "invest" ? (
              <PortfolioWorkspace
                displayMode="invest"
                portfolioFile={portfolioFile}
                portfolioAsOfDate={portfolioAsOfDate}
                portfolioState={portfolioState}
                robinhoodSyncState={robinhoodSyncState}
                robinhoodEnabled={robinhoodEnabled}
                robinhoodSidecarConfigured={robinhoodSidecarConfigured}
                targetAllocation={profileResult?.target_allocation ?? {}}
                rebalanceThreshold={profileResult?.rebalance_threshold ?? null}
                summary={portfolioSummary}
                marketMap={marketMap}
                marketAnalysis={marketAnalysis}
                marketAnalysisModel={marketAnalysisModel}
                marketAnalysisState={marketAnalysisState}
                alertSettings={alertSettings}
                marketAlerts={marketAlerts}
                alertState={alertState}
                etfSelectionEngine={etfSelectionEngine}
                modelOptions={modelOptions}
                onGenerateMarketAnalysis={generateMarketAnalysis}
                onMarketAnalysisModelChange={setMarketAnalysisModel}
                onRefreshMarketMap={() => void refreshMarketMap(true)}
                onPortfolioFileChange={setPortfolioFile}
                onPortfolioAsOfDateChange={setPortfolioAsOfDate}
                onOpenMoneyPlanning={() => setActiveNav("planning")}
                onUpload={uploadPortfolio}
                onSyncRobinhood={syncRobinhood}
                onEvaluateAlerts={evaluateMarketAlerts}
                onSaveAlertSettings={saveAlertSettings}
                onAlertFeedback={submitAlertFeedback}
              />
            ) : activeItem.id === "profile" ? (
              <ProfileWorkspace
                form={profileForm}
                guidance={profileGuidance}
                guidanceState={profileGuidanceState}
                profile={profileResult}
                profileState={profileState}
                stylePacks={stylePacks}
                methodDocuments={methodDocuments}
                methodDocumentFile={methodDocumentFile}
                methodDocumentState={methodDocumentState}
                onChange={setProfileForm}
                onClear={clearProfile}
                onGenerateGuidance={generateProfileGuidance}
                onDeleteMethodDocument={deleteMethodDocument}
                onMethodDocumentChange={handleMethodDocumentChange}
                onMethodDocumentFileChange={setMethodDocumentFile}
                onSave={saveProfile}
                onUploadMethodDocument={uploadMethodDocument}
              />
            ) : activeItem.id === "planning" ? (
              <PortfolioWorkspace
                displayMode="planning"
                portfolioFile={portfolioFile}
                portfolioAsOfDate={portfolioAsOfDate}
                portfolioState={portfolioState}
                robinhoodSyncState={robinhoodSyncState}
                robinhoodEnabled={robinhoodEnabled}
                robinhoodSidecarConfigured={robinhoodSidecarConfigured}
                targetAllocation={profileResult?.target_allocation ?? {}}
                rebalanceThreshold={profileResult?.rebalance_threshold ?? null}
                summary={portfolioSummary}
                marketMap={marketMap}
                marketAnalysis={marketAnalysis}
                marketAnalysisModel={marketAnalysisModel}
                marketAnalysisState={marketAnalysisState}
                alertSettings={alertSettings}
                marketAlerts={marketAlerts}
                alertState={alertState}
                etfSelectionEngine={etfSelectionEngine}
                modelOptions={modelOptions}
                onGenerateMarketAnalysis={generateMarketAnalysis}
                onMarketAnalysisModelChange={setMarketAnalysisModel}
                onRefreshMarketMap={() => void refreshMarketMap(true)}
                onPortfolioFileChange={setPortfolioFile}
                onPortfolioAsOfDateChange={setPortfolioAsOfDate}
                onOpenMoneyPlanning={() => setActiveNav("planning")}
                onEditProfile={() => setActiveNav("profile")}
                onUpload={uploadPortfolio}
                onSyncRobinhood={syncRobinhood}
                onEvaluateAlerts={evaluateMarketAlerts}
                onSaveAlertSettings={saveAlertSettings}
                onAlertFeedback={submitAlertFeedback}
              />
            ) : activeItem.id === "runs" ? (
              <RunsWorkspace
                dashboard={runsDashboard}
                detail={runDetail}
                detailState={runDetailState}
                modelOptions={modelOptions}
                runsState={runsState}
                onRefresh={refreshRuns}
                onSelectRun={loadRunDetail}
              />
            ) : (
              <PlaceholderPanel activeIcon={ActiveIcon} label={activeItem.label} />
            )}
          </section>

          {activeItem.id === "research" && (
            <ResearchLibraryPanel
              activeDocumentId={activeDocumentId}
              activeMethodDocumentIds={methodDocumentIds}
              documents={documents}
              methodDocuments={methodDocuments}
              onDeleteAllDocuments={deleteAllDocuments}
              onDeleteDocument={deleteDocument}
              onDeleteMethodDocument={deleteMethodDocument}
              onSelectDocument={handleResearchScopeChange}
              onSelectMethodDocument={handleMethodDocumentChange}
            />
          )}
        </div>
      </section>
    </main>
  );
}

function ResearchWorkspace({
  asOfDate,
  activeDocument,
  chatResult,
  queryFailure,
  indexedSourceCount,
  ingestState,
  selectedFile,
  query,
  queryState,
  reportResult,
  reportState,
  reportTopic,
  canGenerateReport,
  modelChoice,
  modelOptions,
  evidenceScope,
  researchStyleId,
  stylePacks,
  methodDocuments,
  methodDocumentIds,
  methodDocumentFile,
  methodDocumentState,
  onAsOfDateChange,
  onEvidenceScopeChange,
  onModelChoiceChange,
  onResearchStyleChange,
  onMethodDocumentChange,
  onMethodDocumentFileChange,
  onUploadMethodDocument,
  onGenerateReport,
  onSelectedFileChange,
  onUploadFile,
  onQueryChange,
  onReportTopicChange,
  onSubmitQuery
}: {
  asOfDate: string;
  activeDocument: DocumentSummary | null;
  chatResult: ChatQueryResponse | null;
  queryFailure: QueryFailure | null;
  indexedSourceCount: number;
  ingestState: RequestState;
  selectedFile: File | null;
  query: string;
  queryState: RequestState;
  reportResult: ReportResponse | null;
  reportState: RequestState;
  reportTopic: string;
  canGenerateReport: boolean;
  modelChoice: string;
  modelOptions: ChatModelOption[];
  evidenceScope: "indexed" | "web" | "hybrid";
  researchStyleId: string;
  stylePacks: StylePackResponse[];
  methodDocuments: MethodDocumentResponse[];
  methodDocumentIds: number[];
  methodDocumentFile: File | null;
  methodDocumentState: RequestState;
  onAsOfDateChange: (value: string) => void;
  onEvidenceScopeChange: (value: "indexed" | "web" | "hybrid") => void;
  onModelChoiceChange: (value: string) => void;
  onResearchStyleChange: (value: string) => void;
  onMethodDocumentChange: (value: number[]) => void;
  onMethodDocumentFileChange: (value: File | null) => void;
  onUploadMethodDocument: (file?: File | null) => void;
  onGenerateReport: () => void;
  onSelectedFileChange: (value: File | null) => void;
  onUploadFile: (file?: File | null) => void;
  onQueryChange: (value: string) => void;
  onReportTopicChange: (value: string) => void;
  onSubmitQuery: () => void;
}) {
  const ingesting = ingestState.status === "loading";
  const querying = queryState.status === "loading";
  const reporting = reportState.status === "loading";
  const chatSources = chatResult?.sources ?? [];
  const chatClaims = chatResult?.claims ?? [];
  const reportUrl = reportResult ? `${apiBaseUrl}${reportResult.html_url}` : "";
  const selectedModel = modelOptions.find((option) => option.id === modelChoice);
  const selectedMethodDocuments = methodDocuments.filter(
    (document) => methodDocumentIds.includes(document.id)
  );
  const selectedStylePack = stylePacks.find(
    (pack) => pack.definition.id === researchStyleId
  );
  const resultModel = modelOptions.find((option) => option.id === chatResult?.selected_model);
  const needsIndexedSources = evidenceScope !== "web";
  const canAsk = !querying && (!needsIndexedSources || indexedSourceCount > 0)
    && Boolean(selectedModel?.available)
    && (evidenceScope === "indexed" || Boolean(selectedModel?.supports_independent_web_search));
  const askDisabledReason = querying
    ? "Research is running."
    : needsIndexedSources && indexedSourceCount === 0
      ? "Upload at least one evidence source for uploaded or combined research."
      : !selectedModel?.available
          ? "Select an available answer model."
          : evidenceScope !== "indexed" && !selectedModel.supports_independent_web_search
            ? "The selected answer model is not available for independent web research."
            : "Ask";
  const reportChecks = reportReadinessChecks(chatResult);

  return (
    <div className="research-workspace">
      <details className="research-setup-details">
        <summary>
          <span className="research-setup-action">
            <Upload aria-hidden="true" />
            <span>Upload sources &amp; methods</span>
            <ChevronDown className="research-setup-chevron" aria-hidden="true" />
          </span>
          <small>
            {selectedStylePack?.definition.name ?? "General evidence-first research"}
            {` · ${indexedSourceCount} evidence ${indexedSourceCount === 1 ? "source" : "sources"}`}
            {` · ${selectedMethodDocuments.length} expert ${selectedMethodDocuments.length === 1 ? "method" : "methods"} selected`}
          </small>
        </summary>
        <div className="research-input-kind-grid">
        <section className="upload-panel evidence-upload-panel" aria-label="Research evidence upload">
          <div className="upload-panel-header">
            <div className="input-kind-heading">
              <span>Evidence source</span>
              <strong>Upload documents to search</strong>
            </div>
            <input
              className="hidden-file-input"
              key={selectedFile ? `${selectedFile.name}-${selectedFile.size}` : "empty"}
              id="source-file"
              type="file"
              accept=".md,.txt,.pdf,.csv"
              disabled={ingesting}
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                onSelectedFileChange(file);
                if (file) {
                  onUploadFile(file);
                }
              }}
            />
            <label
              className={`compact-upload-trigger${ingesting ? " disabled" : ""}`}
              htmlFor="source-file"
            >
              {ingesting ? <Loader2 className="spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
              <span>{ingesting ? "Uploading…" : "Choose & upload"}</span>
            </label>
          </div>
          <p className="field-note">
            {selectedFile
              ? `${selectedFile.name} (${formatFileSize(selectedFile.size)})`
              : "Markdown, TXT, text PDF, or research CSV. These files are indexed as facts and citations."}
          </p>
          {ingestState.status !== "success" && <RequestStatus state={ingestState} />}
        </section>

        <section className="upload-panel method-upload-panel" aria-label="Research method composition">
          <div className="upload-panel-header">
            <div className="input-kind-heading">
              <span>Method, not evidence</span>
              <strong>Base framework + expert method panel</strong>
            </div>
            <input
              className="hidden-file-input"
              key={methodDocumentFile
                ? `${methodDocumentFile.name}-${methodDocumentFile.size}`
                : "empty-method-document"}
              id="research-method-file"
              type="file"
              accept=".md,.markdown,.txt,.doc,.docx,.pdf,.csv,text/markdown,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf,text/csv"
              disabled={methodDocumentState.status === "loading"}
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                onMethodDocumentFileChange(file);
                if (file) {
                  onUploadMethodDocument(file);
                }
              }}
            />
            <label
              className={`compact-upload-trigger${methodDocumentState.status === "loading" ? " disabled" : ""}`}
              htmlFor="research-method-file"
            >
              {methodDocumentState.status === "loading"
                ? <Loader2 className="spin" aria-hidden="true" />
                : <Upload aria-hidden="true" />}
              <span>{methodDocumentState.status === "loading" ? "Compiling…" : "Choose & upload"}</span>
            </label>
          </div>
          <label className="method-composition-field" htmlFor="research-method-pack">
            1. Base investment framework (optional)
            <select
              id="research-method-pack"
              value={researchStyleId}
              onChange={(event) => onResearchStyleChange(event.target.value)}
            >
              <option value="">No framework · neutral evidence-first research</option>
              {stylePacks.map((pack) => (
                <option key={pack.definition.id} value={pack.definition.id}>
                  {pack.definition.name}{pack.builtin ? "" : " · custom"}
                </option>
              ))}
            </select>
            <small className="framework-description" aria-live="polite">
              <strong>Framework focus · 框架侧重点</strong>
              <span>
                {selectedStylePack
                  ? selectedStylePack.definition.description
                  : "Argus will use neutral evidence-first research. Choose a framework only when you want a specific investment lens, evidence checklist, and report order."}
              </span>
            </small>
          </label>
          <div className="method-and-divider" aria-hidden="true"><span>+</span></div>
          <div className="method-active-row">
            <div className="method-active-summary">
              <span>2. Expert methods (optional · up to 5)</span>
              <div className="selected-method-list">
                {selectedMethodDocuments.length > 0
                  ? selectedMethodDocuments.map((item) => (
                      <strong className="selected-method-chip" key={item.id}>{item.name}</strong>
                    ))
                  : <strong className="selected-method-empty">None selected</strong>}
              </div>
            </div>
            {selectedMethodDocuments.length > 0 && (
              <button type="button" onClick={() => onMethodDocumentChange([])}>
                Clear
              </button>
            )}
          </div>
          <p className="field-note">
            Markdown, TXT, Word DOC/DOCX, text PDF, or research CSV. Uploads are compiled as method checklists,
            never indexed as facts. Select up to five saved methods in the library. Argus
            compares agreements and conflicts; it does not run an unbounded multi-model debate.
          </p>
          {methodDocumentState.status !== "success" && <RequestStatus state={methodDocumentState} />}
        </section>
        </div>
      </details>

      <form
        className="input-stack question-stack"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmitQuery();
        }}
      >
        <label className="research-question-label" htmlFor="research-question">Ask a research question</label>
        <p className="field-note">
          {evidenceScope === "web"
            ? "Search scope: cited public web sources; uploaded files are not sent."
            : activeDocument
            ? `Search scope: ${documentDisplayName(activeDocument)}`
            : indexedSourceCount > 0
            ? `Search scope: all ${indexedSourceCount} indexed source(s)${evidenceScope === "hybrid" ? " plus cited web sources" : ""}`
            : "No indexed evidence is available. Open Sources & methods to upload a source, or choose public web sources below."}
        </p>
        <textarea
          id="research-question"
          rows={4}
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="What would you like Argus to research?"
        />

        <section className="research-route-panel" aria-label="Research connection and model">
          <label className="model-field" htmlFor="evidence-scope">
            Where should Argus search?
            <select
              id="evidence-scope"
              value={evidenceScope}
              onChange={(event) => onEvidenceScopeChange(
                event.target.value as "indexed" | "web" | "hybrid"
              )}
            >
              <option value="indexed">Uploaded / indexed sources only</option>
              <option value="web">Cited public web sources only</option>
              <option value="hybrid">Uploaded sources + cited public web</option>
            </select>
          </label>
          <label className="model-field" htmlFor="model-choice">
            Answer model
            <select
              id="model-choice"
              value={modelChoice}
              onChange={(event) => onModelChoiceChange(event.target.value)}
            >
              <option value="" disabled>Select an answer model (required)</option>
              {modelOptions.map((option) => (
                <option
                  key={option.id}
                  value={option.id}
                  disabled={!option.available || (
                    evidenceScope !== "indexed" && !option.supports_independent_web_search
                  )}
                >
                  {option.label}{option.available ? "" : " · unavailable"}
                </option>
              ))}
            </select>
          </label>
          <div className="route-guidance route-explanation">
            <p>
              {evidenceScope === "indexed"
                ? "Uploaded-only research extracts directly supported passages without an internet search."
                : evidenceScope === "web"
                ? "Public-web research retrieves direct-URL evidence first; the selected answer model writes only from evidence accepted by Argus."
                : "Combined research checks uploaded passages and direct-URL web evidence before the selected answer model writes."}
            </p>
            <p>
              Choose an available answer model for each page session. Argus does not auto-select,
              invoke model-provided web search, or silently switch models. Search and model usage
              are tracked separately.
            </p>
            {evidenceScope === "web" && indexedSourceCount > 0 && (
              <p>
                Web-only mode excludes uploaded files. Choose uploaded or combined search to include them.
              </p>
            )}
          </div>
        </section>
        <div className="research-question-footer">
          <label className="date-field compact-date-field" htmlFor="as-of-date">
            Historical evidence cutoff (optional)
            <input
              id="as-of-date"
              type="date"
              value={asOfDate}
              onChange={(event) => onAsOfDateChange(event.target.value)}
            />
            <small>Only use evidence dated on or before this day; leave blank for no cutoff.</small>
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={!canAsk}
            title={askDisabledReason}
          >
            {querying ? <Loader2 className="spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
            <span>Ask</span>
          </button>
        </div>
        <details className="report-test-walkthrough">
          <summary>Known-good Report Generation test examples · CSV or text</summary>
          <h4>Option A · structured CSV</h4>
          <ol>
            <li>Choose &amp; upload <code>examples/research/gold_macro_indicators.csv</code>.</li>
            <li>Select <strong>Uploaded / indexed sources only</strong> and the local evidence model.</li>
            <li>
              Ask the exact tested question:
              <button
                className="inline-example-button"
                type="button"
                onClick={() => onQueryChange(
                  "How did gold return real yield ETF flows and central bank demand trend?"
                )}
              >
                Fill example question
              </button>
            </li>
            <li>After all readiness checks turn green, click Generate HTML report.</li>
          </ol>
          <p>
            This CSV contains five annual observations and is intentionally structured
            to exercise claims, citations, trend charts, and the Evidence Gate without
            spending external-model tokens.
          </p>
          <h4>Option B · Markdown text</h4>
          <ol>
            <li>Choose &amp; upload <code>examples/research/gold_real_yields.md</code>.</li>
            <li>Select <strong>Uploaded / indexed sources only</strong> and the local evidence model.</li>
            <li>
              Ask:
              <button
                className="inline-example-button"
                type="button"
                onClick={() => onQueryChange(
                  "Why might gold benefit when real yields fall?"
                )}
              >
                Fill text-document question
              </button>
            </li>
            <li>Generate the report after citations and readiness checks pass.</li>
          </ol>
          <p>
            Markdown, TXT, and text-based PDF can generate reports too. The document
            must contain complete passages that answer the question; CSV is only a
            special case that makes numeric charts easier to generate.
          </p>
        </details>
        <RequestStatus state={queryState} />
      </form>

      {queryFailure && (
        <section className="answer-block failed-answer-block" aria-label="Research run failure">
          <div className="answer-header">
            <h2>Answer</h2>
            <span className="run-status failed">MODEL CALL FAILED</span>
          </div>
          <p>
            No answer was generated. Evidence already collected for this failed Run remains
            available in Runs Management for diagnosis.
          </p>
          <div className="source-row">
            {queryFailure.runId !== null && <span>Run ID: {queryFailure.runId}</span>}
            <span>Error: {humanizeErrorCode(queryFailure.code)}</span>
          </div>
        </section>
      )}

      {chatResult && (
        <section className="answer-block" aria-label="Agent answer">
          <div className="answer-header">
            <h2>Answer</h2>
            <span className={`run-status ${chatResult.answer_generated ? "complete" : "warning"}`}>
              {chatResult.answer_generated ? "ANSWER GENERATED" : "NO ANSWER · SAFE STOP"}
            </span>
          </div>
          <ResearchAnswer value={chatResult.answer} />
          <div className="source-row">
            {chatSources.length > 0
              ? chatSources.map((source) => (
                  <span key={source.evidence_id}>Source: {source.display_name}</span>
                ))
              : <span>No supporting source was accepted for this answer.</span>}
          </div>
          {chatResult.web_sources.length > 0 && (
            <div className="guidance-references">
              <strong>Argus-validated web evidence</strong>
              <ul>
                {chatResult.web_sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      [{source.citation_id}] {source.title}
                    </a>
                    <span>
                      {source.published_at
                        ? `Published ${formatTimestamp(source.published_at)} · `
                        : ""}
                      Retrieved {formatTimestamp(source.retrieved_at)}
                    </span>
                    <p>{source.excerpt}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {chatSources.length > 0 && (
            <CitationPanel sources={chatSources} claims={chatClaims} />
          )}
          {chatResult.critic.status !== "passed" && chatResult.critic.status !== "web_evidence_validated" && (
            <CriticPanel critic={chatResult.critic} />
          )}
          <details className="cost-explanation answer-audit-details">
            <summary>Audit, search, and cost details</summary>
            <dl className="run-metrics">
              <div><dt>Trace ID</dt><dd>{chatResult.run_id}</dd></div>
              <div><dt>Agent steps</dt><dd>{chatResult.iterations}</dd></div>
              {chatResult.search.mode && (
                <div><dt>Search mode</dt><dd>{chatResult.search.mode}</dd></div>
              )}
              {chatResult.deployment === "cloud" && (
                <>
                  <div><dt>Search provider</dt><dd>{chatResult.search_provider ?? "none"}</dd></div>
                  <div><dt>Search calls</dt><dd>{chatResult.search_calls}</dd></div>
                  <div><dt>Search cost</dt><dd>{formatCost(chatResult.search_estimated_cost_usd)}</dd></div>
                  <div><dt>Answer-model tokens</dt><dd>{chatResult.provider_tokens}</dd></div>
                  <div><dt>Answer-model cost</dt><dd>{formatCost(chatResult.answer_model_estimated_cost_usd)}</dd></div>
                  <div><dt>Total estimated cost</dt><dd>{formatCost(chatResult.total_estimated_cost_usd)}</dd></div>
                </>
              )}
            </dl>
            <p>{chatResult.execution_message}</p>
            <p>
              Evidence scope: {chatResult.evidence_scope}. Grounding: {chatResult.grounding_method}.
              Base framework: {chatResult.style_pack_name}. Expert method add-on:
              {` ${chatResult.method_document_name ?? "none"}`}.
            </p>
            {chatResult.search.mode && (
              <p>
                Search budget: {chatResult.search.mode} (complexity score {chatResult.search.complexity_score ?? 0}).
                Evidence Gate: {chatResult.search.evidence_gate?.decision ?? "not recorded"}.
                Targeted follow-up: {chatResult.search.agent_search_triggered ? "used" : "not needed or not allowed"}.
                Queries: {chatResult.search.queries?.length ?? 0}. Stop reason:
                {` ${chatResult.search.stop_reason ?? "not recorded"}`}.
              </p>
            )}
            {(chatResult.search.evidence_gate?.material_gaps.length ?? 0) > 0 && (
              <p>
                Material evidence gap: {chatResult.search.evidence_gate?.material_gaps.join(" ")}
              </p>
            )}
            {chatResult.deployment === "cloud" && (
              <>
                <p>
                  Answer-model estimate = {chatResult.prompt_tokens.toLocaleString()} input tokens ÷ 1,000,000 ×
                  ${resultModel?.input_cost_per_million ?? 0} + {chatResult.completion_tokens.toLocaleString()}
                  output tokens ÷ 1,000,000 × ${resultModel?.output_cost_per_million ?? 0}.
                </p>
                <p>
                  Total estimate = independent search cost + answer-model token cost.
                  Provider dashboards remain the billing source of truth.
                </p>
              </>
            )}
            {chatClaims.length > 0 && (
              <p>Structured claims: {chatClaims.map((claim) => cleanModelMarkdown(claim.claim_text)).join(" · ")}</p>
            )}
          </details>
        </section>
      )}

      {chatResult && (
        <section className="report-builder" aria-label="Report builder">
          <div className="answer-header">
            <h2>Research report</h2>
            <span>Trace ID {chatResult.run_id}</span>
          </div>
          <p className="field-note">
            Generates an HTML report from the current source-backed answer without rerunning Ask.
          </p>
          <div
            className={`report-readiness${canGenerateReport ? " ready" : " not-ready"}`}
            aria-label="Report readiness checks"
          >
            <strong>{canGenerateReport ? "Report ready" : "Report not ready"}</strong>
            <ul>
              {reportChecks.map((check) => (
                <li className={check.passed ? "passed" : "failed"} key={check.label}>
                  <span aria-hidden="true">{check.passed ? "✓" : "○"}</span>
                  {check.label}
                </li>
              ))}
            </ul>
          </div>
          <label className="advanced-field" htmlFor="report-topic">
            Report topic optional
            <div className="input-action-row">
              <input
                id="report-topic"
                type="text"
                value={reportTopic}
                onChange={(event) => onReportTopicChange(event.target.value)}
                placeholder="Auto-generated from question"
                disabled={!canGenerateReport}
              />
              <button
                className="report-button"
                type="button"
                disabled={reporting || !canGenerateReport}
                title={
                  canGenerateReport
                    ? "Generate report from current answer"
                    : "A report requires a source-backed answer."
                }
                onClick={onGenerateReport}
              >
                {reporting ? <Loader2 className="spin" aria-hidden="true" /> : <FileText aria-hidden="true" />}
                <span>Generate HTML report</span>
              </button>
            </div>
          </label>
          {!canGenerateReport && (
            <p className="request-status error report-quality-message">
              A short extract may remain useful, but Argus will not inflate it into a repetitive
              report. Refine the question or collect broader evidence until every check passes.
            </p>
          )}
          <RequestStatus state={reportState} />
          {reportResult && (
            <div className="generated-report-summary" aria-label="Generated report">
              <div className="report-summary">
                <strong>{reportResult.title}</strong>
                <span className={`run-status ${reportResult.status}`}>{reportResult.status}</span>
                <span>{reportResult.report_json.claims.length} claim(s)</span>
                <span>{reportResult.report_json.charts?.length ?? 0} chart(s)</span>
              </div>
              <a className="report-link" href={reportUrl} target="_blank" rel="noreferrer">
                <ExternalLink aria-hidden="true" />
                <span>Open HTML report</span>
              </a>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function CitationPanel({
  sources,
  claims
}: {
  sources: ChatSource[];
  claims: ChatClaim[];
}) {
  const claimByEvidence = new Map<number, string[]>();
  for (const claim of claims) {
    for (const evidenceId of claim.evidence_ids) {
      const existing = claimByEvidence.get(evidenceId) ?? [];
      existing.push(claim.claim_text);
      claimByEvidence.set(evidenceId, existing);
    }
  }

  return (
    <section className="citation-panel" aria-label="Citation details">
      <h3>Citations</h3>
      <ul>
        {sources.map((source) => (
          <li key={source.evidence_id}>
            <div className="citation-heading">
              <strong>Evidence #{source.evidence_id}</strong>
              <span>{source.source_type}</span>
            </div>
            <span>{source.display_name}</span>
            {source.page_or_section && <em>{source.page_or_section}</em>}
            {(claimByEvidence.get(source.evidence_id) ?? []).length > 0 && (
              <p>
                Supports: {cleanModelMarkdown(
                  (claimByEvidence.get(source.evidence_id) ?? []).slice(0, 1)[0]
                )}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function CriticPanel({ critic }: { critic: ChatCriticReview }) {
  return (
    <details
      className={`critic-panel ${critic.status}`}
      aria-label="Evidence validation details"
      open={critic.status !== "passed"}
    >
      <summary>
        <strong>Evidence validation</strong>
        <span>{formatEvidenceCheckStatus(critic.status)}</span>
      </summary>
      <p className="field-note">
        Argus compares the answer with the exact passage retrieved for it. A warning means
        the wording could not be matched strongly enough, so do not rely on that conclusion
        without refining the question or source. This check still cannot prove that the
        source itself is true or that an investment conclusion is suitable for you.
      </p>
      {critic.findings.length > 0 ? (
        <ul>
          {critic.findings.map((finding) => (
            <li key={`${finding.code}-${finding.message}`}>
              <strong>{finding.severity}</strong>
              <span>{finding.message}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>No citation issues detected by the local critic.</p>
      )}
    </details>
  );
}

function PortfolioWorkspace({
  displayMode,
  portfolioFile,
  portfolioAsOfDate,
  portfolioState,
  robinhoodSyncState,
  robinhoodEnabled,
  robinhoodSidecarConfigured,
  targetAllocation,
  rebalanceThreshold,
  summary,
  marketMap,
  marketAnalysis,
  marketAnalysisModel,
  marketAnalysisState,
  alertSettings,
  marketAlerts,
  alertState,
  etfSelectionEngine,
  modelOptions,
  onGenerateMarketAnalysis,
  onMarketAnalysisModelChange,
  onRefreshMarketMap,
  onPortfolioFileChange,
  onPortfolioAsOfDateChange,
  onOpenMoneyPlanning,
  onEditProfile,
  onUpload,
  onSyncRobinhood,
  onEvaluateAlerts,
  onSaveAlertSettings,
  onAlertFeedback
}: {
  displayMode: "invest" | "planning";
  portfolioFile: File | null;
  portfolioAsOfDate: string;
  portfolioState: RequestState;
  robinhoodSyncState: RequestState;
  robinhoodEnabled: boolean;
  robinhoodSidecarConfigured: boolean;
  targetAllocation: Record<string, number>;
  rebalanceThreshold: number | null;
  summary: PortfolioSummaryResponse | null;
  marketMap: MarketMapResponse | null;
  marketAnalysis: MarketAnalysisResponse | null;
  marketAnalysisModel: string;
  marketAnalysisState: RequestState;
  alertSettings: AlertSettings | null;
  marketAlerts: MarketAlertPreview[];
  alertState: RequestState;
  etfSelectionEngine: EtfSelectionEngine | null;
  modelOptions: ChatModelOption[];
  onGenerateMarketAnalysis: () => void;
  onMarketAnalysisModelChange: (value: string) => void;
  onRefreshMarketMap: () => void;
  onPortfolioFileChange: (value: File | null) => void;
  onPortfolioAsOfDateChange: (value: string) => void;
  onOpenMoneyPlanning: () => void;
  onEditProfile?: () => void;
  onUpload: () => void;
  onSyncRobinhood: () => void;
  onEvaluateAlerts: () => void;
  onSaveAlertSettings: (value: AlertSettings) => void;
  onAlertFeedback: (
    alertId: number,
    feedback: "useful" | "noise" | "too_late" | "incorrect"
  ) => void;
}) {
  const uploading = portfolioState.status === "loading";
  const syncingRobinhood = robinhoodSyncState.status === "loading";
  const analyzingMarket = marketAnalysisState.status === "loading";
  const usesModelCandidateSelection = etfSelectionEngine === "model";
  const marketModels = modelOptions.filter((option) => option.supports_market_search);
  const recommendedSectorSymbols = new Set(
    marketAnalysis?.watchlist.map((item) => item.symbol) ?? []
  );
  const directlyHeldSymbols = new Set(
    summary?.positions.map((position) => position.symbol.trim().toUpperCase()) ?? []
  );
  const recommendationModeBySymbol = new Map(
    marketAnalysis?.watchlist.map((item) => [item.symbol.trim().toUpperCase(), item.recommendation_mode])
      ?? []
  );
  const marketTileGroups = marketMap
    ? Array.from(new Set(marketMap.tiles.map((tile) => tile.group))).map((group) => ({
        group,
        tiles: marketMap.tiles
          .filter((tile) => tile.group === group)
          .sort((left, right) => left.symbol.localeCompare(right.symbol))
      }))
    : [];
  const [selectedMarketSymbol, setSelectedMarketSymbol] = useState<string | null>(null);
  const [activePortfolioTab, setActivePortfolioTab] =
    useState<"overview" | "alerts" | "settings">("overview");
  const selectedMarketTile = marketMap?.tiles.find(
    (tile) => tile.symbol === selectedMarketSymbol
  ) ?? null;
  const selectedRecommendationMode = selectedMarketTile
    ? recommendationModeBySymbol.get(selectedMarketTile.symbol.toUpperCase()) ?? null
    : null;

  useEffect(() => {
    if (!selectedMarketTile) {
      return undefined;
    }
    const priorOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedMarketSymbol(null);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = priorOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [selectedMarketTile]);

  return (
    <div className={`research-workspace portfolio-workspace ${displayMode}-mode`}>
      {displayMode === "invest" && (
        <nav className="portfolio-tabs" aria-label="Investment suggestions views">
          {(["overview", "alerts", "settings"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              className={activePortfolioTab === tab ? "active" : ""}
              aria-current={activePortfolioTab === tab ? "page" : undefined}
              onClick={() => setActivePortfolioTab(tab)}
            >
              {tab[0].toUpperCase() + tab.slice(1)}
              {tab === "alerts" && marketAlerts.length > 0 && <span>{marketAlerts.length}</span>}
            </button>
          ))}
        </nav>
      )}
      {displayMode === "invest" && activePortfolioTab === "alerts" && (
        <MarketAlertsPanel
          alerts={marketAlerts}
          state={alertState}
          enabled={alertSettings?.enabled ?? true}
          onEvaluate={onEvaluateAlerts}
          onFeedback={onAlertFeedback}
        />
      )}
      {displayMode === "invest" && activePortfolioTab === "settings" && (
        <MarketAlertSettingsPanel
          settings={alertSettings}
          state={alertState}
          onSave={onSaveAlertSettings}
        />
      )}
      <div hidden={displayMode === "invest" && activePortfolioTab !== "overview"}>
      {displayMode === "planning" && (
        <section className="portfolio-block planning-detail money-planning-intro" aria-label="Money planning overview">
          <div>
            <span className="eyebrow">Goals before trades · 先规划，再投资</span>
            <h2>Cash management and retirement planning · 现金管理与养老规划</h2>
            <p className="section-note">
              Short-term cash goals protect money needed within 1–120 months. The
              retirement model separately estimates the long-term balance and starting
              monthly deposit required. Both use saved Profile inputs; neither places trades.
            </p>
          </div>
          <button type="button" className="secondary-action" onClick={onEditProfile}>
            <UserRound aria-hidden="true" />
            <span>Edit planning inputs in Profile</span>
          </button>
        </section>
      )}
      {displayMode === "planning" && !summary && (
        <section className="portfolio-block planning-detail" aria-label="Money planning inputs needed">
          <p className="empty-state">
            Save the planning inputs in Profile to generate short-term cash and
            retirement schedules. Portfolio holdings are used only when they are
            relevant to retirement savings already accumulated.
          </p>
        </section>
      )}
      {displayMode === "invest" && robinhoodEnabled && (
        <section className="portfolio-source-toolbar" aria-label="Robinhood portfolio source">
          <div>
            <span className="eyebrow">Optional live source · 可选实时来源</span>
            <strong>Robinhood Investments</strong>
            <small>
              Manual, read-only refresh. Argus cannot place, modify, review, or cancel orders.
            </small>
          </div>
          <button
            type="button"
            className="secondary-action"
            disabled={syncingRobinhood || !robinhoodSidecarConfigured}
            onClick={onSyncRobinhood}
          >
            {syncingRobinhood ? <Loader2 className="spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
            <span>{syncingRobinhood ? "Refreshing" : "Refresh positions"}</span>
          </button>
          {!robinhoodSidecarConfigured && (
            <p>Robinhood is enabled, but the local read-only Sidecar is not configured.</p>
          )}
          <RequestStatus state={robinhoodSyncState} />
        </section>
      )}
      <form
        className="input-stack portfolio-import-form"
        onSubmit={(event) => {
          event.preventDefault();
          onUpload();
        }}
      >
        <div className="portfolio-import-row">
          <label className="snapshot-date-field" htmlFor="holdings-as-of-date">
            Holdings as-of date
            <input
              id="holdings-as-of-date"
              type="date"
              required
              value={portfolioAsOfDate}
              onChange={(event) => onPortfolioAsOfDateChange(event.target.value)}
            />
          </label>
          <div className="holdings-file-field">
            <label htmlFor="holdings-file">Portfolio holdings file</label>
            <div className="input-action-row">
              <input
                id="holdings-file"
                type="file"
                accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                onChange={(event) => onPortfolioFileChange(event.target.files?.[0] ?? null)}
              />
              <button type="submit" disabled={uploading}>
                {uploading ? <Loader2 className="spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
                <span>Import</span>
              </button>
            </div>
          </div>
        </div>
        <p className="field-note">
          CSV, XLSX, or XLS up to 10 MB. The first worksheet must contain symbol, name,
          asset_class, quantity, price, market_value, cost_basis, and account columns.
          An optional as_of_date column must match the date above. Use local mode for
          sensitive holdings.
          {portfolioFile ? ` Selected: ${portfolioFile.name}` : ""}
        </p>
        <RequestStatus state={portfolioState} />
      </form>

      {displayMode === "invest" && (marketMap || summary) && (
        <section className="market-intelligence" aria-label="Market intelligence">
          <div className="market-intelligence-header">
            <div>
              <span className="eyebrow">Market intelligence · 行情与市场分析</span>
              <h2>
                {marketMap?.unified_universe_enabled
                  ? "Evidence-backed market context"
                  : "Current prices and evidence-backed context"}
              </h2>
            </div>
            <p>
              {marketMap?.unified_universe_enabled
                ? "Current quotes and volume now appear in ETF Universe below. Optional AI analysis explains broader context from separately retrieved, cited evidence."
                : "Quotes provide the current numbers. Optional AI analysis explains the broader market context from separately retrieved, cited evidence."}
            </p>
          </div>
      {marketMap && !marketMap.unified_universe_enabled && (
        <section className="market-data-status" aria-label="Market data status">
          <div>
            <span className="eyebrow">1 · Market data · 行情数据</span>
            <strong>{marketMap.configured_provider_name}</strong>
          </div>
          <div className="market-data-actions">
            <span className={`status-chip ${marketMap.is_live ? "feasible" : "neutral"}`}>
              {marketMap.is_live ? (marketMap.is_delayed ? "Delayed" : "Live") : "Not live"}
            </span>
            <button
              className="icon-button"
              type="button"
              onClick={onRefreshMarketMap}
              title="Refresh quotes and, when enabled, the historical-volume cache"
              aria-label="Refresh market data"
            >
              <RefreshCw aria-hidden="true" />
            </button>
          </div>
          <p>{marketMap.message}</p>
          <small>
            {marketMap.tiles.filter((tile) => tile.latest_price !== null).length}
            {` of ${marketMap.tiles.length} controlled ETF quotes available`}
          </small>
        </section>
      )}

      {marketMap?.heatmap_enabled && !marketMap.unified_universe_enabled && (
        <section className="market-heatmap" aria-label="ETF market heatmap">
          <div className="market-heatmap-heading">
            <div>
              <h3>ETF HeatmapMatrix · 行业行情矩阵</h3>
              <p>
                Fixed-size tiles prevent trading volume from looking like recommendation
                strength. Red/green shows the latest regular-session price versus the prior
                completed regular-session close (1D, not weekly or yearly). Volume activity
                uses a separate color label; badges show holdings and the evidence-backed role.
              </p>
            </div>
            <span className="status-chip neutral">{marketMap.tiles.length} ETFs</span>
          </div>
          <div className="market-heatmap-legend" aria-label="Heatmap status legend">
            <span>● HELD ETF · 直接持有</span>
            <span>◆ RELATED n · 持有相关股票</span>
            <span>＋ NEW · 新增敞口候选</span>
            <span>⇄ REPLACE · 分散替代候选</span>
            <span>◎ REVIEW · 现有 ETF 复核</span>
          </div>
          <div className="market-heatmap-groups">
            {marketTileGroups.map(({ group, tiles }) => (
              <section className="market-heatmap-group" key={group}>
                <h4>{group}</h4>
                <div className="market-heatmap-grid">
                  {tiles.map((tile) => {
                    const recommendationMode = recommendationModeBySymbol.get(
                      tile.symbol.toUpperCase()
                    );
                    return (
                      <button
                        className={`market-heatmap-tile ${marketChangeClass(tile.percent_change)} ${volumeActivityClass(tile.volume_z_score)}`}
                        key={tile.symbol}
                        type="button"
                        aria-pressed={selectedMarketSymbol === tile.symbol}
                        aria-haspopup="dialog"
                        aria-label={`Open ${tile.symbol} market details`}
                        onClick={() => setSelectedMarketSymbol((current) => (
                          current === tile.symbol ? null : tile.symbol
                        ))}
                      >
                        <span className="heatmap-badge-row">
                          <span>
                            {tile.directly_held && <em>● HELD ETF</em>}
                            {tile.related_holdings.length > 0 && (
                              <em>◆ RELATED {tile.related_holdings.length}</em>
                            )}
                          </span>
                          {recommendationMode && (
                            <em>{recommendationModeBadge(recommendationMode)}</em>
                          )}
                        </span>
                        <span className="heatmap-quote-row">
                          <strong>{tile.symbol}</strong>
                          <strong>{formatMarketMove(tile.percent_change)}</strong>
                        </span>
                        <span className="heatmap-tile-name">{tile.name}</span>
                        <span className="heatmap-tile-metrics">
                          <span>{tile.latest_price === null ? "No quote" : formatCurrencyPrecise(tile.latest_price)}</span>
                          <span className={`volume-activity-label ${volumeActivityLabelClass(tile.volume_activity)}`}>
                            Volume: {tile.volume_activity}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
          {selectedMarketTile && (
            <div
              className="market-heatmap-modal-backdrop"
              role="presentation"
              onMouseDown={(event) => {
                if (event.currentTarget === event.target) {
                  setSelectedMarketSymbol(null);
                }
              }}
            >
            <article
              className="market-heatmap-detail market-heatmap-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="market-heatmap-dialog-title"
            >
              <div className="market-heatmap-detail-heading">
                <div>
                  <span className="eyebrow">Selected ETF · 详情</span>
                  <h4 id="market-heatmap-dialog-title">{selectedMarketTile.symbol} · {selectedMarketTile.name}</h4>
                </div>
                <button
                  className="secondary-action"
                  type="button"
                  autoFocus
                  onClick={() => setSelectedMarketSymbol(null)}
                >
                  Close details
                </button>
              </div>
              <div className="heatmap-detail-badges">
                {selectedMarketTile.directly_held && <span>● HELD ETF · 直接持有</span>}
                {selectedMarketTile.related_holdings.length > 0 && (
                  <span>◆ RELATED {selectedMarketTile.related_holdings.length} · 持有相关股票</span>
                )}
                {selectedRecommendationMode && (
                  <span>{recommendationModeBadge(selectedRecommendationMode)}</span>
                )}
              </div>
              {selectedMarketTile.related_holdings.length > 0 && (
                <details open>
                  <summary>Related stock holdings · 展开相关股票</summary>
                  <p>{selectedMarketTile.related_holdings.join(", ")}</p>
                </details>
              )}
              <div className="market-heatmap-detail-grid">
                <div><span>Latest regular-session price</span><strong>{selectedMarketTile.latest_price === null ? "Unavailable" : formatCurrencyPrecise(selectedMarketTile.latest_price)}</strong></div>
                <div><span>1D move vs prior close</span><strong>{formatMarketMove(selectedMarketTile.percent_change)}</strong></div>
                <div>
                  <span>Prior completed close</span>
                  <strong>
                    {selectedMarketTile.previous_close === null
                      ? "Unavailable"
                      : `${formatCurrencyPrecise(selectedMarketTile.previous_close)}${selectedMarketTile.previous_close_date ? ` · ${selectedMarketTile.previous_close_date}` : ""}`}
                  </strong>
                </div>
                <div><span>Dollar volume</span><strong>{selectedMarketTile.dollar_volume === null ? "Unavailable" : formatCurrencyShort(selectedMarketTile.dollar_volume)}</strong></div>
                <div><span>Quote observed</span><strong>{selectedMarketTile.quote_observed_at ? formatTimestamp(selectedMarketTile.quote_observed_at) : "Unavailable"}</strong></div>
              </div>
              <VolumeActivityExplanation tile={selectedMarketTile} />
            </article>
            </div>
          )}
        </section>
      )}

      {summary && (
        <section className="market-analysis-panel" aria-label="AI market analysis">
          <div className="answer-header">
            <div>
              <h2>AI market analysis · current market context</h2>
              <p className="field-note">
                Optional external analysis. Argus sends up to 12 symbols, asset classes,
                portfolio weights, and the holdings date—not account names or dollar values.
                It runs two bounded independent searches: portfolio drivers, then sector leadership
                and independent counter-evidence. The second search excludes domains returned
                by the first when possible. If only one domain passes the Evidence Gate,
                Argus shows a limitation instead of silently presenting it as comprehensive.
              </p>
            </div>
            <button
              className="action-button"
              type="button"
              disabled={analyzingMarket || !marketAnalysisModel}
              onClick={onGenerateMarketAnalysis}
            >
              {analyzingMarket
                ? <Loader2 className="spin" aria-hidden="true" />
                : <FileSearch aria-hidden="true" />}
              <span>Generate analysis</span>
            </button>
          </div>
          <label className="model-field" htmlFor="market-analysis-model">
            {etfSelectionEngine === null
              ? "Answer model · loading backend role"
              : usesModelCandidateSelection
                ? "Answer model · synthesis and ETF candidate selection"
                : "Answer model · explanation only"}
            <select
              id="market-analysis-model"
              value={marketAnalysisModel}
              onChange={(event) => onMarketAnalysisModelChange(event.target.value)}
            >
              <option value="">Select a configured model</option>
              {marketModels.map((option) => (
                <option key={option.id} value={option.id} disabled={!option.available}>
                  {option.label}{option.available ? "" : " · unavailable"}
                </option>
              ))}
            </select>
          </label>
          <p className="market-model-explanation">
            {etfSelectionEngine === null
              ? "Argus is loading the active backend ETF-selection mode before describing the model boundary."
              : usesModelCandidateSelection
                ? "Independent web search returns direct-URL evidence before Argus applies the Evidence Gate. In model-candidate mode, the answer model you select synthesizes the analysis and ranks up to three ETFs from the controlled universe. The backend still validates allowed symbols, citations, holdings status, candidate limits, and safety rules. The model cannot invoke its own web search or trigger a silent fallback. One same-model citation repair is allowed; a second failure is rejected."
                : "Independent web search returns direct-URL evidence before Argus applies the Evidence Gate. The backend fixes ETF eligibility and rank; the answer model you select only explains that result. It cannot invoke its own web search, change the ETF list, or trigger a silent fallback. One same-model citation repair is allowed; a second failure is rejected."}
          </p>
          <RequestStatus state={marketAnalysisState} />
          {marketAnalysis && (
            <div className="allocation-guidance-result">
              <p className="guidance-method-note">
                Generated {formatTimestamp(marketAnalysis.generated_at)} · {marketAnalysis.source_method}
                {` · ${marketAnalysis.style_pack_name} · ${formatCost(marketAnalysis.estimated_cost_usd)} total`}
                {marketAnalysis.method_document_names.length > 0
                  ? ` · expert panel: ${marketAnalysis.method_document_names.join(" + ")}`
                  : ""}
              </p>
              <p className="section-note">
                Search: {marketAnalysis.search_calls} call(s), {formatCost(marketAnalysis.search_estimated_cost_usd)}
                {` · ${marketAnalysis.model}: ${marketAnalysis.answer_model_calls} answer call(s), ${formatCost(marketAnalysis.answer_model_estimated_cost_usd)}`}
                {` · Search returned ${marketAnalysis.retrieved_result_count} unique result(s) across ${marketAnalysis.retrieved_domain_count} domain(s)`}
                {` · Argus accepted ${marketAnalysis.source_count} source(s) across ${marketAnalysis.domain_count} domain(s)`}
              </p>
              <p className="market-audit-summary">
                <strong>Audit Run #{marketAnalysis.run_id}</strong>
                <span>
                  {marketAnalysis.selection_engine === "deterministic"
                    ? "Fixed deterministic ranking"
                    : "Legacy model-candidate rollback mode"}
                  {` · ${marketAnalysis.selection_version}`}
                  {` · independent audit ${marketAnalysis.audit_status}`}
                  {` · Evidence snapshot ${marketAnalysis.evidence_snapshot_id || "not available"}`}
                  {` · ${marketAnalysis.candidate_parse_status.split("_").join(" ")}`}
                  {` · ${marketAnalysis.candidate_audit.filter((item) => item.accepted).length} candidate(s) accepted`}
                  {` · ${marketAnalysis.candidate_audit.filter((item) => !item.accepted).length} not selected`}
                  {" · open Runs to inspect structured rejection codes"}
                </span>
              </p>
              {marketAnalysis.limitations.length > 0 && (
                <div className="guidance-warnings market-analysis-limitations">
                  <strong>Argus Evidence Gate warning · not an Exa result limit</strong>
                  <ul>
                    {marketAnalysis.limitations.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                  <p>
                    {marketAnalysis.gate_rejected_result_count} retrieved result(s) were
                    excluded because their passages did not directly support the requested
                    portfolio or sector claim. The analysis still used Profile, holdings,
                    deterministic rebalance gaps, and the accepted web evidence.
                  </p>
                </div>
              )}
              <ResearchAnswer value={marketAnalysis.content} />
              <div className="guidance-references">
                <strong>Web sources and retrieval timestamps</strong>
                <ul>
                  {marketAnalysis.sources.map((source) => (
                    <li key={source.url}>
                      <a href={source.url} target="_blank" rel="noreferrer">
                        [{source.citation_id}] {source.title}
                      </a>
                      <span>Retrieved {formatTimestamp(source.retrieved_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <p className="section-note">
                AI-generated, source-backed context—not personalized advice. Verify dates,
                original sources, current quotes, taxes, and suitability before acting.
              </p>
            </div>
          )}
        </section>
      )}
        </section>
      )}

      {summary && <PortfolioCharts summary={summary} targetAllocation={targetAllocation} />}

      <section className="portfolio-block" aria-label="Portfolio summary">
        <h2>Summary</h2>
        <div className="portfolio-grid">
          <div className="metric-card">
            <span>Total value</span>
            <strong>{formatCurrency(summary?.total_value ?? 0)}</strong>
          </div>
          <div className="metric-card">
            <span>Holdings date</span>
            <strong>{summary?.as_of_date ?? "Not set"}</strong>
          </div>
          <div className="metric-card">
            <span>Positions</span>
            <strong>{summary?.positions.length ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Flags</span>
            <strong>{summary?.concentration_flags.length ?? 0}</strong>
          </div>
        </div>
      </section>

      {summary && (
        <>
          <section className="portfolio-block" aria-label="Asset allocation">
            <h2>Allocation</h2>
            <ul className="allocation-list">
              {summary.allocation.map((item) => (
                <li key={item.asset_class}>
                  <span>{item.asset_class}</span>
                  <strong>{formatPercent(item.weight)}</strong>
                  <em>{formatCurrency(item.market_value)}</em>
                </li>
              ))}
            </ul>
          </section>

          <section className="portfolio-block" aria-label="Positions">
            <h2>Positions</h2>
            <div className="table-wrap">
              <table className="positions-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Asset</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>Value</th>
                    <th>Weight</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.positions.map((position) => (
                    <tr key={`${position.symbol}-${position.account ?? ""}`}>
                      <td>
                        <strong>{position.symbol}</strong>
                        <span>{position.name}</span>
                      </td>
                      <td>{position.asset_class}</td>
                      <td>{formatShares(position.quantity)}</td>
                      <td>{formatCurrencyPrecise(position.price)}</td>
                      <td>{formatCurrency(position.market_value)}</td>
                      <td>{formatPercent(position.weight)}</td>
                      <td>
                        <span className={`source-chip ${position.source_key}`}>
                          {position.source_key === "robinhood_mcp" ? "Robinhood" : "File"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="portfolio-block" aria-label="Rebalance suggestions">
            <h2>Rebalance suggestions</h2>
            <div className="recommendation-context">
              {summary.recommendation_context.price_source === "position_snapshot_with_live_candidate_quotes" ? (
                <>
                  <strong>Using saved holdings + current read-only candidate quotes</strong>
                  <span>
                    Existing positions use the latest saved holdings snapshot dated
                    {` ${summary.as_of_date ?? "unknown"}`}. Approved funds that are not yet held
                    use current quotes from the configured read-only market-data provider. Refresh
                    Market view and confirm the quote before trading.
                  </span>
                </>
              ) : summary.recommendation_context.price_source === "robinhood_mcp_snapshot" ? (
                <>
                  <strong>Using a Robinhood-synced price snapshot · not streaming</strong>
                  <span>
                    Amounts and share estimates use prices captured during the latest read-only
                    Robinhood position sync dated {summary.as_of_date ?? "unknown"}. Refresh
                    Robinhood before relying on them, and confirm the current quote before trading.
                  </span>
                </>
              ) : summary.recommendation_context.price_source === "mixed_position_snapshots" ? (
                <>
                  <strong>Using mixed-source price snapshots · not streaming</strong>
                  <span>
                    Amounts and share estimates use the active saved position snapshots dated
                    {` ${summary.as_of_date ?? "unknown"}`}. Refresh each connected source or upload
                    before relying on them, and confirm the current quote before trading.
                  </span>
                </>
              ) : (
                <>
                  <strong>Using an uploaded price snapshot · not live</strong>
                  <span>
                    Amounts and share estimates use prices stored in the active holdings file dated
                    {` ${summary.as_of_date ?? "unknown"}`}. Upload a newer file before relying on
                    them, and confirm the current quote before trading.
                  </span>
                </>
              )}
              {summary.recommendation_context.status === "target_allocation_required" && (
                <span>
                  The 20% line is an example review level, not your personal target.
                  Save a target allocation in Profile for policy-based BUY and SELL amounts.
                </span>
              )}
              <span>{summary.recommendation_context.analysis_method_description}</span>
              <span>{summary.recommendation_context.policy}</span>
            </div>
            <div className="rebalance-scenario-grid" aria-label="Rebalancing scenario comparison">
              {summary.rebalance_scenarios.map((scenario) => (
                <article
                  className={`rebalance-scenario-card scenario-${scenario.code}`}
                  key={scenario.code}
                >
                  <div className="scenario-card-heading">
                    <div>
                      <span className="scenario-kind">
                        {scenario.code === "maintain"
                          ? "Reference only"
                          : scenario.code === "new_contributions"
                            ? "Contribution option"
                            : "Trade option"}
                      </span>
                      <strong>{scenario.title}</strong>
                      <span>{scenario.description}</span>
                    </div>
                    <div>
                      <span>Rebalancing amount</span>
                      <strong>{formatCurrencyPrecise(scenario.rebalancing_amount)}</strong>
                    </div>
                  </div>
                  <div className="scenario-projection-heading">
                    <strong>Projected allocation</strong>
                    <span>Total: {formatCurrencyPrecise(scenario.projected_total_value)}</span>
                  </div>
                  <ul className="scenario-allocation-list">
                    {scenario.projected_allocation.map((allocation) => (
                      <li key={allocation.asset_class}>
                        <span>{allocation.asset_class}</span>
                        <strong>{formatPercent(allocation.weight)}</strong>
                        <em>{formatCurrencyPrecise(allocation.market_value)}</em>
                      </li>
                    ))}
                  </ul>
                  <div className="scenario-detail-block">
                    <strong>Amounts and estimated shares</strong>
                    {scenario.trades.length > 0 ? (
                      <ul className="scenario-trade-list">
                        {scenario.trades.map((trade, index) => (
                          <li key={`${trade.action}-${trade.symbol ?? trade.asset_class}-${index}`}>
                            <strong>{trade.action}</strong>
                            <span>{trade.symbol ?? trade.asset_class}</span>
                            <span>{formatCurrencyPrecise(trade.amount)}</span>
                            <span>{shareInstruction(trade)}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span>No trade · 0 shares</span>
                    )}
                  </div>
                  <div className="scenario-detail-block">
                    <strong>Known limitations</strong>
                    <ul className="scenario-limit-list">
                      {scenario.limitations.map((limitation) => (
                        <li key={limitation}>{limitation}</li>
                      ))}
                    </ul>
                  </div>
                </article>
              ))}
            </div>
            {summary.rebalance_actions.length > 0 ? (
              <div className="table-wrap">
                <table className="positions-table recommendation-table">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Asset</th>
                      <th>Rebalancing amount</th>
                      <th>Estimated shares</th>
                      <th>Current → reference</th>
                      <th>Why this appears / checks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.rebalance_actions.map((action, index) => (
                      <tr key={`${action.action}-${action.symbol ?? action.asset_class}-${index}`}>
                        <td>
                          <strong className={`trade-action ${action.action.toLowerCase()}`}>
                            {action.action === "REVIEW" && action.reference_kind === "policy_target"
                              ? "ROUNDING"
                              : action.action}
                          </strong>
                        </td>
                        <td>
                          {action.asset_url ? (
                            <a
                              className="asset-name-link"
                              href={action.asset_url}
                              target="_blank"
                              rel="noreferrer"
                              title={`Open ${action.asset_source ?? "official asset source"}`}
                            >
                              <strong>{action.symbol ?? action.asset_class}</strong>
                              <span>{action.name ?? action.asset_class}</span>
                            </a>
                          ) : (
                            <>
                              <strong>{action.symbol ?? action.asset_class}</strong>
                              <span>{action.name ?? action.asset_class}</span>
                            </>
                          )}
                        </td>
                        <td>{formatCurrencyPrecise(action.amount)}</td>
                        <td>
                          {shareInstruction(action)}
                          {action.reference_price !== null && (
                            <span>
                              @ {formatCurrencyPrecise(action.reference_price)} · {action.price_as_of_date}
                            </span>
                          )}
                        </td>
                        <td>
                          {formatPercent(action.current_weight)} → {formatPercent(action.target_weight)}
                          <span>{action.reference_label}</span>
                        </td>
                        <td>
                          <div className="decision-rationale">
                            <strong>Policy signal</strong>
                            <span>{action.rationale}</span>
                            <strong>Portfolio role</strong>
                            <span>{action.asset_description}</span>
                            {action.warnings.length > 0 && (
                              <details>
                                <summary>Checks before acting ({action.warnings.length})</summary>
                                <ul>
                                  {action.warnings.map((warning) => (
                                    <li key={warning}>{warning}</li>
                                  ))}
                                </ul>
                              </details>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <ul className="scenario-list">
                {summary.scenarios.map((scenario) => (
                  <li key={scenario.scenario}>
                    <strong>{scenario.scenario}</strong>
                    <span>{scenario.rationale}</span>
                  </li>
                ))}
              </ul>
            )}
            {marketAnalysis && (
              <div className="market-watchlist-panel" aria-label="Source-backed ETF configuration candidates">
                <div className="section-heading-row">
                  <div>
                    <h3>Additional ETF configuration candidates · 证据支持的额外配置候选</h3>
                    <p className="section-note">
                      These appear only when current accepted evidence, Profile context, and
                      the uploaded holdings jointly support further research. The count means
                      “candidates that passed / maximum shown.” Argus does not fill unused slots
                      when the evidence cannot support another fund.
                    </p>
                  </div>
                  <span className="status-chip neutral">
                    {marketAnalysis.watchlist.length} evidence-backed candidate(s) · max 3
                  </span>
                </div>
                {marketAnalysis.watchlist.length > 0 ? (
                  <div className="market-watchlist-grid">
                    {marketAnalysis.watchlist.map((item) => {
                      const candidate = summary.sector_candidates.find(
                        (value) => value.symbol === item.symbol
                      );
                      const policyAction = summary.rebalance_actions.find(
                        (action) => action.symbol?.trim().toUpperCase() === item.symbol.trim().toUpperCase()
                      );
                      const executablePolicyAction = policyAction && policyAction.action !== "REVIEW";
                      return (
                        <article key={item.symbol}>
                            <div>
                              <a
                                href={candidate?.source_url}
                                target="_blank"
                                rel="noreferrer"
                                title={candidate?.source_link_note}
                              >
                                {item.symbol} · {item.name}
                              </a>
                              <span>
                                {candidate?.issuer || item.category.replace("_", " ")}
                                {candidate?.source_link_kind === "issuer_directory"
                                  ? ` · official ETF directory; search ${item.symbol}`
                                  : " · verified official fund profile"}
                                {candidate?.source_checked_at
                                  ? ` · checked ${candidate.source_checked_at}`
                                  : ""}
                              </span>
                              <em className={`watchlist-mode ${item.recommendation_mode}`}>
                                {item.recommendation_mode === "diversifying_replacement"
                                  ? "ETF replacement candidate · not an additive purchase"
                                  : item.recommendation_mode === "existing_holding_review"
                                    ? "Existing ETF holding review · not a new purchase"
                                    : "New-exposure ETF research candidate"}
                              </em>
                            </div>
                          {item.recommendation_mode === "existing_holding_review" && (
                            <div className={`existing-etf-decision ${executablePolicyAction ? "action-calculated" : "monitor-only"}`}>
                              <strong>
                                {executablePolicyAction
                                  ? "Position adjustment calculated by the deterministic Rebalance policy"
                                  : policyAction
                                    ? "Rebalance review only · no executable position change calculated"
                                  : "Monitor only · no position change calculated"}
                              </strong>
                              {executablePolicyAction && policyAction ? (
                                <span>
                                  Rebalance currently shows {policyAction.action.toUpperCase()} {formatCurrencyPrecise(policyAction.amount)}
                                  {policyAction.estimated_shares !== null
                                    ? ` (${formatShares(policyAction.estimated_shares)} shares)`
                                    : ". A share count is unavailable; review the Rebalance warnings for the missing quote or execution constraint"}
                                  {`. This result comes from saved target drift—not from the market model. ${policyAction.rationale}`}
                                </span>
                              ) : policyAction ? (
                                <span>
                                  {policyAction.rationale} This is not a hidden or unfinished sell
                                  calculation. Review the Rebalance row for its reference line and
                                  constraints; no executable BUY or SELL is currently proposed.
                                </span>
                              ) : (
                                <span>
                                  This review does not mean Argus wants a trade. Monitor the market thesis,
                                  counter-evidence, invalidation signal, overlap, and future policy drift below.
                                  A dollar/share change appears only if Rebalance independently calculates one.
                                </span>
                              )}
                            </div>
                          )}
                          <dl>
                            <div><dt>Thesis to review</dt><dd>{item.rationale}</dd></div>
                            <div><dt>Evidence against the thesis</dt><dd>{item.counter_evidence}</dd></div>
                            <div><dt>Change / exit trigger to monitor</dt><dd>{item.invalidation_signal}</dd></div>
                            <div><dt>Portfolio overlap to review</dt><dd>{item.overlap_risk}</dd></div>
                            <div>
                              <dt>DCA</dt>
                              <dd>
                                {item.dca_guidance}
                                {item.dca_suitable
                                  ? item.dca_monthly_amount > 0
                                    ? ` Profile budget: ${formatCurrency(item.dca_monthly_amount)} / month.`
                                    : " Suitable only as a bounded satellite; set an optional sector ETF budget in Profile to assign dollars."
                                  : " No recurring allocation is proposed."}
                              </dd>
                            </div>
                          </dl>
                          <small>Citations: {item.citation_ids.join(", ")}</small>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="empty-state">Generate market analysis to evaluate the controlled ETF universe, or no candidate passed the evidence and portfolio-fit checks.</p>
                )}
              </div>
            )}
            <p className="section-note">{summary.recommendation_context.disclaimer}</p>
          </section>

          {(summary.coverage_gaps.length > 0 || recommendedSectorSymbols.size > 0) && (
            <section className="portfolio-block" aria-label="Diversification gaps">
              <h2>Diversification and missing exposure</h2>
              {summary.coverage_gaps.length > 0 && <ul className="coverage-list">
                {summary.coverage_gaps.map((gap) => (
                  <li key={gap.asset_class}>
                    <div>
                      <strong>{gap.asset_class}</strong>
                      <span>{gap.rationale}</span>
                      {gap.gap_amount !== null && (
                        <em>Target gap: {formatCurrencyPrecise(gap.gap_amount)}</em>
                      )}
                    </div>
                    {gap.candidates.length > 0 && (
                      <div className="candidate-list">
                        {gap.candidates.map((candidate) => (
                          <a
                            key={candidate.symbol}
                            href={candidate.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <strong>{candidate.symbol}</strong>
                            <span>{candidate.portfolio_role}</span>
                            <em>{candidate.satellite ? "Satellite" : "Core candidate"}</em>
                          </a>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>}
              {marketAnalysis && marketAnalysis.watchlist.length > 0 && (
                <div className="evidence-backed-exposure">
                  <div>
                    <strong>Current evidence-backed sector / industry candidates</strong>
                    <span>
                      These are bounded satellite research candidates, not proof that the
                      portfolio lacks a core asset class and not automatic BUY instructions.
                    </span>
                  </div>
                  <div className="candidate-list">
                    {marketAnalysis.watchlist.map((item) => {
                      const candidate = summary.sector_candidates.find((value) => value.symbol === item.symbol);
                      return (
                        <a key={item.symbol} href={candidate?.source_url} target="_blank" rel="noreferrer">
                          <strong>{item.symbol}</strong>
                          <span>{item.name}</span>
                          <em>
                            {item.recommendation_mode === "diversifying_replacement"
                              ? "ETF replacement research; related stocks already held"
                              : item.recommendation_mode === "existing_holding_review"
                                ? "Existing ETF holding review"
                                : "New-exposure ETF research candidate"}
                          </em>
                        </a>
                      );
                    })}
                  </div>
                </div>
              )}
              {!marketAnalysis && (
                <div className="evidence-backed-exposure pending-research">
                  <div>
                    <strong>Sector / industry recommendation not generated yet</strong>
                    <span>
                      Use Generate analysis above. Exa must first collect current evidence;
                      then the selected model ranks 1–3 controlled ETFs against this Profile
                      and the uploaded holdings. A dollar budget is not required to display them.
                    </span>
                  </div>
                </div>
              )}
              {marketAnalysis && marketAnalysis.watchlist.length === 0 && (
                <div className="evidence-backed-exposure pending-research">
                  <div>
                    <strong>No sector / industry candidate passed this analysis</strong>
                    <span>
                      The controlled fund library below is not itself a recommendation.
                      Retry with fresher evidence only when useful; Argus does not invent a
                      candidate merely to fill this section.
                    </span>
                  </div>
                </div>
              )}
            </section>
          )}

          {marketMap?.unified_universe_enabled ? (
            <UnifiedEtfUniverse
              marketMap={marketMap}
              summary={summary}
              marketAnalysis={marketAnalysis}
              onRefreshMarketMap={onRefreshMarketMap}
            />
          ) : (
          <section className="portfolio-block sector-research-library" aria-label="Sector and industry ETF research candidates">
            <div className="section-heading-row">
              <div>
                <h2>Sector and industry ETF research candidates</h2>
                <p className="section-note">
                  Controlled multi-issuer peer library: State Street and Vanguard funds cover
                  all 11 broad GICS sectors; State Street industry funds and iShares SOXX add
                  narrower comparisons. Each fund name opens a verified official profile when
                  available; otherwise it opens the issuer’s official ETF directory and tells
                  you which ticker to search.
                  This is not every U.S. ETF, so “recommended” means the best evidence-supported
                  fit among these controlled peers—not a guaranteed market-wide top performer.
                </p>
              </div>
              <span className="status-chip neutral">{summary.sector_candidates.length} candidates</span>
            </div>
            <div className="sector-candidate-legend" aria-label="ETF candidate color legend">
              <span className="held"><i aria-hidden="true" />Exact ETF held · 已直接持有该 ETF</span>
              <span className="related"><i aria-hidden="true" />Related stocks held · 持有相关股票，并非持有该 ETF</span>
              <span className="recommended"><i aria-hidden="true" />New-exposure ETF candidate · 新增配置研究候选</span>
              <span className="related-replacement"><i aria-hidden="true" />ETF replacement candidate · 用 ETF 分散替代相关股票</span>
              <span className="both"><i aria-hidden="true" />Existing ETF review · 已持有 ETF 的保留/调整复核</span>
              <small>
                Related-stock status never means Argus recommends those stocks. It means the
                ETF overlaps a mapped stock already in the upload. If that ETF passes the
                evidence gate, it is shown only as a possible diversified replacement—not an
                additional purchase on top of the stock. Broad-index look-through is not inferred.
              </small>
            </div>
            {(["sector_research", "industry_research"] as const).map((category) => (
              <div className="candidate-universe-group" key={category}>
                <h3>{category === "sector_research" ? "Broad-sector ETF peers · 11 sectors" : "Industry ETF peers"}</h3>
                <div className="sector-candidate-grid">
                  {summary.sector_candidates.filter((candidate) => candidate.candidate_category === category).map((candidate) => {
                    const recommended = recommendedSectorSymbols.has(candidate.symbol);
                    const held = directlyHeldSymbols.has(candidate.symbol.toUpperCase());
                    const related = candidate.related_holdings.length > 0;
                    const stateClass = held && recommended
                      ? "held-and-recommended-candidate"
                      : related && recommended
                        ? "related-and-recommended-candidate"
                      : recommended
                        ? "current-research-candidate"
                        : held
                          ? "held-sector-candidate"
                          : related
                            ? "related-stock-candidate"
                            : "";
                    return (
                      <article className={`sector-candidate-card ${stateClass}`} key={candidate.symbol}>
                        <a
                          href={candidate.source_url}
                          target="_blank"
                          rel="noreferrer"
                          title={candidate.source_link_note}
                        >
                          <strong>{candidate.symbol}</strong>
                          <span>{candidate.portfolio_role.replace(/ (sector|industry) research satellite$/, "")}</span>
                        </a>
                        <small>{candidate.issuer}</small>
                        {(held || recommended || related) && (
                          <em>
                            {held && recommended
                              ? "Existing ETF holding review"
                              : related && recommended
                                ? "ETF replacement candidate · related stocks held"
                              : held
                                ? "Exact ETF held"
                                : recommended
                                  ? "New-exposure ETF candidate"
                                  : "Related stocks held · ETF not held"}
                          </em>
                        )}
                        <small className="candidate-link-note">
                          {candidate.source_link_kind === "issuer_directory"
                            ? `Official ETF directory · search ${candidate.symbol}`
                            : "Verified official fund profile"}
                          {candidate.source_checked_at
                            ? ` · checked ${candidate.source_checked_at}`
                            : ""}
                        </small>
                        {related && (
                          <details>
                            <summary>Stocks mapped to this exposure ({candidate.related_holdings.length})</summary>
                            <span>{candidate.related_holdings.join(", ")}</span>
                          </details>
                        )}
                      </article>
                    );
                  })}
                </div>
              </div>
            ))}
            <p className="section-note">
              A watchlist recommendation must include a current bull case, counter-evidence,
              an invalidation signal, and overlap/concentration risk. It cannot reliably
              predict a rally before it starts and does not place trades.
            </p>
          </section>
          )}

          {displayMode === "invest" && (
            <PortfolioPlanningSummary
              cashPlan={summary.cash_plan}
              retirementPlan={summary.retirement_plan}
              onOpen={onOpenMoneyPlanning}
            />
          )}

          <section className="portfolio-block planning-detail" aria-label="Cash goal plan">
            <div className="section-heading-row">
              <div>
                <h2>Short-term cash goal plan · 短期现金目标储蓄计划</h2>
                <p className="section-note">Emergency reserves and dated expenses; retirement investing is calculated separately below.</p>
              </div>
              <span className={`status-chip ${summary.cash_plan.feasibility_status}`}>
                {formatCashPlanStatus(summary.cash_plan.feasibility_status)}
              </span>
            </div>
            <div className="plain-language-purpose cash-purpose">
              <strong>What this section answers · 这个区域解决什么问题？</strong>
              <span>
                Can the cash you already entered cover known bills due within the next
                1–120 months? If not, how much additional cash must be saved each month
                before each deadline? It does not estimate retirement and does not tell
                you to invest this money.
              </span>
            </div>
            {summary.cash_plan.goals.length > 0 ? (
              <>
                {summary.cash_plan.primary_financial_priority && (
                  <div className="cash-priority-banner">
                    <strong>Priority to protect</strong>
                    <span>{summary.cash_plan.primary_financial_priority}</span>
                    <small>
                      When the monthly plan is tight, Argus preserves this outcome before
                      reducing lower-priority goals. See the trade-off steps below.
                    </small>
                  </div>
                )}
                <div className="compact-metric-grid">
                  <div className="metric-card">
                    <span>Current cash entered</span>
                    <strong>{formatCurrencyPrecise(summary.cash_plan.current_cash_savings)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Total of enabled goals</span>
                    <strong>{formatCurrencyPrecise(summary.cash_plan.total_target)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Still needs saving</span>
                    <strong>{formatCurrencyPrecise(summary.cash_plan.remaining_gap)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Minimum new saving</span>
                    <strong>{formatCurrency(summary.cash_plan.monthly_required)} / mo</strong>
                  </div>
                </div>
                <div className="cash-goal-plan-list">
                  {summary.cash_plan.goals.map((goal) => {
                    const progress = goal.target_amount > 0
                      ? Math.min(100, (goal.allocated_current_savings / goal.target_amount) * 100)
                      : 0;
                    return (
                      <article className={`cash-goal-plan-card ${goal.funding_status}`} key={goal.code}>
                        <div className="cash-goal-plan-heading">
                          <div><strong>{goal.title}</strong><span>{goal.priority} priority · {goal.deadline_label}</span></div>
                          <span className={`status-chip ${goal.funding_status === "funded" ? "feasible" : "warning"}`}>
                            {goal.funding_status === "funded" ? "Covered by entered cash" : goal.funding_status === "partially_funded" ? "Partly covered" : "Not covered"}
                          </span>
                        </div>
                        <div className="cash-goal-progress" aria-label={`${progress.toFixed(0)} percent funded`}>
                          <span style={{ width: `${progress}%` }} />
                        </div>
                        <div className="cash-goal-plan-numbers">
                          <span>Target <strong>{formatCurrencyPrecise(goal.target_amount)}</strong></span>
                          <span>Entered cash assigned <strong>{formatCurrencyPrecise(goal.allocated_current_savings)}</strong></span>
                          <span>Remaining <strong>{formatCurrencyPrecise(goal.remaining_gap)}</strong></span>
                          <span>{goal.monthly_required > 0 ? "Save each month" : "Additional saving"} <strong>{goal.monthly_required > 0 ? `${formatCurrency(goal.monthly_required)} / mo` : "$0 · already covered"}</strong></span>
                        </div>
                        <p>{goal.rationale}</p>
                      </article>
                    );
                  })}
                </div>
                <div className={`cash-capacity-summary ${summary.cash_plan.feasibility_status}`}>
                  <strong>Monthly feasibility check</strong>
                  <span>
                    Capacity after entered spending and planned investing: {formatOptionalCurrency(summary.cash_plan.monthly_capacity_for_cash_goals)}.
                    {summary.cash_plan.remaining_gap <= 0
                      ? " Because current cash already covers every enabled goal, $0 monthly saving is expected—not missing data."
                      : summary.cash_plan.feasibility_status === "shortfall"
                        ? ` The plan is short by ${formatOptionalCurrency(summary.cash_plan.monthly_shortfall)} per month.`
                        : " This covers the minimum monthly savings schedule."}
                  </span>
                </div>
              </>
            ) : (
              <p className="empty-state">Add a cash goal in Profile to calculate a schedule.</p>
            )}
            {(summary.cash_plan.warnings.length > 0 || summary.cash_plan.guidance.length > 0) && (
              <details className="explanation-details" open={summary.cash_plan.feasibility_status === "shortfall"}>
                <summary>How this plan and priority trade-offs are calculated</summary>
                <p>
                  Argus applies the cash savings entered in Profile to enabled goals in
                  priority order, then calculates the monthly amount needed by each deadline.
                  Investment holdings are excluded, and cash goals do not change the saved
                  investment-allocation percentages.
                </p>
                {summary.cash_plan.warnings.length > 0 && (
                  <div className="plan-explanation-group">
                    <strong>Missing or incomplete inputs</strong>
                    <ul>
                      {[...new Set(summary.cash_plan.warnings)].map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {summary.cash_plan.guidance.length > 0 && (
                  <div className="plan-explanation-group">
                    <strong>Next steps</strong>
                    <ol>
                      {[...new Set(summary.cash_plan.guidance)].map((item) => <li key={item}>{item}</li>)}
                    </ol>
                  </div>
                )}
              </details>
            )}
          </section>

          <section className="portfolio-block retirement-funding-plan planning-detail" aria-label="Retirement funding plan">
            <div className="section-heading-row">
              <div>
                <h2>Retirement funding plan · 退休资金倒推</h2>
                <p className="section-note">
                  FINRA-inspired accumulation plus withdrawal model. It estimates the
                  first-year monthly deposit needed now and assumes a $0 ending balance
                  at age {summary.retirement_plan.plan_through_age}.
                </p>
              </div>
              <span className={`status-chip ${summary.retirement_plan.status === "on_track" || summary.retirement_plan.status === "already_funded" || summary.retirement_plan.status === "income_covers_spending" ? "feasible" : summary.retirement_plan.status === "funding_gap" ? "warning" : "neutral"}`}>
                {summary.retirement_plan.status === "on_track" ? "On modeled track"
                  : summary.retirement_plan.status === "already_funded" ? "Current assets modeled sufficient"
                  : summary.retirement_plan.status === "income_covers_spending" ? "Income covers target"
                  : summary.retirement_plan.status === "funding_gap" ? "Monthly gap"
                  : "Inputs needed"}
              </span>
            </div>
            <div className="plain-language-purpose retirement-purpose">
              <strong>What this section answers · 这个区域解决什么问题？</strong>
              <span>
                After subtracting Social Security, pension, or other reliable income,
                how much must your retirement account fund each month? How large must the
                account be when retirement starts, and what starting monthly deposit is
                required between now and then?
              </span>
            </div>
            {summary.retirement_plan.retirement_tax_rate === null
              && ((summary.retirement_plan.income_taxable
                && summary.retirement_plan.monthly_reliable_income_today > 0)
                || (summary.retirement_plan.taxable_withdrawal_share ?? 0) > 0) && (
              <div className="tax-excluded-baseline" role="note">
                <strong>Tax not included · 未计税基线</strong>
                <span>
                  No retirement tax rate was entered. The amounts below use 0% tax;
                  taxable income and Traditional-account withdrawals would require a
                  higher gross balance and monthly saving amount.
                </span>
              </div>
            )}
            {summary.retirement_plan.status === "inputs_required" ? (
              <div className="retirement-inputs-needed">
                <strong>Complete these Profile inputs</strong>
                <ul>{summary.retirement_plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </div>
            ) : (
              <>
                <div className="retirement-flow-summary">
                  <div><span>After-tax spending wanted</span><strong>{formatOptionalCurrency(summary.retirement_plan.monthly_spending_today)} / mo</strong></div>
                  <b>−</b>
                  <div><span>Reliable income after tax</span><strong>{formatOptionalCurrency(summary.retirement_plan.monthly_reliable_income_after_tax)} / mo</strong></div>
                  <b>=</b>
                  <div><span>After-tax portfolio gap</span><strong>{formatOptionalCurrency(summary.retirement_plan.monthly_spending_gap)} / mo</strong></div>
                </div>
                <div className="compact-metric-grid retirement-metrics">
                  <div className="metric-card"><span>Retirement savings counted now</span><strong>{formatCurrencyPrecise(summary.retirement_plan.current_retirement_savings)}</strong><small>{summary.retirement_plan.current_savings_source === "profile_input" ? "Profile amount" : "Uploaded investments used"}</small></div>
                  <div className="metric-card"><span>Required balance at retirement</span><strong>{formatOptionalCurrency(summary.retirement_plan.target_assets_at_retirement)}</strong><small>Future nominal dollars</small></div>
                  <div className="metric-card"><span>Current savings projected to retirement</span><strong>{formatOptionalCurrency(summary.retirement_plan.projected_current_assets_at_retirement)}</strong></div>
                  <div className="metric-card emphasis"><span>Required starting deposit now</span><strong>{formatOptionalCurrency(summary.retirement_plan.required_monthly_investment)} / mo</strong><small>{summary.retirement_plan.adjust_contributions_for_inflation ? "Then increases with inflation yearly" : "Held level in nominal dollars"}</small></div>
                  {summary.retirement_plan.estimated_monthly_take_home_cost !== null && summary.retirement_plan.estimated_monthly_take_home_cost !== summary.retirement_plan.required_monthly_investment && <div className="metric-card"><span>Estimated take-home cash cost</span><strong>{formatCurrency(summary.retirement_plan.estimated_monthly_take_home_cost)} / mo</strong><small>Simplified current-tax estimate for a deductible pre-tax deposit</small></div>}
                  <div className="metric-card"><span>Current planned investment</span><strong>{formatCurrency(summary.retirement_plan.planned_monthly_investment)} / mo</strong></div>
                </div>
                {summary.retirement_plan.monthly_investment_gap !== null && summary.retirement_plan.monthly_investment_gap > 0 && (
                  <div className="retirement-gap-callout">
                    <strong>Modeled monthly shortfall: {formatCurrency(summary.retirement_plan.monthly_investment_gap)}</strong>
                    <span>{summary.retirement_plan.guidance.join(" ")}</span>
                  </div>
                )}
              </>
            )}
            {summary.retirement_plan.status !== "inputs_required" && <details className="explanation-details">
              <summary>Show the calculation with my numbers · 展开计算公式</summary>
              <ol className="retirement-formula-steps">
                <li><strong>After-tax income:</strong> {formatCurrency(summary.retirement_plan.monthly_reliable_income_today)} × {summary.retirement_plan.income_taxable ? `(1 − ${formatPercent(summary.retirement_plan.retirement_tax_rate ?? 0)})` : "not taxable"} = {formatOptionalCurrency(summary.retirement_plan.monthly_reliable_income_after_tax)} / month.</li>
                <li><strong>After-tax spending gap:</strong> {formatOptionalCurrency(summary.retirement_plan.monthly_spending_today)} − {formatOptionalCurrency(summary.retirement_plan.monthly_reliable_income_after_tax)} = {formatOptionalCurrency(summary.retirement_plan.monthly_spending_gap)} / month.</li>
                <li><strong>Gross account withdrawal:</strong> {formatOptionalCurrency(summary.retirement_plan.monthly_spending_gap)} ÷ simplified {retirementAccountLabel(summary.retirement_plan.account_type)} tax treatment{summary.retirement_plan.taxable_withdrawal_share !== null ? ` (${formatPercent(summary.retirement_plan.taxable_withdrawal_share)} treated as pre-tax withdrawals)` : ""} = {formatOptionalCurrency(summary.retirement_plan.gross_monthly_portfolio_withdrawal)} / month.</li>
                <li><strong>Real return:</strong> (1 + {formatPercent(summary.retirement_plan.annual_return)}) ÷ (1 + {formatPercent(summary.retirement_plan.inflation_rate)}) − 1 = {formatPercent(summary.retirement_plan.real_annual_return)}.</li>
                <li><strong>Balance needed:</strong> present value of {summary.retirement_plan.retirement_years} years of withdrawals = {formatOptionalCurrency(summary.retirement_plan.target_assets_at_retirement_today_dollars)} in today's dollars, or {formatOptionalCurrency(summary.retirement_plan.target_assets_at_retirement)} at retirement after inflation.</li>
                <li><strong>Current savings growth:</strong> {formatCurrencyPrecise(summary.retirement_plan.current_retirement_savings)} grown for {summary.retirement_plan.years_to_retirement} years at {formatPercent(summary.retirement_plan.annual_return)} = {formatOptionalCurrency(summary.retirement_plan.projected_current_assets_at_retirement)}.</li>
                <li><strong>Monthly deposit:</strong> the remaining retirement balance is divided by the future-value factor for {summary.retirement_plan.years_to_retirement} years = {formatOptionalCurrency(summary.retirement_plan.required_monthly_investment)} starting per month.</li>
              </ol>
              <ul>
                <li>Primary account: {retirementAccountLabel(summary.retirement_plan.account_type)}. Ending-balance target: {formatCurrency(summary.retirement_plan.ending_balance_target)} at age {summary.retirement_plan.plan_through_age}.</li>
                <li>{summary.retirement_plan.adjust_contributions_for_inflation ? "Deposits increase annually with inflation." : "Deposits remain level; they are not automatically increased for inflation."}</li>
                <li>Taxes are simplified. Social Security taxation, account-specific contribution order, capital-gains basis, required distributions, fees, health-care shocks, and sequence risk need a fuller plan.</li>
                <li>This deterministic estimate is not a return forecast, guarantee, or personalized tax advice.</li>
              </ul>
              {summary.retirement_plan.warnings.length > 0 && <ul className="recommendation-warning-list">{summary.retirement_plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
            </details>}
          </section>

          <section className="portfolio-block" aria-label="Recurring investment plan">
            <div className="section-heading-row">
              <div>
                <h2>DCA plan · 定期定额投资 / 定投计划</h2>
                <p className="section-note">Monthly new money directed to underweight targets.</p>
              </div>
              <span className="status-chip neutral">Investments only</span>
            </div>
            {summary.dca_suggestions.length > 0 ? (
              <div className="table-wrap">
                <table className="positions-table compact-plan-table">
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Monthly amount</th>
                      <th>Estimated shares</th>
                      <th>Purpose</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.dca_suggestions.map((suggestion) => (
                      <tr key={`${suggestion.asset_class}-${suggestion.symbol ?? "cash"}`}>
                        <td>
                          {suggestion.asset_url ? (
                            <a className="asset-name-link" href={suggestion.asset_url}
                              target="_blank" rel="noreferrer"
                              title={`Open ${suggestion.asset_source ?? "official asset source"}`}>
                              <strong>{suggestion.symbol ?? suggestion.asset_class}</strong>
                              <span>{suggestion.name ?? suggestion.asset_class}</span>
                            </a>
                          ) : <strong>{suggestion.symbol ?? suggestion.asset_class}</strong>}
                        </td>
                        <td><strong>{formatCurrency(suggestion.monthly_amount)}</strong></td>
                        <td>{shareInstruction(suggestion)}</td>
                        <td>{suggestion.rationale}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-state">Set a monthly contribution and target allocation in Profile.</p>
            )}
            {summary.dca_suggestions.length > 0 && (
              <details className="explanation-details">
                <summary>How to read this plan</summary>
                <p>
                  Dollar amounts are rounded to whole dollars. Cash goals are calculated
                  separately. A 0% target excludes an asset class. Confirm current quotes
                  before converting dollars to shares.
                </p>
                {summary.dca_suggestions.flatMap((suggestion) => suggestion.warnings).map((warning, index) => (
                  <span className="recommendation-warning" key={`${warning}-${index}`}>{warning}</span>
                ))}
              </details>
            )}
            {marketAnalysis && marketAnalysis.watchlist.some((item) => item.dca_suitable) && (
              <div className="sector-dca-panel">
                <div>
                  <strong>Optional sector / industry satellite DCA</strong>
                  <span>
                    Uses only the capped Profile budget and only candidates that passed
                    current evidence, counter-evidence, invalidation, overlap, and DCA checks.
                  </span>
                </div>
                <ul>
                  {marketAnalysis.watchlist.filter((item) => item.dca_suitable).map((item) => (
                    <li key={item.symbol}>
                      <strong>{item.symbol}</strong>
                      <span>{item.dca_monthly_amount > 0 ? `${formatCurrency(item.dca_monthly_amount)} / month` : "No dollar budget set"}</span>
                      <small>{item.dca_guidance}</small>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {summary.concentration_flags.length > 0 && (
            <section className="portfolio-block" aria-label="Concentration review">
              <div className="section-heading-row">
                <div>
                  <h2>Concentration review · 集中度检查</h2>
                  <p className="section-note">
                    Single holding ≥25% · asset-class total ≥70% · cash excluded. These
                    rule-based screens are separate from your rebalance drift threshold.
                  </p>
                </div>
                <span className="status-chip warning">
                  {summary.concentration_flags.length} concentration
                  {` ${summary.concentration_flags.length === 1 ? "flag" : "flags"}`}
                </span>
              </div>
              <ul className="risk-flag-list">
                {summary.concentration_flags.map((flag) => (
                  <li key={`${flag.code}-${flag.symbol ?? flag.asset_class ?? ""}`}>
                    <div className="risk-flag-identity">
                      <span className="risk-severity">Review</span>
                      <strong>{flag.symbol ?? flag.asset_class ?? "Portfolio"}</strong>
                      <small>{riskScopeLabel(flag.code)}</small>
                    </div>
                    <span className="risk-metric">
                      <small>Invested weight · 投资占比</small>
                      <strong>{flag.weight === null ? "—" : formatPercent(flag.weight)}</strong>
                    </span>
                    <span className="risk-metric">
                      <small>Review threshold · 检查阈值</small>
                      <strong>{flag.threshold === null ? "—" : `≥ ${formatPercent(flag.threshold)}`}</strong>
                    </span>
                    <span className="risk-metric risk-excess">
                      <small>Excess · 超出幅度</small>
                      <strong>
                        {flag.excess_percentage_points === null
                          ? "—"
                          : `+${flag.excess_percentage_points.toFixed(1)} pp`}
                      </strong>
                    </span>
                    <em>Review portfolio impact</em>
                  </li>
                ))}
              </ul>
              <details className="explanation-details">
                <summary>Why this flag appears · 为什么触发</summary>
                <p>
                  The 25% single-holding and 70% asset-class thresholds are built-in Argus
                  screening defaults—not personalized targets or regulatory limits.
                  Weight equals the holding or asset-class value divided by all invested
                  holdings; cash is excluded from this concentration denominator.
                  Rebalance drift is different: it compares each current asset-class weight
                  with its saved Profile target and uses your
                  {rebalanceThreshold === null
                    ? " Profile drift setting"
                    : ` ${formatPercent(rebalanceThreshold)} drift setting`}.
                  Both are review prompts, not automatic trades. Neither rule uses AI.
                </p>
              </details>
            </section>
          )}
        </>
      )}
      </div>
    </div>
  );
}

function MarketAlertsPanel({
  alerts,
  state,
  enabled,
  onEvaluate,
  onFeedback
}: {
  alerts: MarketAlertPreview[];
  state: RequestState;
  enabled: boolean;
  onEvaluate: () => void;
  onFeedback: (
    alertId: number,
    feedback: "useful" | "noise" | "too_late" | "incorrect"
  ) => void;
}) {
  return (
    <section className="portfolio-block alert-preview-panel" aria-label="Market review previews">
      <div className="answer-header">
        <div>
          <span className="eyebrow">Preview only · 不推送</span>
          <h2>Market review alerts · 市场复核提醒</h2>
          <p className="section-note">
            Deterministic review prompts from Robinhood holdings and completed regular-session
            OHLCV. Fundamental-event validation and Telegram delivery are not enabled in v1.
          </p>
        </div>
        <button
          type="button"
          className="action-button"
          disabled={!enabled || state.status === "loading"}
          onClick={onEvaluate}
        >
          {state.status === "loading"
            ? <Loader2 className="spin" aria-hidden="true" />
            : <RefreshCw aria-hidden="true" />}
          <span>Run preview</span>
        </button>
      </div>
      <RequestStatus state={state} />
      {!enabled ? (
        <p className="empty-state">Market review previews are paused in Settings.</p>
      ) : alerts.length === 0 ? (
        <p className="empty-state">
          No saved previews yet. Refresh Robinhood positions, then run a preview.
          No alert is also a valid result when the configured conditions are not met.
        </p>
      ) : (
        <div className="alert-preview-list">
          {alerts.map((alert) => (
            <article className={`alert-preview-card ${alert.direction}`} key={alert.id}>
              <header>
                <div>
                  <span className={`status-chip ${alert.direction === "buy" ? "feasible" : "warning"}`}>
                    {alert.direction === "buy" ? "BUY REVIEW" : "REDUCE REVIEW"}
                  </span>
                  <h3>{alert.symbol}</h3>
                </div>
                <div className="alert-preview-score">
                  <span>Policy v{alert.policy_version}</span>
                  <strong>Score {alert.score}</strong>
                </div>
              </header>
              <div className="alert-context-grid">
                <div><span>Current position</span><strong>{alert.holding_quantity.toLocaleString()} shares</strong></div>
                <div><span>Portfolio weight</span><strong>{formatPercent(alert.portfolio_weight)}</strong></div>
                <div><span>Completed close</span><strong>{formatCurrencyPrecise(alert.latest_close)}</strong></div>
                <div><span>Market / holdings dates</span><strong>{alert.market_as_of_date} / {alert.holdings_as_of_date}</strong></div>
              </div>
              <div className="alert-evidence-grid">
                <section>
                  <h4>Why this appeared</h4>
                  <ul>{alert.reasons.map((item) => <li key={item}>{item}</li>)}</ul>
                </section>
                <section>
                  <h4>Counter-evidence</h4>
                  <ul>{alert.counter_evidence.map((item) => <li key={item}>{item}</li>)}</ul>
                </section>
                <section>
                  <h4>Invalidate / suppress if</h4>
                  <ul>{alert.invalidation_conditions.map((item) => <li key={item}>{item}</li>)}</ul>
                </section>
              </div>
              <div className="guidance-warnings">
                {alert.warnings.map((item) => <span key={item}>{item}</span>)}
              </div>
              <footer className="alert-feedback">
                <span>Was this preview useful?</span>
                {(["useful", "noise", "too_late", "incorrect"] as const).map((value) => (
                  <button
                    type="button"
                    className={alert.feedback === value ? "active" : ""}
                    key={value}
                    onClick={() => onFeedback(alert.id, value)}
                  >
                    {value.split("_").join(" ")}
                  </button>
                ))}
              </footer>
              {alert.feedback_action && <p className="feedback-action">{alert.feedback_action}</p>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MarketAlertSettingsPanel({
  settings,
  state,
  onSave
}: {
  settings: AlertSettings | null;
  state: RequestState;
  onSave: (value: AlertSettings) => void;
}) {
  const [draft, setDraft] = useState<AlertSettings | null>(settings);
  useEffect(() => setDraft(settings), [settings]);
  if (!draft) {
    return <section className="portfolio-block"><p className="empty-state">Loading alert settings…</p></section>;
  }
  return (
    <section className="portfolio-block alert-settings-panel" aria-label="Market alert settings">
      <div>
        <span className="eyebrow">Simple mode · Policy v{draft.policy_version}</span>
        <h2>Market review settings · 提醒设置</h2>
        <p className="section-note">
          Safe defaults manage freshness, deduplication and a 24-hour cooldown. Saving a
          material change creates a new policy version; historical previews do not change.
        </p>
      </div>
      <div className="alert-setting-row">
        <div><strong>市场复核提醒</strong><small>Pause evaluation without deleting history.</small></div>
        <button
          type="button"
          className={`toggle-button ${draft.enabled ? "active" : ""}`}
          aria-pressed={draft.enabled}
          onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
        >
          {draft.enabled ? "开启" : "关闭"}
        </button>
      </div>
      <fieldset>
        <legend>发送方式</legend>
        <label><input type="radio" checked readOnly /> 仅在 Argus 预览</label>
        <label className="disabled-option"><input type="radio" disabled /> Telegram（Preview 验证后开放）</label>
      </fieldset>
      <fieldset>
        <legend>提醒范围</legend>
        <label><input type="radio" checked readOnly /> 我的持仓</label>
        <label className="disabled-option"><input type="radio" disabled /> 持仓 + 观察列表（稍后开放）</label>
      </fieldset>
      <label className="alert-sensitivity">
        <span>提醒灵敏度</span>
        <select
          value={draft.sensitivity}
          onChange={(event) => setDraft({
            ...draft,
            sensitivity: event.target.value as AlertSettings["sensitivity"]
          })}
        >
          <option value="conservative">少 · 保守</option>
          <option value="standard">标准 · 推荐</option>
          <option value="active">多 · 积极</option>
        </select>
      </label>
      <div className="quiet-hours">
        <span>免打扰</span>
        <input
          type="time"
          value={draft.quiet_hours_start}
          onChange={(event) => setDraft({ ...draft, quiet_hours_start: event.target.value })}
        />
        <span>–</span>
        <input
          type="time"
          value={draft.quiet_hours_end}
          onChange={(event) => setDraft({ ...draft, quiet_hours_end: event.target.value })}
        />
        <small>Saved now; applied when Telegram delivery is implemented.</small>
      </div>
      <button
        type="button"
        className="action-button"
        disabled={state.status === "loading"}
        onClick={() => onSave(draft)}
      >
        <ShieldCheck aria-hidden="true" />
        <span>保存设置</span>
      </button>
      <RequestStatus state={state} />
    </section>
  );
}

type EtfUniverseItem = {
  candidate: InvestmentCandidate;
  market: MarketMapTile | null;
  recommendation: MarketAnalysisResponse["watchlist"][number] | null;
};

function UnifiedEtfUniverse({
  marketMap,
  summary,
  marketAnalysis,
  onRefreshMarketMap
}: {
  marketMap: MarketMapResponse;
  summary: PortfolioSummaryResponse;
  marketAnalysis: MarketAnalysisResponse | null;
  onRefreshMarketMap: () => void;
}) {
  const [view, setView] = useState<"market" | "research">(
    marketMap.heatmap_enabled ? "market" : "research"
  );
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const marketBySymbol = new Map(
    marketMap.tiles.map((tile) => [tile.symbol.trim().toUpperCase(), tile])
  );
  const recommendationBySymbol = new Map(
    marketAnalysis?.watchlist.map((item) => [item.symbol.trim().toUpperCase(), item]) ?? []
  );
  const directlyHeldSymbols = new Set(
    summary.positions.map((position) => position.symbol.trim().toUpperCase())
  );
  const availableQuoteCount = marketMap.tiles.filter(
    (tile) => tile.latest_price !== null
  ).length;
  const universeItems: EtfUniverseItem[] = summary.sector_candidates.map((candidate) => {
    const symbol = candidate.symbol.trim().toUpperCase();
    return {
      candidate,
      market: marketBySymbol.get(symbol) ?? null,
      recommendation: recommendationBySymbol.get(symbol) ?? null
    };
  });
  const selectedItem = universeItems.find(
    (item) => item.candidate.symbol.toUpperCase() === selectedSymbol
  ) ?? null;
  const marketGroups = Array.from(
    new Set(universeItems.map((item) => item.market?.group ?? "Other"))
  ).map((group) => ({
    group,
    items: universeItems.filter((item) => (item.market?.group ?? "Other") === group)
  }));

  useEffect(() => {
    if (marketMap.heatmap_enabled || view !== "market") {
      return;
    }
    setView("research");
  }, [marketMap.heatmap_enabled, view]);

  useEffect(() => {
    if (!selectedItem) {
      return undefined;
    }
    const priorOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedSymbol(null);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = priorOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [selectedItem]);

  return (
    <section className="portfolio-block etf-universe" aria-label="ETF Universe">
      <div className="etf-universe-heading">
        <div>
          <span className="eyebrow">ETF Universe · ETF 行情与研究库</span>
          <h2>One fund universe, two views</h2>
          <p className="section-note">
            Market view shows observable price and volume data. Research view shows fund
            identity, portfolio overlap, and current research status. A rising price is not
            automatically a recommendation, and a candidate badge is not a trade instruction.
          </p>
        </div>
        <span className="status-chip neutral">{universeItems.length} ETFs</span>
      </div>
      <div className="etf-universe-tabs" role="tablist" aria-label="ETF Universe view">
        <button
          type="button"
          role="tab"
          aria-selected={view === "market"}
          disabled={!marketMap.heatmap_enabled}
          onClick={() => setView("market")}
        >
          Market view · 行情
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "research"}
          onClick={() => setView("research")}
        >
          Research view · 研究
        </button>
      </div>

      {view === "market" ? (
        <div className="market-heatmap unified-market-view" role="tabpanel">
          <div className="market-view-source" aria-label="ETF market data status">
            <div>
              <strong>{marketMap.configured_provider_name}</strong>
              <span>
                {availableQuoteCount} of {universeItems.length} ETF quotes available
              </span>
            </div>
            <div>
              <span className={`status-chip ${marketMap.is_live ? "feasible" : "neutral"}`}>
                {marketMap.is_live ? (marketMap.is_delayed ? "Delayed" : "Live") : "Not live"}
              </span>
              <button
                className="icon-button"
                type="button"
                onClick={onRefreshMarketMap}
                title="Refresh quotes and, when enabled, the historical-volume cache"
                aria-label="Refresh ETF market data"
              >
                <RefreshCw aria-hidden="true" />
              </button>
            </div>
          </div>
          <div className="market-heatmap-heading">
            <p>
              Red/green is the latest regular-session price versus the prior completed close
              (1D). Volume activity is direction-neutral. Neutral badges separately show what
              you hold and what the current evidence-backed analysis asks you to research.
            </p>
          </div>
          {availableQuoteCount === 0 && (
            <p className="market-data-inline-warning">{marketMap.message}</p>
          )}
          <div className="market-heatmap-legend" aria-label="Heatmap status legend">
            <span>● HELD ETF · 直接持有</span>
            <span>◆ RELATED n · 持有相关股票</span>
            <span>＋ NEW · 新增敞口候选</span>
            <span>⇄ REPLACE · 分散替代候选</span>
            <span>◎ REVIEW · 现有 ETF 复核</span>
          </div>
          <div className="market-heatmap-groups">
            {marketGroups.map(({ group, items }) => (
              <section className="market-heatmap-group" key={group}>
                <h4>{group}</h4>
                <div className="market-heatmap-grid">
                  {items.map(({ candidate, market, recommendation }) => (
                    <button
                      className={`market-heatmap-tile ${marketChangeClass(market?.percent_change ?? null)} ${volumeActivityClass(market?.volume_z_score ?? null)}`}
                      key={candidate.symbol}
                      type="button"
                      aria-haspopup="dialog"
                      aria-label={`Open ${candidate.symbol} ETF details`}
                      onClick={() => setSelectedSymbol(candidate.symbol.toUpperCase())}
                    >
                      <span className="heatmap-badge-row">
                        <span>
                          {(market?.directly_held || directlyHeldSymbols.has(candidate.symbol.toUpperCase())) && <em>● HELD ETF</em>}
                          {candidate.related_holdings.length > 0 && (
                            <em>◆ RELATED {candidate.related_holdings.length}</em>
                          )}
                        </span>
                        {recommendation && (
                          <em>{recommendationModeBadge(recommendation.recommendation_mode)}</em>
                        )}
                      </span>
                      <span className="heatmap-quote-row">
                        <strong>{candidate.symbol}</strong>
                        <strong>{formatMarketMove(market?.percent_change ?? null)}</strong>
                      </span>
                      <span className="heatmap-tile-name">{candidate.name}</span>
                      <span className="heatmap-tile-metrics">
                        <span>{market?.latest_price == null ? "No quote" : formatCurrencyPrecise(market.latest_price)}</span>
                        <span className={`volume-activity-label ${volumeActivityLabelClass(market?.volume_activity ?? "Unavailable")}`}>
                          Volume: {market?.volume_activity ?? "Unavailable"}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      ) : (
        <div className="unified-research-view" role="tabpanel">
          <p className="research-view-source-note">
            Research view comes from the Argus controlled fund library, active holdings
            mappings, and accepted evidence-backed analysis—not from Robinhood market data.
          </p>
          <div className="sector-candidate-legend" aria-label="ETF research status legend">
            <span className="held"><i aria-hidden="true" />Exact ETF held · 已直接持有</span>
            <span className="related"><i aria-hidden="true" />Related stocks held · 持有相关股票</span>
            <span className="recommended"><i aria-hidden="true" />New exposure · 新增敞口研究</span>
            <span className="related-replacement"><i aria-hidden="true" />Replacement · 分散替代研究</span>
            <span className="both"><i aria-hidden="true" />Review · 现有 ETF 复核</span>
            <small>
              These colors describe holdings overlap and research role. They do not describe
              today’s price direction and do not authorize a transaction.
            </small>
          </div>
          {(["sector_research", "industry_research"] as const).map((category) => (
            <div className="candidate-universe-group" key={category}>
              <h3>{category === "sector_research" ? "Broad-sector ETF peers · 11 sectors" : "Industry ETF peers"}</h3>
              <div className="sector-candidate-grid">
                {universeItems.filter((item) => item.candidate.candidate_category === category).map(({ candidate, market, recommendation }) => {
                  const held = market?.directly_held || directlyHeldSymbols.has(candidate.symbol.toUpperCase());
                  const related = candidate.related_holdings.length > 0;
                  const recommended = recommendation !== null;
                  const stateClass = held && recommended
                    ? "held-and-recommended-candidate"
                    : related && recommended
                      ? "related-and-recommended-candidate"
                      : recommended
                        ? "current-research-candidate"
                        : held
                          ? "held-sector-candidate"
                          : related
                            ? "related-stock-candidate"
                            : "";
                  return (
                    <button
                      className={`sector-candidate-card universe-research-card ${stateClass}`}
                      key={candidate.symbol}
                      type="button"
                      aria-haspopup="dialog"
                      onClick={() => setSelectedSymbol(candidate.symbol.toUpperCase())}
                    >
                      <span className="research-card-title">
                        <strong>{candidate.symbol}</strong>
                        <span>{candidate.portfolio_role.replace(/ (sector|industry) research satellite$/, "")}</span>
                      </span>
                      <small>{candidate.issuer}</small>
                      {(held || recommended || related) && (
                        <em>
                          {held && recommended
                            ? "Existing ETF review"
                            : recommendation?.recommendation_mode === "diversifying_replacement"
                              ? "ETF replacement candidate"
                              : recommendation?.recommendation_mode === "new_exposure"
                                ? "New-exposure candidate"
                                : held
                                  ? "Exact ETF held"
                                  : "Related stocks held · ETF not held"}
                        </em>
                      )}
                      <small className="candidate-link-note">Open combined market and research details</small>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedItem && (
        <EtfUniverseModal item={selectedItem} onClose={() => setSelectedSymbol(null)} />
      )}
    </section>
  );
}

function EtfUniverseModal({
  item,
  onClose
}: {
  item: EtfUniverseItem;
  onClose: () => void;
}) {
  const { candidate, market, recommendation } = item;
  const held = market?.directly_held ?? false;
  return (
    <div
      className="market-heatmap-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) {
          onClose();
        }
      }}
    >
      <article
        className="market-heatmap-detail market-heatmap-modal etf-universe-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="etf-universe-dialog-title"
      >
        <div className="market-heatmap-detail-heading">
          <div>
            <span className="eyebrow">ETF market + research details · 行情与研究详情</span>
            <h4 id="etf-universe-dialog-title">{candidate.symbol} · {candidate.name}</h4>
          </div>
          <button className="secondary-action" type="button" autoFocus onClick={onClose}>
            Close details
          </button>
        </div>
        <div className="heatmap-detail-badges">
          {held && <span>● HELD ETF · 直接持有</span>}
          {candidate.related_holdings.length > 0 && (
            <span>◆ RELATED {candidate.related_holdings.length} · 持有相关股票，并非持有该 ETF</span>
          )}
          {recommendation ? (
            <span>{recommendationModeBadge(recommendation.recommendation_mode)}</span>
          ) : (
            <span>Not in the current evidence-backed shortlist</span>
          )}
        </div>
        <section className="etf-detail-section">
          <div className="section-heading-row">
            <div>
              <h5>Market data · 行情</h5>
              <p>Observable data only; price direction is not a recommendation.</p>
            </div>
          </div>
          <div className="market-heatmap-detail-grid">
            <div><span>Latest regular-session price</span><strong>{market?.latest_price == null ? "Unavailable" : formatCurrencyPrecise(market.latest_price)}</strong></div>
            <div><span>1D move vs prior close</span><strong>{formatMarketMove(market?.percent_change ?? null)}</strong></div>
            <div><span>Prior completed close</span><strong>{market?.previous_close == null ? "Unavailable" : `${formatCurrencyPrecise(market.previous_close)}${market.previous_close_date ? ` · ${market.previous_close_date}` : ""}`}</strong></div>
            <div><span>Dollar volume</span><strong>{market?.dollar_volume == null ? "Unavailable" : formatCurrencyShort(market.dollar_volume)}</strong></div>
            <div><span>Quote observed</span><strong>{market?.quote_observed_at ? formatTimestamp(market.quote_observed_at) : "Unavailable"}</strong></div>
          </div>
          {market ? <VolumeActivityExplanation tile={market} /> : (
            <p className="empty-state">No market-data tile is available for this fund.</p>
          )}
        </section>
        <section className="etf-detail-section">
          <h5>Portfolio relationship · 持仓关系</h5>
          <p>
            {held
              ? "This exact ETF ticker appears in the active holdings snapshot."
              : "This exact ETF ticker does not appear in the active holdings snapshot."}
          </p>
          {candidate.related_holdings.length > 0 ? (
            <details open>
              <summary>Related stock holdings ({candidate.related_holdings.length})</summary>
              <p>{candidate.related_holdings.join(", ")}</p>
            </details>
          ) : (
            <p>No directly mapped individual-stock overlap is recorded for this exposure.</p>
          )}
        </section>
        <section className="etf-detail-section recommendation-identity">
          <h5>Current research role · 当前推荐身份</h5>
          {recommendation ? (
            <dl>
              <div><dt>Role</dt><dd>{recommendationModeLabel(recommendation.recommendation_mode)}</dd></div>
              <div><dt>Why research it</dt><dd>{recommendation.rationale}</dd></div>
              <div><dt>Counter-evidence</dt><dd>{recommendation.counter_evidence}</dd></div>
              <div><dt>Stop / invalidate if</dt><dd>{recommendation.invalidation_signal}</dd></div>
              <div><dt>Overlap risk</dt><dd>{recommendation.overlap_risk}</dd></div>
            </dl>
          ) : (
            <p>
              This fund remains in the controlled comparison universe but was not selected in
              the current evidence-backed shortlist. That is not a permanent rejection and is
              not a recommendation to sell it.
            </p>
          )}
        </section>
        <section className="etf-detail-section fund-reference">
          <h5>Fund reference · 基金资料</h5>
          <dl>
            <div><dt>Issuer</dt><dd>{candidate.issuer}</dd></div>
            <div><dt>Portfolio role</dt><dd>{candidate.portfolio_role}</dd></div>
            <div><dt>Universe group</dt><dd>{candidate.candidate_category === "sector_research" ? "Broad sector" : "Industry"}</dd></div>
            <div><dt>Source status</dt><dd>{candidate.source_link_note}{candidate.source_checked_at ? ` Checked ${candidate.source_checked_at}.` : ""}</dd></div>
          </dl>
          <a href={candidate.source_url} target="_blank" rel="noreferrer">
            {candidate.source_link_kind === "issuer_directory"
              ? `Open official ETF directory and search ${candidate.symbol}`
              : `Open ${candidate.symbol} official fund profile`}
          </a>
        </section>
      </article>
    </div>
  );
}

function VolumeActivityExplanation({ tile }: { tile: MarketMapTile }) {
  return (
    <section className="volume-z-explanation">
      <div className="section-heading-row">
        <div>
          <h5>Volume activity · 成交量活跃度</h5>
          <p>
            <span className={`volume-activity-label detail ${volumeActivityLabelClass(tile.volume_activity)}`}>
              {tile.volume_activity}
            </span>
            {tile.volume_z_score === null
              ? " · Z-value unavailable"
              : ` · Robust Z = ${tile.volume_z_score.toFixed(2)}`}
          </p>
        </div>
        <span className="status-chip neutral">{tile.volume_reference_sessions} reference sessions</span>
      </div>
      <div className="volume-activity-interpretation">
        <strong>What this status means · 当前状态怎么理解</strong>
        <span>{volumeActivityMeaning(tile.volume_activity)}</span>
      </div>
      <div className="volume-activity-scale" aria-label="Volume activity thresholds">
        <span><strong>Quiet</strong>Z ≤ −1.5 · unusually light participation</span>
        <span><strong>Normal</strong>−1.5 &lt; Z &lt; 1 · typical range</span>
        <span><strong>Elevated</strong>1 ≤ Z &lt; 2 · above-normal participation</span>
        <span><strong>High</strong>2 ≤ Z &lt; 3 · distinctly unusual participation</span>
        <span><strong>Unusual</strong>Z ≥ 3 · extreme relative participation</span>
      </div>
      <code>
        Robust Z = [ln(1 + V observed) − median(ln(1 + V reference))]
        {' ÷ '}[1.4826 × MAD(ln(1 + V reference))]
      </code>
      {tile.volume_z_score !== null
        && tile.volume_observation_value !== null
        && tile.volume_reference_median !== null
        && tile.volume_reference_log_mad !== null && (
          <code>
            = [ln(1 + {formatOptionalCompactNumber(tile.volume_observation_value)})
            {' − '}ln(1 + {formatOptionalCompactNumber(tile.volume_reference_median)})]
            {' ÷ '}[1.4826 × {tile.volume_reference_log_mad.toFixed(4)}]
            {' = '}{tile.volume_z_score.toFixed(2)}
          </code>
        )}
      <div className="volume-z-inputs">
        <span>Observed completed-session volume: {formatOptionalCompactNumber(tile.volume_observation_value)}</span>
        <span>Reference median volume: {formatOptionalCompactNumber(tile.volume_reference_median)}</span>
        <span>Reference log-MAD: {tile.volume_reference_log_mad === null ? "Unavailable" : tile.volume_reference_log_mad.toFixed(4)}</span>
        <span>Observed session: {tile.volume_observation_date ?? "Unavailable"}</span>
        <span>Reference range: {tile.volume_reference_start ?? "Unavailable"} → {tile.volume_reference_end ?? "Unavailable"}</span>
      </div>
      <p>
        This indicator compares an ETF with its own recent completed sessions; it does not
        compare fund popularity across ETFs. A positive extreme means participation was unusual,
        not bullish: pair it with the price direction to distinguish heavy buying pressure from
        heavy selling pressure. Event days, index rebalances, and one-off flows can also raise it,
        so it is a confirmation/context metric—not a forecast or standalone BUY/SELL signal.
      </p>
      {tile.volume_quality !== "supported" && (
        <p className="volume-quality-warning">
          Argus does not use this value in decisions because its quality status is
          {` ${formatStatus(tile.volume_quality)}`}.
        </p>
      )}
    </section>
  );
}

function PortfolioCharts({
  summary,
  targetAllocation
}: {
  summary: PortfolioSummaryResponse;
  targetAllocation: Record<string, number>;
}) {
  return (
    <section className="portfolio-block" aria-label="Portfolio analysis charts">
      <h2>Portfolio charts</h2>
      <div className="investment-chart-grid">
        <AllocationDonutChart allocation={summary.allocation} />
        <PositionConcentrationChart positions={summary.positions} />
        <AllocationDriftChart
          allocation={summary.allocation}
          targetAllocation={targetAllocation}
        />
      </div>
    </section>
  );
}

function PortfolioPlanningSummary({
  cashPlan,
  retirementPlan,
  onOpen
}: {
  cashPlan: CashPlan;
  retirementPlan: RetirementFundingPlan;
  onOpen: () => void;
}) {
  const retirementStatus = retirementPlan.status === "on_track"
    || retirementPlan.status === "already_funded"
    || retirementPlan.status === "income_covers_spending"
    ? "On modeled track"
    : retirementPlan.status === "funding_gap"
      ? "Monthly gap"
      : "Inputs needed";

  return (
    <section className="portfolio-block planning-summary" aria-label="Money planning summary">
      <div className="section-heading-row">
        <div>
          <h2>Money planning summary · 现金与退休规划摘要</h2>
          <p className="section-note">
            These goal-based amounts constrain how much new cash is available for investing.
            Detailed schedules and formulas now live in Money Planning.
          </p>
        </div>
        <button type="button" className="secondary-action" onClick={onOpen}>
          <PiggyBank aria-hidden="true" />
          <span>View Money Planning</span>
        </button>
      </div>
      <div className="compact-metric-grid planning-summary-metrics">
        <div className="metric-card">
          <span>Short-term goals · minimum saving</span>
          <strong>{formatCurrency(cashPlan.monthly_required)} / mo</strong>
          <small>{formatCashPlanStatus(cashPlan.feasibility_status)}</small>
        </div>
        <div className="metric-card">
          <span>Retirement · required starting deposit</span>
          <strong>{formatOptionalCurrency(retirementPlan.required_monthly_investment)} / mo</strong>
          <small>{retirementStatus}</small>
        </div>
        <div className="metric-card">
          <span>Current planned investing</span>
          <strong>{formatCurrency(retirementPlan.planned_monthly_investment)} / mo</strong>
          <small>Saved Profile contribution</small>
        </div>
      </div>
    </section>
  );
}

function AllocationDonutChart({
  allocation
}: {
  allocation: AllocationSlice[];
}) {
  const radius = 58;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const slices = allocation.map((item, index) => {
    const length = item.weight * circumference;
    const dashOffset = -offset;
    offset += length;
    return {
      ...item,
      color: chartColor(index),
      dashArray: `${length} ${Math.max(0, circumference - length)}`,
      dashOffset
    };
  });

  return (
    <div className="investment-chart-panel">
      <h3>Asset allocation</h3>
      <svg viewBox="0 0 180 180" role="img" aria-label="Asset allocation pie chart">
        <circle
          cx="90"
          cy="90"
          r={radius}
          fill="none"
          stroke="#e1e7ec"
          strokeWidth="24"
        />
        {slices.map((slice) => (
          <circle
            key={slice.asset_class}
            cx="90"
            cy="90"
            r={radius}
            fill="none"
            stroke={slice.color}
            strokeDasharray={slice.dashArray}
            strokeDashoffset={slice.dashOffset}
            strokeLinecap="butt"
            strokeWidth="24"
            transform="rotate(-90 90 90)"
          />
        ))}
        <text className="chart-center-label" x="90" y="84" textAnchor="middle">
          Total
        </text>
        <text className="chart-center-value" x="90" y="104" textAnchor="middle">
          {formatCurrencyShort(
            allocation.reduce((total, item) => total + item.market_value, 0)
          )}
        </text>
      </svg>
      <ul className="chart-legend">
        {slices.map((slice) => (
          <li key={slice.asset_class}>
            <span style={{ background: slice.color }} aria-hidden="true" />
            <strong>{slice.asset_class}</strong>
            <em>{formatPercent(slice.weight)}</em>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PositionConcentrationChart({
  positions
}: {
  positions: PortfolioPosition[];
}) {
  const topPositions = positions.slice(0, 6);
  return (
    <div className="investment-chart-panel">
      <h3>Position concentration</h3>
      <ul className="bar-chart-list">
        {topPositions.map((position, index) => (
          <li key={`${position.symbol}-${position.account ?? ""}`}>
            <div className="bar-chart-row-label">
              <strong>{position.symbol}</strong>
              <span>{formatPercent(position.weight)}</span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <span
                style={{
                  background: chartColor(index),
                  width: `${Math.max(2, position.weight * 100)}%`
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AllocationDriftChart({
  allocation,
  targetAllocation
}: {
  allocation: AllocationSlice[];
  targetAllocation: Record<string, number>;
}) {
  const rows = allocationDriftRows(allocation, targetAllocation);
  if (rows.length === 0) {
    return (
      <div className="investment-chart-panel">
        <h3>Current vs target</h3>
        <p className="chart-empty">
          Save target allocation in Profile to compare current and target weights.
        </p>
      </div>
    );
  }

  return (
    <div className="investment-chart-panel">
      <h3>Current vs target</h3>
      <ul className="drift-chart-list">
        {rows.map((row) => (
          <li key={row.assetClass}>
            <div className="bar-chart-row-label">
              <strong>{row.assetClass}</strong>
              <span>{formatPercent(row.current)} / {formatPercent(row.target)}</span>
            </div>
            <div className="paired-bar-row">
              <span
                className="current-bar"
                style={{ width: `${Math.max(2, row.current * 100)}%` }}
              />
              <span
                className="target-bar"
                style={{ width: `${Math.max(2, row.target * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
      <div className="paired-bar-legend">
        <span><i className="current-swatch" />Current</span>
        <span><i className="target-swatch" />Target</span>
      </div>
    </div>
  );
}

function MoneyInput({
  id,
  label,
  value,
  onChange,
  note,
  placeholder,
  disabled = false
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  note: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <label className="profile-field-with-note" htmlFor={id}>
      {label}
      <input
        id={id}
        type="text"
        inputMode="decimal"
        placeholder={placeholder ?? "e.g. 125,000"}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          const formatted = formatMoneyTyping(event.target.value);
          if (formatted !== null) {
            onChange(formatted);
          }
        }}
      />
      <span>{note} Thousands separators appear while you type.</span>
    </label>
  );
}

function ProfileWorkspace({
  form,
  guidance,
  guidanceState,
  profile,
  profileState,
  stylePacks,
  methodDocuments,
  methodDocumentFile,
  methodDocumentState,
  onChange,
  onClear,
  onDeleteMethodDocument,
  onGenerateGuidance,
  onMethodDocumentChange,
  onMethodDocumentFileChange,
  onSave,
  onUploadMethodDocument
}: {
  form: ProfileFormState;
  guidance: ProfileGuidanceResponse | null;
  guidanceState: RequestState;
  profile: ProfileResponse | null;
  profileState: RequestState;
  stylePacks: StylePackResponse[];
  methodDocuments: MethodDocumentResponse[];
  methodDocumentFile: File | null;
  methodDocumentState: RequestState;
  onChange: (value: ProfileFormState) => void;
  onClear: () => void;
  onDeleteMethodDocument: (documentId: number) => Promise<void>;
  onGenerateGuidance: () => void;
  onMethodDocumentChange: (value: number[]) => void;
  onMethodDocumentFileChange: (value: File | null) => void;
  onSave: () => void;
  onUploadMethodDocument: (file?: File | null) => Promise<void>;
}) {
  const busy = profileState.status === "loading";
  const guiding = guidanceState.status === "loading";
  const update = (patch: Partial<ProfileFormState>) => onChange({ ...form, ...patch });
  const recommendedStyle = recommendInvestmentStyle(form);
  const activeStylePack = stylePacks.find(
    (pack) => pack.definition.id === form.preferredStyle
  );
  const retirementPlanningYears = Math.max(
    0,
    (Number(form.retirementPlanningAge) || 100)
      - (Number(form.plannedRetirementAge) || 0)
  );
  const savedEmergencyTarget = profile
    ? (profile.emergency_fund_target_amount
      ?? ((profile.emergency_fund_months > 0 && (profile.monthly_essential_expenses ?? 0) > 0)
        ? profile.emergency_fund_months * (profile.monthly_essential_expenses ?? 0)
        : 0))
    : 0;
  const selectedCashGoalTypes = new Set(form.cashGoals.map((goal) => goal.goalType));
  const toggleCashGoal = (goalType: CashGoalType, enabled: boolean) => {
    const cashGoals = enabled
      ? [
          ...form.cashGoals,
          { goalType, targetAmount: "", monthsUntilNeeded: "", priority: "important" as const }
        ]
      : form.cashGoals.filter((goal) => goal.goalType !== goalType);
    update({ cashGoals });
  };
  const updateCashGoal = (
    goalType: CashGoalType,
    patch: Partial<CashGoalFormItem>
  ) => update({
    cashGoals: form.cashGoals.map((goal) => (
      goal.goalType === goalType ? { ...goal, ...patch } : goal
    ))
  });

  return (
    <div className="profile-workspace-layout">
      <form
        className="input-stack profile-editor"
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <div className="profile-editor-toolbar">
          <div>
            <h2>Edit Profile</h2>
            <p className="field-note">Defaults are examples until you review and save them.</p>
          </div>
          <button
            className="restore-defaults-button"
            type="button"
            disabled={busy}
            onClick={onClear}
          >
            <RefreshCw aria-hidden="true" />
            <span>Clear &amp; restore defaults</span>
          </button>
        </div>
        <div className="profile-section-heading">
          <span>1</span>
          <div>
            <h2>Investor context</h2>
            <p>Risk capacity, time horizon, experience, income stability, and liquidity.</p>
          </div>
        </div>
        <div className="profile-grid profile-context-panel">
          <label htmlFor="risk-tolerance">
            Risk tolerance
            <select
              id="risk-tolerance"
              value={form.riskTolerance}
              onChange={(event) => update({ riskTolerance: event.target.value })}
            >
              <option value="">Select risk tolerance</option>
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </label>
          <label htmlFor="life-stage">
            Life stage
            <select
              id="life-stage"
              value={form.lifeStage}
              onChange={(event) => update({ lifeStage: event.target.value })}
            >
              <option value="">Select life stage</option>
              {lifeStageOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="profile-field-with-note" htmlFor="investment-horizon">
            Investment horizon
            <select
              id="investment-horizon"
              value={form.investmentHorizon}
              onChange={(event) => update({ investmentHorizon: event.target.value })}
            >
              <option value="">Select horizon</option>
              {investmentHorizonOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <span>How long until this money is needed. This affects risk capacity.</span>
          </label>
          <label className="profile-field-with-note" htmlFor="investing-experience">
            Investing experience · years already invested
            <select
              id="investing-experience"
              value={form.investingExperience}
              onChange={(event) => update({ investingExperience: event.target.value })}
            >
              <option value="">Select experience</option>
              {investingExperienceOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <span>Used to simplify explanations and product choices—not to assume you can take more risk.</span>
          </label>
          <label htmlFor="income-stability">
            Income stability
            <select
              id="income-stability"
              value={form.incomeStability}
              onChange={(event) => update({ incomeStability: event.target.value })}
            >
              <option value="">Select stability</option>
              {incomeStabilityOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label htmlFor="liquidity-needs">
            Liquidity needs
            <select
              id="liquidity-needs"
              value={form.liquidityNeeds}
              onChange={(event) => update({ liquidityNeeds: event.target.value })}
            >
              <option value="">Select liquidity need</option>
              {liquidityNeedOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
        </div>
        <section className="profile-cashflow-panel investment-approach-panel" aria-label="Investment approach">
          <div className="profile-section-heading embedded">
            <span>2</span>
            <div>
              <h2>Investment approach</h2>
              <p>Required base style AND an optional expert research method.</p>
            </div>
          </div>
          <div className="investment-approach-grid">
            <div className="profile-field-with-note">
              <label htmlFor="preferred-style">Base investment style</label>
              <select
                id="preferred-style"
                value={form.preferredStyle}
                onChange={(event) => update({ preferredStyle: event.target.value })}
              >
                <option value="">Select investment style</option>
                {stylePacks.map((pack) => (
                  <option key={pack.definition.id} value={pack.definition.id}>
                    {pack.definition.name}{pack.builtin ? "" : " · custom"}
                  </option>
                ))}
              </select>
              <span>Suggested starting style: {recommendedStyle}</span>
              {activeStylePack && (
                <details className="base-style-details">
                  <summary>How {activeStylePack.definition.name} guides Argus</summary>
                  <p>{activeStylePack.definition.description}</p>
                  <dl>
                    <div>
                      <dt>Research lenses</dt>
                      <dd>{activeStylePack.definition.research_lenses.join(", ")}</dd>
                    </div>
                    <div>
                      <dt>Portfolio priorities</dt>
                      <dd>{activeStylePack.definition.portfolio_priorities.join(", ")}</dd>
                    </div>
                    <div>
                      <dt>Product preferences</dt>
                      <dd>{activeStylePack.definition.product_preferences.join(", ")}</dd>
                    </div>
                  </dl>
                </details>
              )}
            </div>
            <div className="method-composition-plus" aria-hidden="true">
              <span>+</span>
            </div>
            <div className="method-panel-selector" role="group" aria-labelledby="expert-method-panel-title">
              <div className="method-panel-header">
                <strong id="expert-method-panel-title">Expert methods (optional, select up to 5)</strong>
                <span>{form.preferredMethodDocumentIds.length} / {MAX_METHOD_PANEL_DOCUMENTS} selected</span>
              </div>
              {methodDocuments.length > 0 ? methodDocuments.map((document) => {
                const selected = form.preferredMethodDocumentIds.includes(document.id);
                return (
                  <div className="method-panel-option" key={document.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selected}
                        disabled={!selected && form.preferredMethodDocumentIds.length >= MAX_METHOD_PANEL_DOCUMENTS}
                        onChange={(event) => {
                          const value = event.target.checked
                            ? [...form.preferredMethodDocumentIds, document.id].slice(
                                0,
                                MAX_METHOD_PANEL_DOCUMENTS
                              )
                            : form.preferredMethodDocumentIds.filter((id) => id !== document.id);
                          update({ preferredMethodDocumentIds: value });
                          onMethodDocumentChange(value);
                        }}
                      />
                      <span><strong>{document.name}</strong><small>{document.source_type} · {document.checklist_items.length} checks</small></span>
                    </label>
                    <button
                      className="method-panel-delete"
                      type="button"
                      aria-label={`Delete ${document.name} expert method`}
                      title="Delete this saved expert method"
                      disabled={methodDocumentState.status === "loading"}
                      onClick={() => void onDeleteMethodDocument(document.id)}
                    >
                      <Trash2 aria-hidden="true" />
                    </button>
                  </div>
                );
              }) : <p className="field-note">Upload a method document to add an expert lens.</p>}
              <p>
                Argus compares panel agreements and conflicts, then resolves them with accepted
                evidence and the base style. Methods never become evidence or alter trade math.
              </p>
            </div>
          </div>
          <div className="method-document-upload-row">
            <input
              className="hidden-file-input"
              key={methodDocumentFile
                ? `${methodDocumentFile.name}-${methodDocumentFile.size}`
                : "empty-profile-method"}
              id="profile-method-file"
              type="file"
              accept=".md,.markdown,.txt,.doc,.docx,.pdf,.csv,text/markdown,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf,text/csv"
              disabled={methodDocumentState.status === "loading"}
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                onMethodDocumentFileChange(file);
                if (file) {
                  onUploadMethodDocument(file);
                }
              }}
            />
            <label
              className={`compact-upload-trigger${methodDocumentState.status === "loading" ? " disabled" : ""}`}
              htmlFor="profile-method-file"
            >
              {methodDocumentState.status === "loading"
                ? <Loader2 className="spin" aria-hidden="true" />
                : <Upload aria-hidden="true" />}
              <span>{methodDocumentState.status === "loading" ? "Compiling…" : "Choose & upload expert method"}</span>
            </label>
            <span>Markdown, TXT, Word DOC/DOCX, text PDF, or research CSV · 5 MB max</span>
          </div>
          {methodDocumentState.status !== "success" && (
            <RequestStatus state={methodDocumentState} />
          )}
        </section>
        <section className="profile-cashflow-panel monthly-cashflow-panel" aria-label="Monthly cash flow inputs">
          <div className="profile-section-heading embedded">
            <span>3</span>
            <div>
              <h2>Monthly cash flow</h2>
              <p className="field-note">
                Enter these before requesting a mix. Income changes risk-capacity and
                contribution-affordability checks; it does not determine a fixed allocation
                by itself.
              </p>
            </div>
          </div>
          <div className="profile-cashflow-grid">
            <MoneyInput
              id="monthly-net-income"
              label="Monthly net cash income (USD)"
              value={form.monthlyNetIncome}
              placeholder="After-tax recurring income"
              onChange={(value) => update({ monthlyNetIncome: value })}
              note="Recurring after-tax income; enter 0 if you currently have none."
            />
            <MoneyInput
              id="monthly-total-expenses"
              label="Normalized monthly spending (USD)"
              value={form.monthlyTotalExpenses}
              onChange={(value) => update({ monthlyTotalExpenses: value })}
              note="Recurring spending plus predictable annual bills divided by 12. Do not include the separate one-time goals selected below."
            />
            <MoneyInput
              id="monthly-contribution"
              label="Planned monthly investment (USD)"
              value={form.monthlyContribution}
              placeholder="e.g. 500 or 1,500"
              onChange={(value) => update({ monthlyContribution: value })}
              note="This is deducted after total spending before Argus tests cash-goal capacity."
            />
            <MoneyInput
              id="monthly-sector-satellite-budget"
              label="Optional sector / industry ETF budget (USD / month)"
              value={form.monthlySectorSatelliteBudget}
              placeholder="0 disables sector ETF DCA"
              onChange={(value) => update({ monthlySectorSatelliteBudget: value })}
              note="This is a capped part of—not additional to—the planned monthly investment. Argus uses it only when a current evidence-backed ETF candidate is also suitable for recurring investing."
            />
            <label className="profile-field-with-note" htmlFor="financial-priority">
              Primary financial / life priority
              <input
                id="financial-priority"
                type="text"
                maxLength={256}
                placeholder="e.g. career transition, family flexibility, early retirement"
                value={form.primaryFinancialPriority}
                onChange={(event) => update({ primaryFinancialPriority: event.target.value })}
              />
              <span>
                The life outcome Argus should protect first when income cannot cover every
                goal. It appears in Portfolio → Cash goal plan as the priority to preserve
                before lower-priority goals; it changes trade-off guidance, not returns.
              </span>
            </label>
          </div>
        </section>
        <section className="profile-cashflow-panel cash-goals-panel" aria-label="Cash goal inputs">
          <div className="profile-section-heading embedded">
            <span>4</span>
            <div>
              <h2>Cash and retirement goals · 现金与退休规划</h2>
              <p className="field-note">
                Select any applicable short-term expense types instead of naming them
                manually. A selected goal may remain unestimated as a reminder, but Argus
                needs both an approximate amount and months-until-needed before including
                it in savings or investment-capacity calculations.
              </p>
            </div>
          </div>
          <div className="profile-cashflow-grid">
            <MoneyInput
              id="essential-expenses"
              label="Essential monthly expenses (USD)"
              value={form.monthlyEssentialExpenses}
              onChange={(value) => update({ monthlyEssentialExpenses: value })}
              note="Housing, utilities, food, insurance, minimum debt payments, and necessary care."
            />
            <MoneyInput
              id="current-cash-savings"
              label="Current cash savings (USD)"
              value={form.currentCashSavings}
              onChange={(value) => update({ currentCashSavings: value })}
              note="Bank savings, CDs, Treasury bills, money-market funds, and brokerage cash you choose to count."
            />
            <fieldset className="retirement-calculator-inputs">
              <legend>Retirement calculator inputs · 退休计算输入</legend>
              <p className="retirement-input-intro">
                These inputs follow the structure of the FINRA retirement calculator.
                Spending is after tax and in today's dollars; return is after investment
                expenses. <a href="https://retirementcalculator.nga.finra.org/calculator/"
                  target="_blank" rel="noreferrer">Review the FINRA reference</a>.
              </p>
              <div className="retirement-input-grid">
                <label htmlFor="current-age">
                  Current age
                  <input id="current-age" type="number" min="18" max="100" step="1"
                    value={form.currentAge}
                    onChange={(event) => update({ currentAge: event.target.value })} />
                </label>
                <label htmlFor="planned-retirement-age">
                  Planned retirement age
                  <input id="planned-retirement-age" type="number" min="18" max="100" step="1"
                    value={form.plannedRetirementAge}
                    onChange={(event) => update({ plannedRetirementAge: event.target.value })} />
                </label>
                <label className="profile-field-with-note" htmlFor="retirement-planning-age">
                  Fund withdrawals through age
                  <input id="retirement-planning-age" type="number" min="80" max="120" step="1"
                    value={form.retirementPlanningAge}
                    onChange={(event) => update({ retirementPlanningAge: event.target.value })} />
                  <span>{Number(form.plannedRetirementAge) > 0
                    ? `${retirementPlanningYears} modeled retirement years; age 100 is a conservative horizon.`
                    : "Add a retirement age to calculate the withdrawal period."}</span>
                </label>
                <MoneyInput
                  id="retirement-current-savings"
                  label="Already saved for retirement (USD)"
                  value={form.retirementCurrentSavings}
                  placeholder="Blank = use uploaded investments"
                  onChange={(value) => update({ retirementCurrentSavings: value })}
                  note="Enter retirement-designated savings across accounts. Leave blank only when the uploaded portfolio represents all retirement investments."
                />
                <MoneyInput
                  id="retirement-monthly-spending"
                  label="Desired after-tax retirement spending (today's USD / month)"
                  value={form.retirementMonthlySpending}
                  onChange={(value) => update({ retirementMonthlySpending: value })}
                  note="The amount you want available for living expenses after taxes. Blank uses essential monthly expenses."
                />
                <MoneyInput
                  id="retirement-monthly-income"
                  label="Other reliable retirement income before tax (USD / month)"
                  value={form.retirementMonthlyIncome}
                  placeholder="Social Security + pension; 0 if unknown"
                  onChange={(value) => update({ retirementMonthlyIncome: value })}
                  note="Social Security, pension, annuity, or other income outside withdrawals from this retirement account."
                />
                <label className="checkbox-field profile-field-with-note" htmlFor="retirement-income-taxable">
                  <input id="retirement-income-taxable" type="checkbox"
                    checked={form.retirementIncomeTaxable}
                    onChange={(event) => update({ retirementIncomeTaxable: event.target.checked })} />
                  <span>Other retirement income is taxable</span>
                  <small>When uncertain or mixed, checked is the more conservative simplified assumption.</small>
                </label>
                <label className="profile-field-with-note" htmlFor="retirement-account-type">
                  Retirement account tax treatment
                  <select id="retirement-account-type" value={form.retirementAccountType}
                    onChange={(event) => update({
                      retirementAccountType: event.target.value,
                      retirementTaxableWithdrawalShare:
                        event.target.value === "mixed"
                          ? form.retirementTaxableWithdrawalShare
                          : ""
                    })}>
                    <option value="">Select account type</option>
                    <option value="traditional_401k">Traditional 401(k) · pre-tax</option>
                    <option value="traditional_ira">Traditional IRA / SEP · pre-tax</option>
                    <option value="roth">Roth IRA / Roth 401(k) · after-tax</option>
                    <option value="taxable_brokerage">Taxable brokerage · after-tax</option>
                    <option value="mixed">Mixed · Traditional 401(k)/IRA + Roth</option>
                  </select>
                  <span>Select Mixed when retirement savings span both pre-tax Traditional and after-tax Roth accounts.</span>
                </label>
                {form.retirementAccountType === "mixed" && (
                  <label className="profile-field-with-note" htmlFor="retirement-taxable-share">
                    Expected withdrawals from pre-tax Traditional accounts (%)
                    <input id="retirement-taxable-share" type="number" min="0" max="100" step="1"
                      value={form.retirementTaxableWithdrawalShare}
                      onChange={(event) => update({ retirementTaxableWithdrawalShare: event.target.value })} />
                    <span>Example: if about 60% will come from a Traditional 401(k) and 40% from Roth, enter 60. This controls the simplified withdrawal tax gross-up.</span>
                  </label>
                )}
                <label className="profile-field-with-note" htmlFor="retirement-inflation-rate">
                  Expected inflation rate (%)
                  <input id="retirement-inflation-rate" type="number" min="0" max="15" step="0.1"
                    value={form.retirementInflationRate}
                    onChange={(event) => update({ retirementInflationRate: event.target.value })} />
                  <span>Used to increase future spending and to calculate the real return.</span>
                </label>
                <label className="profile-field-with-note" htmlFor="retirement-annual-return">
                  Expected annual return after investment expenses (%)
                  <input id="retirement-annual-return" type="number" min="-50" max="50" step="0.1"
                    value={form.retirementAnnualReturn}
                    onChange={(event) => update({ retirementAnnualReturn: event.target.value })} />
                  <span>This is an assumption—not a forecast. Try multiple scenarios.</span>
                </label>
                <label className="profile-field-with-note" htmlFor="retirement-current-tax-rate">
                  Current combined marginal tax rate (%) · optional
                  <input id="retirement-current-tax-rate" type="number" min="0" max="75" step="0.1"
                    value={form.retirementCurrentTaxRate}
                    onChange={(event) => update({ retirementCurrentTaxRate: event.target.value })} />
                  <span>Only estimates take-home cost for deductible pre-tax deposits. Leave blank to omit that secondary estimate.</span>
                </label>
                <label className="profile-field-with-note" htmlFor="retirement-tax-rate">
                  Estimated combined retirement marginal tax rate (%) · optional
                  <input id="retirement-tax-rate" type="number" min="0" max="75" step="0.1"
                    value={form.retirementTaxRate}
                    onChange={(event) => update({ retirementTaxRate: event.target.value })} />
                  <span>Blank now produces a clearly labeled tax-excluded baseline; taxable income or pre-tax withdrawals will need more assets.</span>
                </label>
                <p className="tax-rate-explanation">
                  Why there is no automatic state-only rate: a U.S. marginal tax rate also
                  depends on federal brackets, filing status, taxable income, deductions,
                  account type, and the state where you will live in retirement. A state
                  selection alone cannot produce a defensible personal rate. Argus therefore
                  keeps this assumption optional instead of silently inserting a misleading number.
                </p>
                <label className="checkbox-field profile-field-with-note" htmlFor="retirement-adjust-inflation">
                  <input id="retirement-adjust-inflation" type="checkbox"
                    checked={form.retirementAdjustContributionsForInflation}
                    onChange={(event) => update({
                      retirementAdjustContributionsForInflation: event.target.checked
                    })} />
                  <span>Increase monthly deposits with inflation each year</span>
                  <small>The result becomes the required first-year monthly deposit; later deposits rise with inflation.</small>
                </label>
              </div>
            </fieldset>
            <fieldset className="emergency-fund-group">
              <legend>Emergency cash reserve · 急用钱储备</legend>
              <label className="checkbox-field emergency-fund-toggle" htmlFor="emergency-enabled">
                <input
                  id="emergency-enabled"
                  type="checkbox"
                  checked={form.emergencyFundEnabled}
                  onChange={(event) => update({ emergencyFundEnabled: event.target.checked })}
                />
                <span>Include an emergency-fund savings goal</span>
              </label>
              <div className="emergency-fund-fields">
                <MoneyInput
                  id="emergency-fund-target"
                  label="How much liquid cash do you want available? (USD)"
                  value={form.emergencyFundTargetAmount}
                  disabled={!form.emergencyFundEnabled}
                  onChange={(value) => update({ emergencyFundTargetAmount: value })}
                  note="Enter the total reserve you want Argus to build. This is a direct dollar target, not a months-of-expenses formula."
                />
                <label className="profile-field-with-note" htmlFor="emergency-build-months">
                  When should the full reserve be ready? · months from now
                  <input id="emergency-build-months" type="number" min="1" max="120" step="1"
                    disabled={!form.emergencyFundEnabled}
                    value={form.emergencyFundBuildMonths}
                    onChange={(event) => update({ emergencyFundBuildMonths: event.target.value })} />
                  <span>Example: 12 means the full reserve should be available within 12 months.</span>
                </label>
              </div>
              <p>
                Portfolio will subtract current cash already assigned to this goal, show the
                remaining gap, and calculate the minimum monthly saving needed by the deadline.
                Known medical, tuition, travel, or purchase bills belong in the dated goals below.
              </p>
            </fieldset>
            <div className="cash-goal-selector">
              <div>
                <h3>Short-term one-time expense types</h3>
                <p className="field-note">
                  Unknown emergencies belong in the emergency fund. Select a dated goal
                  only when you can make a reasonable estimate; these goals reduce current
                  investable cash and remain separate from the retirement projection.
                </p>
              </div>
              <div className="cash-goal-option-grid">
                {cashGoalOptions.map((option) => (
                  <label className="cash-goal-option" key={option.goalType}
                    htmlFor={`cash-goal-${option.goalType}`}>
                    <input id={`cash-goal-${option.goalType}`} type="checkbox"
                      checked={selectedCashGoalTypes.has(option.goalType)}
                      onChange={(event) => toggleCashGoal(option.goalType, event.target.checked)} />
                    <span><strong>{option.label}</strong><small>{option.description}</small></span>
                  </label>
                ))}
              </div>
              {form.cashGoals.length > 0 && (
                <div className="selected-cash-goals">
                  {form.cashGoals.map((goal) => {
                    const option = cashGoalOptions.find(
                      (candidate) => candidate.goalType === goal.goalType
                    );
                    return (
                      <section className="selected-cash-goal" key={goal.goalType}>
                        <h4>{option?.label ?? goal.goalType}</h4>
                        <div className="selected-cash-goal-fields">
                          <MoneyInput
                            id={`cash-goal-${goal.goalType}-amount`}
                            label="Estimated total amount (USD)"
                            value={goal.targetAmount}
                            onChange={(value) => updateCashGoal(
                              goal.goalType,
                              { targetAmount: value }
                            )}
                            note="Leave blank when genuinely unknown; the plan will flag it as uncalculated."
                          />
                          <label className="profile-field-with-note"
                            htmlFor={`cash-goal-${goal.goalType}-months`}>
                            Needed within · months
                            <input id={`cash-goal-${goal.goalType}-months`} type="number"
                              min="1" max="120" step="1"
                              value={goal.monthsUntilNeeded}
                              onChange={(event) => updateCashGoal(
                                goal.goalType,
                                { monthsUntilNeeded: event.target.value }
                              )} />
                            <span>Short-term goals support 1–120 months.</span>
                          </label>
                          <label className="profile-field-with-note"
                            htmlFor={`cash-goal-${goal.goalType}-priority`}>
                            Priority
                            <select id={`cash-goal-${goal.goalType}-priority`}
                              value={goal.priority}
                              onChange={(event) => updateCashGoal(
                                goal.goalType,
                                { priority: event.target.value as CashGoalPriority }
                              )}>
                              <option value="urgent">Urgent / required</option>
                              <option value="important">Important</option>
                              <option value="flexible">Flexible</option>
                            </select>
                            <span>Higher-priority goals receive available cash first.</span>
                          </label>
                        </div>
                      </section>
                    );
                  })}
                </div>
              )}
            </div>
            <fieldset className="education-goal-group">
              <legend>Child education goal · 子女教育资金</legend>
              <div className="education-goal-grid">
                <label className="profile-field-with-note" htmlFor="education-plan">
                  Education plan
                  <select id="education-plan" value={form.educationPlan}
                    onChange={(event) => update({
                      educationPlan: event.target.value,
                      educationTargetYear: event.target.value === "none" ? "" : form.educationTargetYear,
                      educationTargetAmount: event.target.value === "none" ? "" : form.educationTargetAmount
                    })}>
                    <option value="none">No education cash goal</option>
                    <option value="public">Public school / college</option>
                    <option value="private">Private school / college</option>
                  </select>
                  <span>Select a plan only when you want a separate long-term education target.</span>
                </label>
                <label className="profile-field-with-note" htmlFor="education-target-year">
                  Funds needed by year
                  <input id="education-target-year" type="number" min="2026" max="2100" step="1"
                    disabled={form.educationPlan === "none"}
                    value={form.educationTargetYear}
                    onChange={(event) => update({ educationTargetYear: event.target.value })} />
                  <span>Disabled when no education cash goal is selected.</span>
                </label>
                <MoneyInput
                  id="education-target-amount"
                  label="Total education cash target (USD)"
                  value={form.educationTargetAmount}
                  disabled={form.educationPlan === "none"}
                  onChange={(value) => update({ educationTargetAmount: value })}
                  note="Enter your own target because school, aid, location, and inflation vary."
                />
                <p className="cash-goal-education-note">
                  Use this section for a longer child-education plan. Do not also select
                  Tuition / education above for the same bill.
                </p>
              </div>
            </fieldset>
          </div>
        </section>
        <section className="allocation-guide-panel" aria-label="Allocation guidance">
          <div className="answer-header">
            <div className="profile-section-heading embedded">
              <span>5</span>
              <div>
                <h2>Allocation guide</h2>
                <p className="field-note">
                  Creates an auditable starting mix from your profile inputs. It does not
                  call an external answer model and does not save or trade automatically.
                </p>
              </div>
            </div>
            <button
              className="action-button"
              type="button"
              disabled={guiding || busy}
              onClick={onGenerateGuidance}
            >
              {guiding
                ? <Loader2 className="spin" aria-hidden="true" />
                : <SlidersHorizontal aria-hidden="true" />}
              <span>Suggest percentages</span>
            </button>
          </div>
          <RequestStatus state={guidanceState} />
          {guidance && (
            <div className="allocation-guidance-result">
              <p className="guidance-method-note">{guidance.method_summary}</p>
              <div className="guidance-allocation-list">
                {Object.entries(guidance.target_allocation).map(([assetClass, weight]) => (
                  <span key={assetClass}>
                    <strong>{assetClass}</strong> {formatPercent(weight)}
                  </span>
                ))}
              </div>
              <div className="guidance-reasons">
                <strong>Why this starting mix</strong>
                <ul>
                  {guidance.rationale.map((reason) => <li key={reason}>{reason}</li>)}
                </ul>
              </div>
              <div className="guidance-warnings">
                <strong>Review before saving</strong>
                <ul>
                  {guidance.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              </div>
              <div className="guidance-references">
                <strong>Method references</strong>
                <p>
                  These sources support the factors and definitions. The exact percentages
                  are Argus example-policy calculations, not percentages prescribed by these institutions.
                </p>
                <ul>
                  {guidance.references.map((reference) => (
                    <li key={reference.url}>
                      <a href={reference.url} target="_blank" rel="noreferrer">
                        {reference.institution} · {reference.title}
                      </a>
                      <span>{reference.principle}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <p className="section-note">{guidance.disclaimer}</p>
            </div>
          )}
        </section>
        <section className="profile-policy-panel" aria-label="Investment policy inputs">
          <div className="profile-section-heading embedded">
            <span>6</span>
            <div>
              <h2>Investment policy</h2>
              <p className="section-note">
                Investment targets must add to 100%. Cash is intentionally excluded and
                planned from the separate goals above.
              </p>
            </div>
          </div>
          <div className="target-grid">
          <label htmlFor="equity-target">
            Equity target %
            <input
              id="equity-target"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={form.equityTarget}
              onChange={(event) => update({ equityTarget: event.target.value })}
            />
          </label>
          <label htmlFor="bond-target">
            Bond target %
            <input
              id="bond-target"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={form.bondTarget}
              onChange={(event) => update({ bondTarget: event.target.value })}
            />
          </label>
          <label htmlFor="commodity-target">
            Commodity / Gold target %
            <input
              id="commodity-target"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={form.commodityTarget}
              onChange={(event) => update({ commodityTarget: event.target.value })}
            />
          </label>
          <label htmlFor="international-equity-target">
            International Equity target %
            <input
              id="international-equity-target"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={form.internationalEquityTarget}
              onChange={(event) => update({ internationalEquityTarget: event.target.value })}
            />
          </label>
          <label className="profile-field-with-note" htmlFor="alternatives-target">
            Alternatives target % (excluding gold)
            <input
              id="alternatives-target"
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={form.alternativesTarget}
              onChange={(event) => update({ alternativesTarget: event.target.value })}
            />
            <span>
              Argus examples: investment/rental real estate, REITs, private equity,
              private credit, hedge-fund strategies, or crypto.
              A primary home is normally excluded unless you intentionally analyze total net worth.
            </span>
          </label>
          </div>
          <div className="recommendation-settings-grid">
          <label htmlFor="rebalance-threshold">
            Rebalance drift threshold %
            <input
              id="rebalance-threshold"
              type="number"
              min="1"
              max="25"
              step="0.5"
              value={form.rebalanceThreshold}
              onChange={(event) => update({ rebalanceThreshold: event.target.value })}
            />
          </label>
          <label htmlFor="rebalance-preference">
            Rebalance method
            <select
              id="rebalance-preference"
              value={form.rebalancePreference}
              onChange={(event) => update({ rebalancePreference: event.target.value })}
            >
              <option value="contributions_first">Use new contributions first</option>
              <option value="target_trades">Show target trades directly</option>
            </select>
          </label>
          <label className="checkbox-field profile-field-with-note" htmlFor="fractional-shares">
            <input
              id="fractional-shares"
              type="checkbox"
              checked={form.allowFractionalShares}
              onChange={(event) => update({ allowFractionalShares: event.target.checked })}
            />
            <span>Broker supports fractional shares</span>
            <small>
              Used only to convert a dollar amount into decimal shares. If unchecked,
              Argus rounds down to whole shares and shows the leftover cash. It never places an order.
            </small>
          </label>
          </div>
          <p className="section-note">
            System defaults are an example starting point, not a personalized recommendation.
          </p>
        </section>
        <div className="query-actions">
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? <Loader2 className="spin" aria-hidden="true" /> : <UserRound aria-hidden="true" />}
            <span>Save profile</span>
          </button>
        </div>
        <RequestStatus state={profileState} />
      </form>

      <aside className="portfolio-block saved-profile-panel" aria-label="Saved profile">
          <div className="answer-header">
            <h2>Saved Profile</h2>
            <span className={`run-status ${profile ? "complete" : "neutral"}`}>
              {profile ? "active" : "cleared"}
            </span>
          </div>
          {profile ? (
            <>
          <p className="section-note">
            This summary is the complete saved policy used by Portfolio calculations,
            not a generated personality label.
          </p>
          <div className="saved-profile-sections">
            <section>
              <h3>Investor context</h3>
              <dl className="profile-summary-list">
                <div><dt>Life stage</dt><dd>{profile.life_stage ?? "Not set"}</dd></div>
                <div><dt>Risk tolerance</dt><dd>{profile.risk_tolerance}</dd></div>
                <div><dt>Investment horizon</dt><dd>{profile.investment_horizon ?? "Not set"}</dd></div>
                <div><dt>Investing experience</dt><dd>{profile.investing_experience ?? "Not set"}</dd></div>
                <div><dt>Income stability</dt><dd>{profile.income_stability ?? "Not set"}</dd></div>
                <div><dt>Liquidity need</dt><dd>{profile.liquidity_needs ?? "Not set"}</dd></div>
                <div><dt>Style</dt><dd>{profile.preferred_style ?? "Not set"}</dd></div>
                <div><dt>Expert method panel</dt><dd>{profile.preferred_method_document_names.join(" + ") || "No add-on"}</dd></div>
                <div><dt>Primary priority</dt><dd>{profile.primary_financial_priority ?? "Not set"}</dd></div>
              </dl>
            </section>
            <section>
              <h3>Monthly cash flow</h3>
              <dl className="profile-summary-list">
                <div><dt>Net income</dt><dd>{formatOptionalCurrency(profile.monthly_net_income)}</dd></div>
                <div><dt>Normalized spending</dt><dd>{formatOptionalCurrency(profile.monthly_total_expenses)}</dd></div>
                <div><dt>Essential expenses</dt><dd>{formatOptionalCurrency(profile.monthly_essential_expenses)}</dd></div>
                <div><dt>Planned investing</dt><dd>{formatOptionalCurrency(profile.monthly_contribution)}</dd></div>
                <div><dt>Sector ETF satellite cap</dt><dd>{formatOptionalCurrency(profile.monthly_sector_satellite_budget)}</dd></div>
                <div><dt>Current cash savings</dt><dd>{formatOptionalCurrency(profile.current_cash_savings)}</dd></div>
              </dl>
            </section>
            <section>
              <h3>Cash and retirement goals</h3>
              <dl className="profile-summary-list">
                <div><dt>Emergency reserve</dt><dd>{savedEmergencyTarget > 0
                  ? `${formatCurrencyPrecise(savedEmergencyTarget)} needed within ${formatMonthCount(profile.emergency_fund_build_months)}`
                  : "Not included"}</dd></div>
                <div><dt>Short-term goals</dt><dd>{profile.cash_goals.length > 0
                  ? profile.cash_goals.map((goal) => (
                      `${cashGoalLabel(goal.goal_type)}: ${formatOptionalCurrency(goal.target_amount)}`
                      + ` within ${goal.months_until_needed === null ? "an unspecified deadline" : formatMonthCount(goal.months_until_needed)} (${goal.priority})`
                    )).join("; ")
                  : "None selected"}</dd></div>
                <div><dt>Education</dt><dd>{profile.education_plan === "none"
                  ? "No education cash goal"
                  : `${profile.education_plan}, ${formatOptionalCurrency(profile.education_target_amount)} by ${profile.education_target_year ?? "unspecified"}`}</dd></div>
                <div><dt>Retirement timing</dt><dd>{profile.current_age !== null && profile.planned_retirement_age !== null
                  ? `Current age ${profile.current_age}; planned retirement ${profile.planned_retirement_age}`
                  : "Not fully set"}</dd></div>
                <div><dt>Retirement planning horizon</dt><dd>{profile.planned_retirement_age !== null
                  ? `Through age ${profile.retirement_planning_age}; ${profile.retirement_planning_age - profile.planned_retirement_age} years after planned retirement`
                  : `Through age ${profile.retirement_planning_age}; add a retirement age to calculate the period`}</dd></div>
                <div><dt>Desired retirement spending</dt><dd>{profile.retirement_monthly_spending === null
                  ? `Uses essential expenses: ${formatOptionalCurrency(profile.monthly_essential_expenses)} / month`
                  : `${formatCurrencyPrecise(profile.retirement_monthly_spending)} / month`}</dd></div>
                <div><dt>Reliable retirement income</dt><dd>{profile.retirement_monthly_income === null
                  ? "$0 assumed until entered"
                  : `${formatCurrencyPrecise(profile.retirement_monthly_income)} / month`}</dd></div>
                <div><dt>Retirement savings counted</dt><dd>{profile.retirement_current_savings === null
                  ? "Uses uploaded investment portfolio"
                  : formatCurrencyPrecise(profile.retirement_current_savings)}</dd></div>
                <div><dt>Retirement account tax treatment</dt><dd>{retirementAccountLabel(profile.retirement_account_type)}{profile.retirement_account_type === "mixed" && profile.retirement_taxable_withdrawal_share !== null ? `; ${formatPercent(profile.retirement_taxable_withdrawal_share)} expected from pre-tax accounts` : ""}</dd></div>
                <div><dt>Inflation / annual return</dt><dd>{formatPercent(profile.retirement_inflation_rate)} / {formatPercent(profile.retirement_annual_return)}</dd></div>
                <div><dt>Tax assumptions</dt><dd>{profile.retirement_income_taxable ? "Other income taxable" : "Other income not taxable"}; retirement rate {profile.retirement_tax_rate === null ? "not set" : formatPercent(profile.retirement_tax_rate)}</dd></div>
              </dl>
            </section>
            <section>
              <h3>Investment policy</h3>
              <ul className="allocation-list compact-allocation-list">
                {Object.entries(profile.target_allocation).map(([assetClass, weight]) => (
                  <li key={assetClass}><span>{assetClass}</span><strong>{formatPercent(weight)}</strong></li>
                ))}
              </ul>
              <p className="section-note">
                Rebalance at {formatPercent(profile.rebalance_threshold)} drift using
                {profile.rebalance_preference === "contributions_first"
                  ? " new contributions first"
                  : " direct target trades"}.
              </p>
            </section>
          </div>
            </>
          ) : (
            <div className="saved-profile-empty">
              <strong>No active saved Profile</strong>
              <span>
                The form now shows example defaults. Review and save them before Portfolio
                uses them for allocation or rebalancing calculations.
              </span>
            </div>
          )}
        </aside>
    </div>
  );
}

function RunsWorkspace({
  dashboard,
  detail,
  detailState,
  modelOptions,
  runsState,
  onRefresh,
  onSelectRun
}: {
  dashboard: RunsDashboardResponse | null;
  detail: RunDetailResponse | null;
  detailState: RequestState;
  modelOptions: ChatModelOption[];
  runsState: RequestState;
  onRefresh: (offset?: number) => Promise<void>;
  onSelectRun: (runId: number) => Promise<void>;
}) {
  const candidateAuditPreviewLimit = 10;
  const kafkaEventPageSize = 10;
  const [refreshing, setRefreshing] = useState(false);
  const [providerImportState, setProviderImportState] = useState<RequestState>({ status: "idle" });
  const [providerImportInputKey, setProviderImportInputKey] = useState(0);
  const [providerBalanceState, setProviderBalanceState] = useState<RequestState>({ status: "idle" });
  const [refreshingProviderBalances, setRefreshingProviderBalances] = useState(false);
  const [showAllCandidateAudit, setShowAllCandidateAudit] = useState(false);
  const [kafkaEventPage, setKafkaEventPage] = useState(0);
  const [kafkaSortKey, setKafkaSortKey] = useState<KafkaSortKey>("processed_at");
  const [kafkaSortDirection, setKafkaSortDirection] = useState<SortDirection>("desc");
  const candidateAuditRows = detail?.decision_trace?.candidate_outcomes ?? [];
  const visibleCandidateAuditRows = showAllCandidateAudit
    ? candidateAuditRows
    : candidateAuditRows.slice(0, candidateAuditPreviewLimit);
  const visibleCandidateAuditGroups = groupCandidateAuditOutcomes(visibleCandidateAuditRows);
  const retainedUsage = dashboard?.retained_run_usage ?? {
    call_count: dashboard?.model_call_count ?? 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: dashboard?.total_tokens ?? 0,
    total_estimated_cost_usd: dashboard?.total_estimated_cost_usd ?? 0,
    first_recorded_at: null,
    last_recorded_at: null
  };
  const historicalUsage = dashboard?.historical_api_usage ?? retainedUsage;
  const historicalModelBreakdown = dashboard?.historical_model_breakdown ?? dashboard?.model_breakdown ?? [];
  const providerBillingSnapshots = dashboard?.provider_billing_snapshots ?? [];
  const providerAccountSnapshots = dashboard?.provider_account_snapshots ?? [];
  const eventPipeline = dashboard?.event_pipeline ?? null;
  const sortedKafkaEvents = [...(eventPipeline?.recent_events ?? [])].sort((left, right) => {
    const primary = kafkaSortKey === "processed_at"
      ? Date.parse(left.processed_at) - Date.parse(right.processed_at)
      : left.event_type.localeCompare(right.event_type);
    if (primary !== 0) {
      return kafkaSortDirection === "asc" ? primary : -primary;
    }
    return Date.parse(right.processed_at) - Date.parse(left.processed_at);
  });
  const kafkaEventPageCount = Math.max(
    1,
    Math.ceil(sortedKafkaEvents.length / kafkaEventPageSize)
  );
  const kafkaEventPageStart = kafkaEventPage * kafkaEventPageSize;
  const visibleKafkaEvents = sortedKafkaEvents.slice(
    kafkaEventPageStart,
    kafkaEventPageStart + kafkaEventPageSize
  );

  useEffect(() => {
    setShowAllCandidateAudit(false);
  }, [detail?.run.id]);

  useEffect(() => {
    setKafkaEventPage((current) => Math.min(current, kafkaEventPageCount - 1));
  }, [kafkaEventPageCount]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh(dashboard?.offset ?? 0);
    } finally {
      setRefreshing(false);
    }
  };

  const importDeepSeekUsage = async (file: File) => {
    setProviderImportState({ status: "loading", message: "Importing official DeepSeek usage export" });
    try {
      const response = await fetch(`${apiBaseUrl}/runs/provider-billing-snapshots/import/deepseek`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Argus-Filename": file.name
        },
        body: file
      });
      const payload = (await response.json()) as ProviderBillingSnapshot | { detail?: unknown };
      if (!response.ok) {
        const detail = "detail" in payload ? formatApiDetail(payload.detail) : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      setProviderImportState({
        status: "success",
        message: "DeepSeek usage export imported. Re-importing the same file will not duplicate it."
      });
      setProviderImportInputKey((current) => current + 1);
      await onRefresh(dashboard?.offset ?? 0);
    } catch (error) {
      setProviderImportState({
        status: "error",
        message: error instanceof Error ? error.message : "Provider usage import failed."
      });
    }
  };

  const refreshProviderBalances = async () => {
    setRefreshingProviderBalances(true);
    setProviderBalanceState({ status: "loading", message: "Refreshing configured provider balances" });
    try {
      const payload = await fetchJson<ProviderBalanceRefreshResponse>(
        "/runs/provider-account-snapshots/refresh",
        { method: "POST" }
      );
      const failed = payload.results.filter((item) => item.status === "failed");
      const notConfigured = payload.results.filter((item) => item.status === "not_configured");
      const updated = payload.results.filter((item) => item.status === "updated");
      const updatedNames = updated.map((item) => formatProviderName(item.provider)).join(", ");
      const failureDetail = failed
        .map((item) => `${formatProviderName(item.provider)} failed: ${item.message}`)
        .join(" · ");
      const missingNames = notConfigured
        .map((item) => formatProviderName(item.provider))
        .join(", ");
      const exaBoundary = "Exa was not queried: its usage API requires separate team-management credentials and reports cost, not remaining balance.";
      if (payload.updated_count === 0) {
        const detail = [
          failureDetail,
          missingNames ? `Not configured: ${missingNames}.` : "",
          exaBoundary
        ].filter(Boolean).join(" ");
        setProviderBalanceState({
          status: "error",
          message: detail || "No configured provider balance could be refreshed."
        });
      } else {
        const details = [
          failureDetail ? `${failureDetail}. The previous snapshot was kept.` : "",
          missingNames ? `Not configured: ${missingNames}.` : "",
          exaBoundary
        ].filter(Boolean).join(" ");
        setProviderBalanceState({
          status: "success",
          message: `Updated: ${updatedNames}. ${details}`
        });
      }
      await onRefresh(dashboard?.offset ?? 0);
    } catch (error) {
      setProviderBalanceState({
        status: "error",
        message: error instanceof Error ? error.message : "Provider balance refresh failed."
      });
    } finally {
      setRefreshingProviderBalances(false);
    }
  };

  const updateKafkaSort = (key: KafkaSortKey) => {
    setKafkaEventPage(0);
    if (key === kafkaSortKey) {
      setKafkaSortDirection((current) => current === "asc" ? "desc" : "asc");
      return;
    }
    setKafkaSortKey(key);
    setKafkaSortDirection(key === "processed_at" ? "desc" : "asc");
  };

  const kafkaSortIndicator = (key: KafkaSortKey) => {
    if (key !== kafkaSortKey) {
      return "↕";
    }
    return kafkaSortDirection === "asc" ? "↑" : "↓";
  };

  return (
    <div className="research-workspace">
      <section className="portfolio-block" aria-label="Runs and cost summary">
        <div className="answer-header">
          <h2>Runs and Cost</h2>
          <div className="heading-actions">
            <button
              className="icon-button"
              type="button"
              onClick={refresh}
              aria-label="Refresh runs"
            >
              <RefreshCw className={refreshing ? "spin" : ""} aria-hidden="true" />
            </button>
          </div>
        </div>
        <RequestStatus state={runsState} />
        <div className="runs-scope-note">
          <strong>Three cost scopes · 三种成本口径</strong>
          <p>
            A Run is one saved top-level workflow. The Token totals below count external answer-model
            API usage only. Retained Run usage is deletable debugging telemetry; Historical API usage
            is the independent append-only ledger and does not decrease when a Run or Evidence source
            is removed.
          </p>
          <p>
            Provider actual billing is the final source of truth. Argus never treats its estimate
            as an invoice; provider exports may be imported as separate reconciliation snapshots.
          </p>
        </div>
        <div className="usage-layer-grid">
          <section className="usage-layer-card retained" aria-label="Retained Run usage">
            <span>Retained Run usage · 当前保留记录</span>
            <strong>{retainedUsage.total_tokens.toLocaleString()} tokens</strong>
            <small>
              {retainedUsage.call_count} external model request(s) · {formatCost(
                retainedUsage.total_estimated_cost_usd
              )} estimated · may decrease when Runs are deleted
            </small>
          </section>
          <section className="usage-layer-card historical" aria-label="Historical API usage">
            <span>Historical API usage · 历史累计用量</span>
            <strong>{historicalUsage.total_tokens.toLocaleString()} tokens</strong>
            <small>
              {historicalUsage.call_count} external model request(s) · {formatCost(
                historicalUsage.total_estimated_cost_usd
              )} estimated · survives Run and Evidence deletion
            </small>
          </section>
          <section className="usage-layer-card provider" aria-label="Provider actual billing">
            <span>Provider actual billing · 供应商实际账单</span>
            {providerBillingSnapshots.length > 0 ? (
              <>
                <strong>{providerBillingSnapshots.length} official cost snapshot(s)</strong>
                <small>Provider-reported charges below are authoritative for their stated periods.</small>
              </>
            ) : (
              <>
                <strong>Not imported</strong>
                <small>Check each provider dashboard or import a normalized billing snapshot.</small>
              </>
            )}
          </section>
        </div>
        {dashboard?.historical_usage_scope_note && (
          <p className="usage-scope-warning">{dashboard.historical_usage_scope_note}</p>
        )}
        <div className="cost-formula" aria-label="Model API cost formula">
          <strong>External model Token-cost formula</strong>
          <code>(input tokens × input price / 1M) + (output tokens × output price / 1M)</code>
          <span>
            Local deterministic processing is excluded. Exa is a search tool billed by request,
            not by input/output Token. Provider bills and credits remain the source of truth.
          </span>
        </div>
        <div className="portfolio-grid">
          <div className="metric-card">
            <span>Total retained Runs</span>
            <strong>{dashboard?.total_runs ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Retained tool calls</span>
            <strong>{dashboard?.tool_call_count ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Non-complete runs</span>
            <strong>{dashboard?.failed_runs ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="portfolio-block event-pipeline-block" aria-label="Kafka event pipeline">
        <div className="answer-header event-pipeline-header">
          <div>
            <h2>Event pipeline · Kafka 事件流水</h2>
            <p className="section-note">
              Current path: the backend sends a small completed or failed notice after a Research
              Run ends. Kafka holds that notice until the audit consumer records it, so the
              Research request does not wait for audit work and a temporary consumer outage does
              not lose the notice.
            </p>
          </div>
          <span className={`status-chip ${eventPipeline?.consumer_status === "running" ? "feasible" : eventPipeline?.consumer_status === "disabled" ? "neutral" : "warning"}`}>
            {formatStatus(eventPipeline?.consumer_status ?? "loading")}
          </span>
        </div>
        <div className="runs-scope-note event-pipeline-note">
          <strong>Why Kafka is kept — and its limit · 为什么保留 Kafka，以及它的边界</strong>
          <p>
            Think of Kafka as an internal mailroom: the API drops off a small notice and can finish,
            while the background consumer picks it up later. If the consumer restarts, the notice
            waits; if the same notice arrives twice, Argus records it only once. Without Kafka,
            answers still work, but audit or future notification jobs must run inside the API or
            repeatedly check PostgreSQL for new Runs.
          </p>
          <p>
            Kafka is not required to generate today's answer. Today Argus has one business sender
            and one audit receiver, so a database worker could be simpler. Argus keeps only this
            narrow path to verify delivery, catch-up, duplicate protection, retry, bad-message
            isolation, and health monitoring. It should expand only when another independent
            receiver, higher event volume, or a real replay need appears.
          </p>
        </div>
        <div className="compact-metric-grid event-pipeline-metrics">
          <div className="metric-card">
            <span>Transport</span>
            <strong>{eventPipeline?.configured ? "Kafka" : "Not configured"}</strong>
            <small>{eventPipeline?.consumer_group ?? "argus-audit-metrics-v1"}</small>
          </div>
          <div className="metric-card">
            <span>Implemented topology</span>
            <strong>1 business producer → 1 consumer</strong>
            <small>Backend API → one audit/metrics group · two terminal event types</small>
          </div>
          <div className="metric-card">
            <span>Completed workflow events</span>
            <strong>{eventPipeline?.completed_count ?? 0}</strong>
            <small>
              {eventPipeline?.answer_generated_count ?? 0} answer(s) · {eventPipeline?.safe_stop_count ?? 0} safe stop(s)
            </small>
          </div>
          <div className={`metric-card ${(eventPipeline?.failed_count ?? 0) > 0 ? "metric-warning" : ""}`}>
            <span>Failed model events</span>
            <strong>{eventPipeline?.failed_count ?? 0}</strong>
            <small>Timeout, authentication, quota, or provider failure</small>
          </div>
          <div className="metric-card">
            <span>Duplicates ignored</span>
            <strong>{eventPipeline?.duplicate_count ?? 0}</strong>
            <small>Repeated event IDs did not create duplicate records</small>
          </div>
          <div className={`metric-card ${(eventPipeline?.dlq_count ?? 0) > 0 ? "metric-warning" : ""}`}>
            <span>DLQ</span>
            <strong>{eventPipeline?.dlq_count ?? 0}</strong>
            <small>Invalid or exhausted events isolated for review</small>
          </div>
        </div>
        {eventPipeline?.last_heartbeat_at ? (
          <p className="section-note">
            Consumer heartbeat: {formatTimestamp(eventPipeline.last_heartbeat_at)}
            {eventPipeline.last_error_code ? ` · last error: ${eventPipeline.last_error_code}` : ""}
          </p>
        ) : (
          <p className="section-note">
            Consumer heartbeat: {eventPipeline?.configured
              ? "waiting for the consumer's first health signal"
              : "unavailable because this backend was started without Kafka configuration"}
          </p>
        )}
        {eventPipeline && eventPipeline.recent_events.length > 0 ? (
          <div className="table-wrap">
            <table className="positions-table event-pipeline-table">
              <thead>
                <tr>
                  <th aria-sort={kafkaSortKey === "event_type" ? (kafkaSortDirection === "asc" ? "ascending" : "descending") : "none"}>
                    <button
                      className="table-sort-button"
                      type="button"
                      onClick={() => updateKafkaSort("event_type")}
                    >
                      Event type <span aria-hidden="true">{kafkaSortIndicator("event_type")}</span>
                    </button>
                  </th>
                  <th>Run ID</th>
                  <th>Result</th>
                  <th>Kafka position</th>
                  <th aria-sort={kafkaSortKey === "processed_at" ? (kafkaSortDirection === "asc" ? "ascending" : "descending") : "none"}>
                    <button
                      className="table-sort-button"
                      type="button"
                      onClick={() => updateKafkaSort("processed_at")}
                    >
                      Processed <span aria-hidden="true">{kafkaSortIndicator("processed_at")}</span>
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleKafkaEvents.map((event) => (
                  <tr key={event.event_id}>
                    <td>
                      <strong>{event.event_type}</strong>
                      <span title={event.event_id}>ID {event.event_id.slice(0, 12)}…</span>
                    </td>
                    <td>{event.aggregate_id}</td>
                    <td>
                      <span className={`status-chip ${event.status === "processed" ? "feasible" : "warning"}`}>
                        {formatStatus(event.status)}
                      </span>
                      <span>
                        {event.attempt_count} attempt(s) · {event.duplicate_count} duplicate(s)
                      </span>
                      {event.event_type === "agent.run.failed.v1" ? (
                        <>
                          <span>Model call failed · {formatModelFailureCode(event.failure_code)}</span>
                          {(event.provider || event.model) && (
                            <span>{[event.provider, event.model].filter(Boolean).join(" / ")}</span>
                          )}
                        </>
                      ) : event.answer_generated !== null && (
                        <span>
                          {event.answer_generated
                            ? "ANSWER GENERATED"
                            : "NO ANSWER · SAFE STOP"}
                          {event.execution_outcome
                            ? ` · ${formatExecutionOutcome(event.execution_outcome)}`
                            : ""}
                        </span>
                      )}
                      {event.run_status && <span>Run status: {formatStatus(event.run_status)}</span>}
                      {event.error_code && event.event_type !== "agent.run.failed.v1" && <span>{event.error_code}</span>}
                    </td>
                    <td>
                      {event.partition !== null && event.message_offset !== null
                        ? `partition ${event.partition} · offset ${event.message_offset}`
                        : "Position unavailable"}
                    </td>
                    <td>{formatTimestamp(event.processed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="runs-pagination" aria-label="Kafka event pagination">
              <button
                type="button"
                disabled={kafkaEventPage === 0}
                onClick={() => setKafkaEventPage((current) => Math.max(0, current - 1))}
              >
                Previous
              </button>
              <span>
                Showing {kafkaEventPageStart + 1}–{kafkaEventPageStart + visibleKafkaEvents.length}
                {` of ${sortedKafkaEvents.length}`}
              </span>
              <button
                type="button"
                disabled={kafkaEventPage >= kafkaEventPageCount - 1}
                onClick={() => setKafkaEventPage((current) => Math.min(kafkaEventPageCount - 1, current + 1))}
              >
                Next
              </button>
            </div>
          </div>
        ) : (
          <p className="empty-state">
            {eventPipeline?.configured
              ? "Kafka is configured; no completed or failed Run event has been consumed yet."
              : "Kafka is optional and currently disabled. Runs still save normally in PostgreSQL."}
          </p>
        )}
      </section>

      <section className="portfolio-block" aria-label="Historical API usage by model">
        <h2>Historical API usage by model</h2>
        <p className="section-note">
          These totals come from the independent API Usage Ledger, not the deletable Run list.
          A recorded price is the call-time price snapshot. Legacy migrated rows may only have
          today's configured rate available as a reference; that reference never rewrites the
          stored historical cost. Local deterministic processing and Exa searches are not model
          Token usage and therefore do not appear in this table.
        </p>
        {historicalModelBreakdown.length > 0 ? (
          <div className="table-wrap">
            <table className="positions-table model-cost-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Calls</th>
                  <th>Input tokens</th>
                  <th>Output tokens</th>
                  <th>Input price / 1M</th>
                  <th>Output price / 1M</th>
                  <th>Estimated cost</th>
                </tr>
              </thead>
              <tbody>
                {historicalModelBreakdown.map((row, index) => {
                  const pricing = configuredModelPricing(modelOptions, row.provider, row.model);
                  const inputPrice = row.input_cost_per_million_usd;
                  const outputPrice = row.output_cost_per_million_usd;
                  const isLocal = row.deployment.toLowerCase() === "local";
                  return (
                    <tr key={`${row.provider}-${row.model}-${row.deployment}-${inputPrice}-${outputPrice}-${index}`}>
                      <td><strong>{row.model}</strong><span>{row.provider} · {row.deployment}</span></td>
                      <td>{row.call_count}</td>
                      <td>{row.prompt_tokens.toLocaleString()}</td>
                      <td>{row.completion_tokens.toLocaleString()}</td>
                      <td>
                        {isLocal
                          ? "No API charge"
                          : inputPrice !== null
                          ? formatPerMillionPrice(inputPrice)
                          : pricing
                            ? `${formatPerMillionPrice(pricing.input_cost_per_million)} · current reference`
                            : "Price unavailable"}
                      </td>
                      <td>
                        {isLocal
                          ? "No API charge"
                          : outputPrice !== null
                          ? formatPerMillionPrice(outputPrice)
                          : pricing
                            ? `${formatPerMillionPrice(pricing.output_cost_per_million)} · current reference`
                            : "Price unavailable"}
                      </td>
                      <td><strong>{formatCost(row.total_estimated_cost_usd)}</strong></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">No API usage ledger entries recorded.</p>
        )}
      </section>

      <section className="portfolio-block" aria-label="Provider actual billing snapshots">
        <h2>Provider actual billing</h2>
        <p className="section-note">
          Imported provider summaries are kept separately from Argus estimates. They are not
          deleted with Runs and are not converted across currencies automatically.
        </p>
        <details className="provider-record-update">
          <summary>Update provider records · 更新供应商数据</summary>
          <div className="provider-record-grid">
            <div>
              <strong>DeepSeek actual usage</strong>
              <p>Upload the official Usage ZIP. Argus validates its structure and removes identity and API-key columns.</p>
              <input
                className="hidden-file-input"
                id="deepseek-usage-export"
                key={providerImportInputKey}
                type="file"
                accept=".zip,application/zip"
                disabled={providerImportState.status === "loading"}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    importDeepSeekUsage(file);
                  }
                }}
              />
              <label
                className={`compact-upload-trigger${providerImportState.status === "loading" ? " disabled" : ""}`}
                htmlFor="deepseek-usage-export"
              >
                {providerImportState.status === "loading"
                  ? <Loader2 className="spin" aria-hidden="true" />
                  : <Upload aria-hidden="true" />}
                <span>{providerImportState.status === "loading" ? "Importing…" : "Import DeepSeek ZIP"}</span>
              </label>
            </div>
            <div>
              <strong>Other providers</strong>
              <p>
                Argus records external model Tokens automatically. Exa search responses provide
                per-request cost rather than Token counts. Exa's historical usage API can be
                integrated separately, but it requires a Team Management service key and the target
                API Key ID; the normal Search API key is not sufficient. Kimi screenshots and
                provider dashboard totals remain manual reconciliation evidence.
              </p>
            </div>
          </div>
          <RequestStatus state={providerImportState} />
        </details>
        {providerBillingSnapshots.length > 0 ? (
          <div className="table-wrap">
            <table className="positions-table provider-billing-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Billing period</th>
                  <th>Requests</th>
                  <th>Tokens</th>
                  <th>Actual charge</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {providerBillingSnapshots.map((snapshot) => (
                  <tr key={snapshot.id}>
                    <td><strong>{snapshot.provider}</strong></td>
                    <td>{snapshot.period_start} → {snapshot.period_end}</td>
                    <td>{snapshot.request_count?.toLocaleString() ?? "Not reported"}</td>
                    <td>{snapshot.total_tokens?.toLocaleString() ?? "Not reported"}</td>
                    <td><strong>{formatProviderAmount(snapshot.actual_cost, snapshot.currency)}</strong></td>
                    <td>{snapshot.source_reference ?? "Official provider summary"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">
            No provider statement imported. The selected provider's billing console remains the
            final source of truth for charges already incurred.
          </p>
        )}
      </section>

      <section className="portfolio-block" aria-label="Provider account status">
        <div className="answer-header provider-account-header">
          <div>
            <h2>Provider balances · 更新供应商余额</h2>
            <p className="section-note">
              Refresh uses the configured providers' official balance APIs. It updates current
              balance and whether the account has funds available for API calls; it does not return
              historical charges, detailed usage, or the provider's full billing tier. Supported
              here: DeepSeek and Kimi. Exa usage requires separate team-management credentials and
              belongs under billing reconciliation, not remaining balance.
            </p>
          </div>
          <button
            className="action-button"
            type="button"
            onClick={refreshProviderBalances}
            disabled={refreshingProviderBalances}
          >
            <RefreshCw className={refreshingProviderBalances ? "spin" : ""} aria-hidden="true" />
            <span>{refreshingProviderBalances ? "Refreshing…" : "Refresh balances"}</span>
          </button>
        </div>
        <RequestStatus state={providerBalanceState} />
        <p className="section-note provider-balance-boundary-note">
          Balances are money still available, not money already spent. DeepSeek usage exports and
          provider billing consoles remain the source of truth for historical charges.
        </p>
        {providerAccountSnapshots.length > 0 ? (
          <div className="portfolio-grid">
            {providerAccountSnapshots.map((snapshot) => (
              <div className="metric-card" key={snapshot.id}>
                <span>
                  {snapshot.provider}
                  {snapshot.billing_tier ? ` · ${snapshot.billing_tier}` : ""}
                  {` · ${formatStatus(snapshot.billing_status)}`}
                </span>
                <strong>
                  {snapshot.available_balance !== null && snapshot.currency
                    ? formatProviderAmount(snapshot.available_balance, snapshot.currency)
                    : formatStatus(snapshot.billing_status)}
                </strong>
                <small>
                  {snapshot.paid_balance !== null && snapshot.currency
                    ? `Paid balance ${formatProviderAmount(snapshot.paid_balance, snapshot.currency)}`
                    : "No paid balance reported"}
                  {snapshot.promotional_balance !== null && snapshot.currency
                    ? ` · promotional ${formatProviderAmount(snapshot.promotional_balance, snapshot.currency)}`
                    : ""}
                  {` · checked ${formatTimestamp(snapshot.created_at)}`}
                </small>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">No provider balance or billing-tier status recorded.</p>
        )}
      </section>

      <section className="portfolio-block recent-runs-block" aria-label="Recent runs">
        <h2>Recent Runs</h2>
        <p className="section-note">
          Newest first. Run numbers are database IDs. They can skip after older Runs are
          deleted because database IDs are not renumbered.
        </p>
        {dashboard && dashboard.recent_runs.length > 0 ? (
          <>
            <div className="table-wrap">
              <table className="positions-table runs-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Model</th>
                  <th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.recent_runs.map((run) => (
                  <tr
                    key={run.id}
                    className={
                      detail?.run.id === run.id
                        ? "clickable-row selected-row"
                        : "clickable-row"
                    }
                    role="button"
                    tabIndex={0}
                    title={run.objective}
                    onClick={() => void onSelectRun(run.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        void onSelectRun(run.id);
                      }
                    }}
                  >
                    <td>
                      <strong>{run.id}</strong>
                    </td>
                    <td>{formatStatus(run.status)}</td>
                    <td>{run.selected_model ?? "None"}</td>
                    <td>{run.total_tokens}</td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
            <div className="runs-pagination" aria-label="Runs pagination">
              <button
                type="button"
                disabled={dashboard.offset === 0 || runsState.status === "loading"}
                onClick={() => void onRefresh(Math.max(0, dashboard.offset - dashboard.limit))}
              >
                Previous
              </button>
              <span>
                Showing {dashboard.offset + 1}–{dashboard.offset + dashboard.recent_runs.length}
                {` of ${dashboard.total_runs}`}
              </span>
              <button
                type="button"
                disabled={!dashboard.has_more || runsState.status === "loading"}
                onClick={() => void onRefresh(dashboard.offset + dashboard.limit)}
              >
                Next
              </button>
            </div>
          </>
        ) : (
          <p className="empty-state">No runs recorded yet.</p>
        )}
      </section>

      {detail && (
        <section className="portfolio-block run-detail-block" aria-label="Run details">
          <div className="answer-header">
            <h2>Run ID {detail.run.id} details</h2>
            <span className={`run-status ${detail.run.status}`}>{detail.run.status}</span>
          </div>
          <RequestStatus state={detailState} />
          <div className="trace-reason">
            <strong>Model selection</strong>
            <span>{detail.run.selection_reason ?? "No selection reason recorded."}</span>
          </div>
          {detail.decision_trace && (
            <div className="portfolio-decision-trace">
              <div className="section-heading-row">
                <div>
                  <h3>Portfolio ETF candidate audit · ETF 候选审计</h3>
                  <p className="section-note">
                    Bounded structured metadata only. Argus does not store the raw prompt,
                    full model response, full web pages, account names, dollar holdings, or API keys.
                  </p>
                </div>
                <span className={`status-chip ${detail.decision_trace.status === "complete" ? "feasible" : "warning"}`}>
                  {detail.decision_trace.status ?? "unknown"}
                </span>
              </div>
              <div className="compact-metric-grid">
                <div className="metric-card">
                  <span>Evidence snapshot ID</span>
                  <strong>{detail.decision_trace.evidence_snapshot_id || "Not reached"}</strong>
                </div>
                <div className="metric-card">
                  <span>Candidate parse</span>
                  <strong>{(detail.decision_trace.candidate_parse_status ?? "unknown").split("_").join(" ")}</strong>
                </div>
                <div className="metric-card">
                  <span>Selection / auditor</span>
                  <strong>
                    {detail.decision_trace.selection_version ?? detail.decision_trace.selection_engine ?? "unknown"}
                    {` · ${detail.decision_trace.audit_status ?? "not recorded"}`}
                  </strong>
                </div>
                <div className="metric-card">
                  <span>Accepted</span>
                  <strong>{detail.decision_trace.accepted_candidate_count ?? 0}</strong>
                </div>
                <div className="metric-card">
                  <span>Not selected</span>
                  <strong>{detail.decision_trace.rejected_candidate_count ?? 0}</strong>
                </div>
              </div>
              {detail.decision_trace.selection_engine_limitation && (
                <p className="trace-limitation">{detail.decision_trace.selection_engine_limitation}</p>
              )}
              {detail.decision_trace.failure_code && (
                <p className="trace-limitation">Failure code: {detail.decision_trace.failure_code}</p>
              )}
              {candidateAuditRows.length > 0 ? (
                <div className="candidate-audit-results">
                  <p className="section-note">
                    Showing {visibleCandidateAuditRows.length} of {candidateAuditRows.length}
                    {` candidate checks, combined into ${visibleCandidateAuditGroups.length} shared decision-reason group${visibleCandidateAuditGroups.length === 1 ? "" : "s"}. Candidates do not have separate timestamps.`}
                  </p>
                  <div className="candidate-audit-groups">
                    {visibleCandidateAuditGroups.map((group) => (
                      <section className="candidate-audit-group" key={group.key}>
                        <div className="candidate-audit-group-heading">
                          <strong>
                            {group.outcomes.length} ETF candidate{group.outcomes.length === 1 ? "" : "s"}
                            {group.outcomes.length === 1
                              ? " shares this decision"
                              : " share this decision"}
                          </strong>
                          <span className={`status-chip ${group.decision === "selected" ? "feasible" : "warning"}`}>
                            {candidateAuditDecisionLabel(group.decision)}
                          </span>
                        </div>
                        <div className="candidate-symbol-list" aria-label="ETF candidates in this reason group">
                          {group.outcomes.map((outcome) => (
                            <span key={`${outcome.index}-${outcome.symbol ?? "invalid"}`}>
                              {outcome.symbol ?? `Candidate ${outcome.index + 1}`}
                            </span>
                          ))}
                        </div>
                        <div className="candidate-shared-reasons">
                          <strong>Shared decision reasons</strong>
                          <ul>
                            {(group.validationCodes.length > 0
                              ? group.validationCodes
                              : ["accepted"]
                            ).map((code) => (
                              <li key={code}>
                                {candidateAuditReasonLabel(code, group.outcomes.length)}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <details className="candidate-audit-group-details">
                          <summary>Review individual scores and technical codes</summary>
                          <ul>
                            {group.outcomes.map((outcome) => (
                              <li key={`${outcome.index}-${outcome.symbol ?? "invalid"}-detail`}>
                                <strong>{outcome.symbol ?? `Candidate ${outcome.index + 1}`}</strong>
                                <span>
                                  Source: {outcome.selection_source} · rank: {outcome.rank ?? "not selected"}
                                  {` · score: ${outcome.total_score ?? "n/a"}`}
                                  {` · mode: ${outcome.expected_mode ?? outcome.requested_mode ?? "unavailable"}`}
                                </span>
                                {outcome.total_score !== null && (
                                  <span>
                                    Components: {Object.entries(outcome.score_components)
                                      .map(([name, value]) => `${name} ${value}`)
                                      .join(" · ") || "none"}
                                    {` · penalties: ${Object.entries(outcome.penalties)
                                      .map(([name, value]) => `${name} -${value}`)
                                      .join(" · ") || "none"}`}
                                    {outcome.market_signal_as_of
                                      ? ` · market signal as of ${outcome.market_signal_as_of}`
                                      : ""}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                          <code>{group.validationCodes.join(", ") || "accepted"}</code>
                        </details>
                      </section>
                    ))}
                  </div>
                  {candidateAuditRows.length > candidateAuditPreviewLimit && (
                    <button
                      className="candidate-audit-toggle"
                      type="button"
                      aria-expanded={showAllCandidateAudit}
                      onClick={() => setShowAllCandidateAudit((current) => !current)}
                    >
                      {showAllCandidateAudit
                        ? `Show first ${candidateAuditPreviewLimit}`
                        : `Show ${candidateAuditRows.length - candidateAuditPreviewLimit} more`}
                    </button>
                  )}
                </div>
              ) : (
                <p className="empty-state">
                  No candidate object reached structured validation for this run.
                </p>
              )}
              <small>
                Retention: latest {detail.decision_trace.retention?.role_limit ?? "configured"}
                {` Portfolio market-analysis runs or ${detail.decision_trace.retention?.max_age_days ?? "configured"} days, whichever removes a trace first · cache used: `}
                {detail.decision_trace.retention?.cache_used ? "yes" : "no"}
              </small>
            </div>
          )}
          <h3>Model Calls · AI 模型调用</h3>
          <p className="section-note">
            Each row is one recorded request to an answer or generation model. Retries and
            repair attempts appear as separate calls. The stored estimate was calculated when
            the call ran; it is not recalculated when you later select another model. Cloud
            Token counts come from provider usage metadata. Local deterministic rows, when present
            in this debugging trace, use approximate word counts and are excluded from the Token and
            cost summaries above.
          </p>
          <ul className="trace-list">
            {detail.model_calls.map((call) => {
              const pricing = configuredModelPricing(modelOptions, call.provider, call.model);
              return (
                <li key={call.id}>
                  <strong>{call.model}</strong>
                  <span>{call.provider} · {call.deployment} · {formatTimestamp(call.created_at)}</span>
                  <span>
                    Input {call.prompt_tokens.toLocaleString()} tokens
                    {` + output ${call.completion_tokens.toLocaleString()} tokens`}
                    {` = ${call.total_tokens.toLocaleString()} total`}
                  </span>
                  <span>
                    Current configured rate: {pricing
                      ? `${formatPerMillionPrice(pricing.input_cost_per_million)} input / ${formatPerMillionPrice(pricing.output_cost_per_million)} output per 1M tokens`
                      : "not available for this historical model"}
                  </span>
                  <span>Stored call-time estimate: {formatCost(call.estimated_cost_usd)}</span>
                </li>
              );
            })}
          </ul>
          <h3>Tool Calls · 工具调用</h3>
          <p className="section-note">
            These are non-model operations such as web search, evidence validation, or local
            retrieval. They do not add model tokens. A paid search provider can still have a
            separate tool cost included in the Run total.
          </p>
          {detail.tool_calls.length > 0 ? (
            <ul className="trace-list">
              {detail.tool_calls.map((call) => (
                <li key={call.id}>
                  <strong>{call.tool_name}</strong>
                  <span>{toolCallDescription(call.tool_name)}</span>
                  <span>
                    {formatStatus(call.status)} · {call.latency_ms === null
                      ? "latency not recorded"
                      : `${call.latency_ms} ms`}
                  </span>
                  <details className="trace-technical-details">
                    <summary>Technical parameters</summary>
                    <code>{compactJson(call.arguments)}</code>
                  </details>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No tool calls recorded for this run.</p>
          )}
        </section>
      )}
    </div>
  );
}

function groupCandidateAuditOutcomes(
  outcomes: MarketCandidateAudit[]
): CandidateAuditGroup[] {
  const groups = new Map<string, CandidateAuditGroup>();
  for (const outcome of outcomes) {
    const decision = outcome.accepted
      ? "selected"
      : outcome.eligible
        ? "eligible_not_selected"
        : "ineligible";
    const validationCodes = Array.from(new Set(outcome.validation_codes)).sort();
    const key = `${decision}:${validationCodes.join("|") || "accepted"}`;
    const existing = groups.get(key);
    if (existing) {
      existing.outcomes.push(outcome);
      continue;
    }
    groups.set(key, {
      key,
      decision,
      validationCodes,
      outcomes: [outcome]
    });
  }
  return Array.from(groups.values());
}

function candidateAuditDecisionLabel(decision: CandidateAuditGroup["decision"]): string {
  if (decision === "selected") {
    return "selected";
  }
  if (decision === "eligible_not_selected") {
    return "eligible · not selected";
  }
  return "ineligible";
}

function candidateAuditReasonLabel(code: string, candidateCount: number): string {
  const labels: Record<string, string> = {
    accepted: "Passed candidate validation and ranking",
    missing_expense_ratio_penalty: "Expense-ratio evidence is missing",
    missing_liquidity_evidence_penalty: "Liquidity evidence is missing",
    missing_publication_date_penalty: "Supporting evidence has no verified publication date",
    no_candidate_specific_accepted_evidence: `No accepted evidence directly supports ${candidateCount === 1 ? "this ETF" : "these ETFs"}`,
    no_comparable_peer_specific_evidence: "No accepted peer-comparison evidence is available",
    score_below_minimum: "The final deterministic score is below the selection minimum"
  };
  return labels[code] ?? code.split("_").join(" ");
}

function ResearchLibraryPanel({
  activeDocumentId,
  activeMethodDocumentIds,
  documents,
  methodDocuments,
  onDeleteAllDocuments,
  onDeleteDocument,
  onDeleteMethodDocument,
  onSelectDocument,
  onSelectMethodDocument
}: {
  activeDocumentId: number | null;
  activeMethodDocumentIds: number[];
  documents: DocumentSummary[];
  methodDocuments: MethodDocumentResponse[];
  onDeleteAllDocuments: () => Promise<void>;
  onDeleteDocument: (document: DocumentSummary) => Promise<void>;
  onDeleteMethodDocument: (documentId: number) => Promise<void>;
  onSelectDocument: (documentId: number | null) => void;
  onSelectMethodDocument: (documentIds: number[]) => void;
}) {
  const [pendingDeleteKey, setPendingDeleteKey] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);

  const confirmEvidenceDelete = async (document: DocumentSummary) => {
    const key = `evidence-${document.id}`;
    setDeletingKey(key);
    try {
      await onDeleteDocument(document);
      setPendingDeleteKey(null);
    } finally {
      setDeletingKey(null);
    }
  };

  const confirmAllEvidenceDelete = async () => {
    const key = "all-evidence";
    setDeletingKey(key);
    try {
      await onDeleteAllDocuments();
      setPendingDeleteKey(null);
    } finally {
      setDeletingKey(null);
    }
  };

  const confirmMethodDelete = async (document: MethodDocumentResponse) => {
    const key = `method-${document.id}`;
    setDeletingKey(key);
    try {
      await onDeleteMethodDocument(document.id);
      setPendingDeleteKey(null);
    } finally {
      setDeletingKey(null);
    }
  };

  return (
    <section className="status-panel documents-panel" aria-label="Uploaded research items">
      <div className="panel-heading">
        <h2>Uploaded research items</h2>
        {documents.length > 0 && (
          <div className="heading-actions">
            <button
              className="clear-evidence-button"
              type="button"
              onClick={() => setPendingDeleteKey("all-evidence")}
            >
              <Trash2 aria-hidden="true" />
              Clear evidence
            </button>
          </div>
        )}
      </div>
      <p className="field-note">
        {documents.length > 0
          ? "Evidence supplies searchable facts and citations. Expert Method Packs supply analysis instructions. Clearing evidence does not delete methods."
          : "No evidence sources are currently uploaded. Expert Method Packs supply analysis instructions and are managed separately."}
      </p>
      {documents.length > 0 && pendingDeleteKey === "all-evidence" && (
        <div className="document-delete-confirmation" role="group" aria-label="Confirm all evidence deletion">
          <span>
            {`Clear ${documents.length} evidence source(s)? This permanently removes their uploaded files, search index, and related Runs and Reports. Expert Method Packs, Profile, and Portfolio stay.`}
          </span>
          <div>
            <button
              type="button"
              disabled={deletingKey === "all-evidence"}
              onClick={() => setPendingDeleteKey(null)}
            >
              Keep files
            </button>
            <button
              className="confirm-delete-button"
              type="button"
              disabled={deletingKey === "all-evidence"}
              onClick={() => void confirmAllEvidenceDelete()}
            >
              {deletingKey === "all-evidence"
                ? "Clearing…"
                : "Clear evidence"}
            </button>
          </div>
        </div>
      )}
      {documents.length > 0 && (
        <button
          className={`library-all-sources${activeDocumentId === null ? " active" : ""}`}
          type="button"
          onClick={() => onSelectDocument(null)}
        >
          <span>Evidence search scope</span>
          <strong>All {documents.length} indexed source(s)</strong>
        </button>
      )}
      {documents.length > 0 || methodDocuments.length > 0 ? (
        <ul className="document-list research-library-list">
          {documents.length > 0 && (
            <li className="library-section-label">
              <strong>Evidence sources · {documents.length}</strong>
              <span>Facts and citations · removed by Clear evidence</span>
            </li>
          )}
          {documents.map((document) => (
            <li
              key={`evidence-${document.id}`}
              className={document.id === activeDocumentId ? "active-document" : ""}
            >
              <div className="document-row">
                <button
                  className="document-scope-button"
                  type="button"
                  onClick={() => onSelectDocument(document.id)}
                >
                  <strong>{documentDisplayName(document)}</strong>
                  <span>
                    <span className="library-type-badge evidence">Evidence</span>
                    {document.source_type}{document.id === activeDocumentId ? " · selected search scope" : ""}
                  </span>
                </button>
                <button
                  className="document-delete-button"
                  type="button"
                  aria-label={`Delete ${documentDisplayName(document)} from research index`}
                  title="Delete from research index"
                  onClick={() => setPendingDeleteKey(`evidence-${document.id}`)}
                >
                  <Trash2 aria-hidden="true" />
                </button>
              </div>
              {pendingDeleteKey === `evidence-${document.id}` && (
                <div className="document-delete-confirmation" role="group" aria-label="Confirm source deletion">
                  <span>
                    Permanently remove this upload, its evidence, chunks, embeddings,
                    and every historical Run or Report that used it?
                  </span>
                  <div>
                    <button
                      type="button"
                      disabled={deletingKey === `evidence-${document.id}`}
                      onClick={() => setPendingDeleteKey(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="confirm-delete-button"
                      type="button"
                      disabled={deletingKey === `evidence-${document.id}`}
                      onClick={() => void confirmEvidenceDelete(document)}
                    >
                      {deletingKey === `evidence-${document.id}` ? "Deleting…" : "Confirm delete"}
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
          {methodDocuments.length > 0 && (
            <li className="library-section-label method-section-label">
              <strong>Expert Method Packs · {methodDocuments.length}</strong>
              <span>Analysis instructions, not evidence · delete individually</span>
            </li>
          )}
          {methodDocuments.map((document) => (
            <li
              key={`method-${document.id}`}
              className={activeMethodDocumentIds.includes(document.id) ? "active-method" : ""}
            >
              <div className="document-row">
                <button
                  className="document-scope-button"
                  type="button"
                  onClick={() => {
                    if (activeMethodDocumentIds.includes(document.id)) {
                      onSelectMethodDocument(activeMethodDocumentIds.filter(
                        (value) => value !== document.id
                      ));
                    } else if (activeMethodDocumentIds.length < MAX_METHOD_PANEL_DOCUMENTS) {
                      onSelectMethodDocument([...activeMethodDocumentIds, document.id]);
                    }
                  }}
                >
                  <strong>{cleanUploadedFileName(document.file_name || document.name)}</strong>
                  <span>
                    <span className="library-type-badge method">Method add-on</span>
                    {document.source_type} · {document.checklist_items.length} checks
                    {activeMethodDocumentIds.includes(document.id)
                      ? " · active panel member"
                      : activeMethodDocumentIds.length >= MAX_METHOD_PANEL_DOCUMENTS
                        ? " · panel limit reached"
                        : " · click to add"}
                  </span>
                </button>
                <button
                  className="document-delete-button"
                  type="button"
                  aria-label={`Delete ${document.name} method add-on`}
                  title="Permanently delete method add-on"
                  onClick={() => setPendingDeleteKey(`method-${document.id}`)}
                >
                  <Trash2 aria-hidden="true" />
                </button>
              </div>
              {pendingDeleteKey === `method-${document.id}` && (
                <div className="document-delete-confirmation" role="group" aria-label="Confirm method deletion">
                  <span>
                    Permanently remove this compiled method add-on and every historical
                    Run or Report that used it?
                  </span>
                  <div>
                    <button
                      type="button"
                      disabled={deletingKey === `method-${document.id}`}
                      onClick={() => setPendingDeleteKey(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="confirm-delete-button"
                      type="button"
                      disabled={deletingKey === `method-${document.id}`}
                      onClick={() => void confirmMethodDelete(document)}
                    >
                      {deletingKey === `method-${document.id}` ? "Deleting…" : "Confirm delete"}
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">No evidence or method add-ons uploaded.</p>
      )}
    </section>
  );
}

function PlaceholderPanel({
  activeIcon: ActiveIcon,
  label
}: {
  activeIcon: typeof FileSearch;
  label: string;
}) {
  return (
    <div className="placeholder-panel">
      <ActiveIcon aria-hidden="true" />
      <h2>{label}</h2>
      <p>Not implemented in the current local slice.</p>
    </div>
  );
}

function RequestStatus({ state }: { state: RequestState }) {
  if (state.status === "idle") {
    return null;
  }
  return (
    <div className={`request-status ${state.status}`}>
      {state.status === "error" && <AlertCircle aria-hidden="true" />}
      {state.status === "loading" && <Loader2 className="spin" aria-hidden="true" />}
      <span>{state.message}</span>
    </div>
  );
}

type ResearchAnswerBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

function ResearchAnswer({ value }: { value: string }) {
  const blocks = researchAnswerBlocks(value);
  return (
    <div className="answer-text research-answer">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return <h3 key={`${block.kind}-${index}`}>{block.text}</h3>;
        }
        if (block.kind === "list") {
          return (
            <ul key={`${block.kind}-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${itemIndex}-${item}`}>{item}</li>
              ))}
            </ul>
          );
        }
        return <p key={`${block.kind}-${index}`}>{block.text}</p>;
      })}
    </div>
  );
}

function researchAnswerBlocks(value: string): ResearchAnswerBlock[] {
  const normalized = value.replace(/\r\n/g, "\n").trim();
  const sourceLines = normalized.split("\n").map((line) => line.trim()).filter(Boolean);
  if (sourceLines.length === 1 && normalized.length >= 360) {
    const protectedAnswer = normalized.replace(
      /\b(?:U\.S|U\.K|e\.g|i\.e)\./gi,
      (match) => match.split(".").join("∯")
    );
    const sentences = (protectedAnswer.match(/[^.!?]+(?:[.!?]+|$)/g) ?? [protectedAnswer])
      .map((sentence) => sentence.split("∯").join("."));
    return sentences
      .map((sentence) => cleanModelMarkdown(sentence).trim())
      .filter(Boolean)
      .map((text) => ({ kind: "paragraph" as const, text }));
  }

  const blocks: ResearchAnswerBlock[] = [];
  let listItems: string[] = [];
  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push({ kind: "list", items: listItems });
      listItems = [];
    }
  };
  for (const line of sourceLines) {
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      flushList();
      blocks.push({ kind: "heading", text: cleanModelMarkdown(heading[1]) });
      continue;
    }
    const bullet = line.match(/^(?:-|\*|\d+[.)])\s+(.+)$/);
    if (bullet) {
      listItems.push(cleanModelMarkdown(bullet[1]));
      continue;
    }
    flushList();
    blocks.push({ kind: "paragraph", text: cleanModelMarkdown(line) });
  }
  flushList();
  return blocks;
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...init.headers },
    ...init
  });
  const payload = (await response.json()) as T | {
    detail?: string | { code?: string; message?: string; run_id?: number | null };
  };
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    let code: string | null = null;
    let runId: number | null = null;
    if (typeof payload === "object" && payload !== null && "detail" in payload) {
      detail = formatApiDetail(payload.detail);
      if (payload.detail && typeof payload.detail === "object" && !Array.isArray(payload.detail)) {
        code = typeof payload.detail.code === "string" ? payload.detail.code : null;
        runId = typeof payload.detail.run_id === "number" ? payload.detail.run_id : null;
      }
    }
    throw new ApiRequestError(detail, code, runId);
  }
  return payload as T;
}

function humanizeErrorCode(code: string | null): string {
  if (code === "provider_timeout") {
    return "The selected model exceeded its response-time limit.";
  }
  if (code === "provider_quota_exhausted") {
    return "The selected model rejected the request because of quota or rate limits.";
  }
  if (code === "provider_authentication_failed") {
    return "The selected model rejected its API credentials.";
  }
  return code ? code.split("_").join(" ") : "model provider failure";
}

async function fetchNoContent(path: string, init: RequestInit = {}): Promise<void> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...init.headers },
    ...init
  });
  if (response.ok) {
    return;
  }
  let detail = `HTTP ${response.status}`;
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) {
      detail = String(payload.detail);
    }
  } catch {
    // Keep the HTTP status when the server does not return JSON.
  }
  throw new Error(detail);
}

function profilePayload(form: ProfileFormState) {
  if (form.emergencyFundEnabled && !form.emergencyFundTargetAmount.trim()) {
    throw new Error("Enter the emergency cash amount, or turn off the emergency-fund goal.");
  }
  if (form.emergencyFundEnabled && !form.emergencyFundBuildMonths.trim()) {
    throw new Error("Enter how many months you have to build the emergency cash reserve.");
  }
  const target_allocation: Record<string, number> = {};
  const targets = [
    ["Equity", form.equityTarget],
    ["Bond", form.bondTarget],
    ["Commodity / Gold", form.commodityTarget],
    ["International Equity", form.internationalEquityTarget],
    ["Alternatives", form.alternativesTarget]
  ];
  for (const [assetClass, rawValue] of targets) {
    const value = rawValue.trim();
    if (value) {
      target_allocation[assetClass] = Number(value) / 100;
    }
  }
  return {
    risk_tolerance: form.riskTolerance,
    life_stage: emptyToNull(form.lifeStage),
    investment_horizon: emptyToNull(form.investmentHorizon),
    investing_experience: emptyToNull(form.investingExperience),
    income_stability: emptyToNull(form.incomeStability),
    liquidity_needs: emptyToNull(form.liquidityNeeds),
    preferred_style: emptyToNull(form.preferredStyle),
    preferred_method_document_ids: form.preferredMethodDocumentIds,
    target_allocation,
    monthly_net_income: optionalMoney(form.monthlyNetIncome, "Monthly net cash income"),
    monthly_contribution: optionalMoney(form.monthlyContribution, "Planned monthly investment"),
    monthly_sector_satellite_budget: optionalMoney(
      form.monthlySectorSatelliteBudget,
      "Optional monthly sector satellite budget"
    ),
    monthly_total_expenses: optionalMoney(form.monthlyTotalExpenses, "Normalized monthly spending"),
    primary_financial_priority: emptyToNull(form.primaryFinancialPriority),
    current_age: optionalNumber(form.currentAge),
    planned_retirement_age: optionalNumber(form.plannedRetirementAge),
    retirement_planning_age: Number(form.retirementPlanningAge) || 100,
    retirement_monthly_spending: optionalMoney(
      form.retirementMonthlySpending,
      "Desired monthly retirement spending"
    ),
    retirement_monthly_income: optionalMoney(
      form.retirementMonthlyIncome,
      "Expected reliable monthly retirement income"
    ),
    retirement_current_savings: optionalMoney(
      form.retirementCurrentSavings,
      "Retirement savings already accumulated"
    ),
    retirement_income_taxable: form.retirementIncomeTaxable,
    retirement_inflation_rate: Number(form.retirementInflationRate) / 100,
    retirement_current_tax_rate: optionalPercent(
      form.retirementCurrentTaxRate,
      "Current marginal tax rate"
    ),
    retirement_tax_rate: optionalPercent(
      form.retirementTaxRate,
      "Retirement marginal tax rate"
    ),
    retirement_annual_return: Number(form.retirementAnnualReturn) / 100,
    retirement_account_type: emptyToNull(form.retirementAccountType),
    retirement_taxable_withdrawal_share: form.retirementAccountType === "mixed"
      ? optionalSharePercent(
          form.retirementTaxableWithdrawalShare,
          "Pre-tax Traditional withdrawal share"
        )
      : null,
    retirement_adjust_contributions_for_inflation:
      form.retirementAdjustContributionsForInflation,
    monthly_essential_expenses: optionalMoney(form.monthlyEssentialExpenses, "Essential monthly expenses"),
    current_cash_savings: optionalMoney(form.currentCashSavings, "Current cash savings"),
    emergency_fund_months: 0,
    emergency_fund_target_amount: form.emergencyFundEnabled
      ? optionalMoney(form.emergencyFundTargetAmount, "Emergency reserve target")
      : null,
    emergency_fund_build_months: form.emergencyFundEnabled
      ? Number(form.emergencyFundBuildMonths)
      : 12,
    education_plan: form.educationPlan,
    education_target_year: form.educationPlan === "none" ? null : optionalNumber(form.educationTargetYear),
    education_target_amount: form.educationPlan === "none"
      ? null
      : optionalMoney(form.educationTargetAmount, "Education cash target"),
    near_term_goal_name: null,
    near_term_goal_amount: null,
    near_term_goal_months: null,
    cash_goals: form.cashGoals.map((goal) => ({
      goal_type: goal.goalType,
      target_amount: optionalMoney(
        goal.targetAmount,
        `${cashGoalLabel(goal.goalType)} amount`
      ),
      months_until_needed: optionalNumber(goal.monthsUntilNeeded),
      priority: goal.priority
    })),
    retirement_cash_months: 0,
    retirement_cash_target: null,
    rebalance_threshold: Number(form.rebalanceThreshold) / 100,
    allow_fractional_shares: form.allowFractionalShares,
    rebalance_preference: form.rebalancePreference
  };
}

function profileGuidancePayload(form: ProfileFormState) {
  return {
    risk_tolerance: form.riskTolerance,
    life_stage: emptyToNull(form.lifeStage),
    investment_horizon: emptyToNull(form.investmentHorizon),
    investing_experience: emptyToNull(form.investingExperience),
    income_stability: emptyToNull(form.incomeStability),
    liquidity_needs: emptyToNull(form.liquidityNeeds),
    preferred_style: emptyToNull(form.preferredStyle),
    monthly_net_income: optionalMoney(form.monthlyNetIncome, "Monthly net cash income"),
    monthly_contribution: optionalMoney(form.monthlyContribution, "Planned monthly investment")
  };
}

function profileFormWithAllocation(
  form: ProfileFormState,
  allocation: Record<string, number>
): ProfileFormState {
  return {
    ...form,
    equityTarget: percentInput(allocation.Equity),
    bondTarget: percentInput(allocation.Bond),
    commodityTarget: percentInput(allocation["Commodity / Gold"]),
    internationalEquityTarget: percentInput(allocation["International Equity"]),
    alternativesTarget: percentInput(allocation.Alternatives)
  };
}

function profileFormFromResponse(profile: ProfileResponse): ProfileFormState {
  return {
    riskTolerance: profile.risk_tolerance,
    lifeStage: profile.life_stage ?? "",
    investmentHorizon: profile.investment_horizon ?? "",
    investingExperience: profile.investing_experience ?? "",
    incomeStability: profile.income_stability ?? "",
    liquidityNeeds: profile.liquidity_needs ?? "",
    preferredStyle: profile.preferred_style ?? "",
    equityTarget: percentInput(profile.target_allocation.Equity),
    bondTarget: percentInput(profile.target_allocation.Bond),
    commodityTarget: percentInput(
      profile.target_allocation["Commodity / Gold"]
        ?? profile.target_allocation.Commodity
    ),
    internationalEquityTarget: percentInput(
      profile.target_allocation["International Equity"]
    ),
    alternativesTarget: percentInput(profile.target_allocation.Alternatives),
    preferredMethodDocumentIds: profile.preferred_method_document_ids,
    monthlyNetIncome: moneyInput(profile.monthly_net_income),
    monthlyContribution: moneyInput(profile.monthly_contribution),
    monthlySectorSatelliteBudget: moneyInput(profile.monthly_sector_satellite_budget),
    monthlyTotalExpenses: moneyInput(profile.monthly_total_expenses),
    primaryFinancialPriority: profile.primary_financial_priority ?? "",
    currentAge: nullableInput(profile.current_age),
    plannedRetirementAge: nullableInput(profile.planned_retirement_age),
    retirementPlanningAge: String(profile.retirement_planning_age),
    retirementMonthlySpending: moneyInput(profile.retirement_monthly_spending),
    retirementMonthlyIncome: moneyInput(profile.retirement_monthly_income),
    retirementCurrentSavings: moneyInput(profile.retirement_current_savings),
    retirementIncomeTaxable: profile.retirement_income_taxable,
    retirementInflationRate: percentInput(profile.retirement_inflation_rate),
    retirementCurrentTaxRate: percentInput(profile.retirement_current_tax_rate),
    retirementTaxRate: percentInput(profile.retirement_tax_rate),
    retirementAnnualReturn: percentInput(profile.retirement_annual_return),
    retirementAccountType: profile.retirement_account_type ?? "",
    retirementTaxableWithdrawalShare: percentInput(
      profile.retirement_taxable_withdrawal_share
    ),
    retirementAdjustContributionsForInflation:
      profile.retirement_adjust_contributions_for_inflation,
    monthlyEssentialExpenses: moneyInput(profile.monthly_essential_expenses),
    currentCashSavings: moneyInput(profile.current_cash_savings),
    emergencyFundEnabled: (
      (profile.emergency_fund_target_amount ?? 0) > 0 || profile.emergency_fund_months > 0
    ),
    emergencyFundMonths: String(profile.emergency_fund_months),
    emergencyFundTargetAmount: (
      (profile.emergency_fund_target_amount ?? 0) > 0 || profile.emergency_fund_months > 0
    )
      ? moneyInput(
          profile.emergency_fund_target_amount
            ?? ((profile.monthly_essential_expenses ?? 0) * profile.emergency_fund_months)
        )
      : "",
    emergencyFundBuildMonths: (
      (profile.emergency_fund_target_amount ?? 0) > 0 || profile.emergency_fund_months > 0
    ) ? String(profile.emergency_fund_build_months) : "",
    educationPlan: profile.education_plan,
    educationTargetYear: nullableInput(profile.education_target_year),
    educationTargetAmount: moneyInput(profile.education_target_amount),
    cashGoals: profile.cash_goals.map((goal) => ({
      goalType: goal.goal_type,
      targetAmount: moneyInput(goal.target_amount),
      monthsUntilNeeded: nullableInput(goal.months_until_needed),
      priority: goal.priority
    })),
    rebalanceThreshold: percentInput(profile.rebalance_threshold),
    allowFractionalShares: profile.allow_fractional_shares,
    rebalancePreference: profile.rebalance_preference
  };
}

function cashGoalLabel(goalType: CashGoalType): string {
  return cashGoalOptions.find((option) => option.goalType === goalType)?.label ?? goalType;
}

function deriveReportTopic(question: string): string {
  const cleaned = question
    .replace(/[?!.]+$/g, "")
    .replace(/^(based on (this|the) (article|document|report|file),?\s*)/i, "")
    .replace(/^(please\s+)?(tell me|explain|summarize)\s+(about\s+)?/i, "")
    .replace(
      /^(can|could|should)\s+i\s+(invest\s+(in\s+)?|buy\s+|sell\s+|hold\s+|allocate\s+(to\s+)?)/i,
      ""
    )
    .replace(
      /^(what\s+(is|are|was|were)|how\s+(did|does|do|has|have|is|are)|why\s+(did|does|do|is|are)|can|could|should|does|do|is|are)\s+/i,
      ""
    )
    .replace(/^(the|a|an)\s+/i, "")
    .replace(/\b(in|for)\s+(20\d{2})\b/i, "$2")
    .trim();
  if (!cleaned) {
    return "";
  }
  const words = cleaned.split(/\s+/).slice(0, 8);
  return words
    .map((word) => word.slice(0, 1).toUpperCase() + word.slice(1))
    .join(" ");
}

function documentDisplayName(document: DocumentSummary): string {
  const fileName = document.metadata.file_name;
  if (typeof fileName === "string" && fileName.trim()) {
    return cleanUploadedFileName(fileName);
  }
  return cleanUploadedFileName(document.title);
}

function cleanUploadedFileName(value: string): string {
  return value.replace(/^[a-f0-9]{32}_/i, "");
}

function reportReadinessChecks(
  result: ChatQueryResponse | null
): Array<{ label: string; passed: boolean }> {
  if (!result) {
    return [];
  }
  const gatePassed = result.search.evidence_gate?.decision === "supported"
    && result.search.evidence_gate.report_eligible === true;
  const answerPassed = isSubstantiveReportAnswer(result.answer);
  const usesWebEvidence = result.evidence_scope === "web" || result.web_sources.length > 0;
  if (usesWebEvidence) {
    return [
      {
        label: "Evidence Gate accepted enough direct support for a report",
        passed: gatePassed
      },
      {
        label: "At least one direct-URL web source was accepted",
        passed: result.web_sources.length > 0
      },
      {
        label: "Answer citations passed Argus validation",
        passed: result.critic.status === "web_evidence_validated"
      },
      {
        label: "Answer is complete and substantive, not a short or broken extract",
        passed: answerPassed
      }
    ];
  }
  const hasStructuredDataset = result.sources.some((source) => source.source_type === "csv");
  return [
    {
      label: "Evidence Gate accepted enough direct support for a report",
      passed: gatePassed
    },
    {
      label: "At least one cited passage and one structured claim were produced",
      passed: result.sources.length > 0 && result.claims.length > 0
    },
    {
      label: "Local evidence critic passed",
      passed: result.critic.status === "passed"
    },
    {
      label: "Answer is substantive, or the evidence is a structured CSV dataset",
      passed: answerPassed || hasStructuredDataset
    }
  ];
}

function isReportableChatResult(result: ChatQueryResponse | null): boolean {
  if (!result) {
    return false;
  }
  if (
    result.web_sources.length > 0
    && result.critic.status === "web_evidence_validated"
    && result.search.evidence_gate?.decision === "supported"
    && result.search.evidence_gate.report_eligible === true
    && isSubstantiveReportAnswer(result.answer)
  ) {
    return true;
  }
  return (
    result.search.evidence_gate?.decision === "supported" &&
    result.search.evidence_gate.report_eligible === true &&
    result.sources.length > 0 &&
    result.claims.length > 0 &&
    result.critic.status === "passed" &&
    (
      isSubstantiveReportAnswer(result.answer)
      || result.sources.some((source) => source.source_type === "csv")
    )
  );
}

function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (!item || typeof item !== "object") {
        return String(item);
      }
      const record = item as { loc?: unknown; msg?: unknown; message?: unknown };
      const message = record.msg ?? record.message;
      const location = Array.isArray(record.loc)
        ? record.loc.filter((part) => part !== "body").join(" → ")
        : "";
      const readableMessage = String(message ?? JSON.stringify(item)).replace(
        /^Value error,\s*/i,
        ""
      );
      return `${location ? `${location}: ` : ""}${readableMessage}`;
    }).filter(Boolean);
    return messages.join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return "The server returned an unreadable validation error.";
  }
}

function isNoEvidenceAnswer(answer: string): boolean {
  return answer.toLowerCase().includes("could not find relevant local evidence");
}

function isSubstantiveReportAnswer(answer: string): boolean {
  if (isNoEvidenceAnswer(answer)) {
    return false;
  }
  let body = answer.replace(/\s+/g, " ").trim();
  const prefix = "Based on the strongest local source, ";
  if (body.startsWith(prefix)) {
    body = body.slice(prefix.length).trim();
  }
  if (
    !body
    || body.endsWith("...")
    || body.split("|").length >= 5
    || /\b(and|or|but|because|although|while|with|without|to|of|for|from|by|in|on|at|as)[\s,;:.!?-]*$/i.test(body)
  ) {
    return false;
  }
  const cjkCount = body.match(/[\u3400-\u9fff]/g)?.length ?? 0;
  if (cjkCount >= 24) {
    return true;
  }
  const wordCount = body.match(/[A-Za-z0-9][A-Za-z0-9'’-]*/g)?.length ?? 0;
  const sentenceCount = body.match(/[.!?](?:\s|$)/g)?.length ?? 0;
  return wordCount >= 24 || (sentenceCount >= 2 && wordCount >= 18);
}

function recommendInvestmentStyle(form: ProfileFormState): string {
  const lifeStage = form.lifeStage.toLowerCase();
  const risk = form.riskTolerance.toLowerCase();
  const liquidity = form.liquidityNeeds.toLowerCase();
  const income = form.incomeStability.toLowerCase();
  const horizon = form.investmentHorizon.toLowerCase();

  if (
    lifeStage.includes("retired") ||
    liquidity.includes("high medical") ||
    (risk === "conservative" && horizon.includes("under 3"))
  ) {
    return "Capital preservation";
  }
  if (
    lifeStage.includes("college") ||
    lifeStage.includes("pre-retirement") ||
    liquidity === "high" ||
    income === "low"
  ) {
    return "Broad index / passive";
  }
  if (risk === "aggressive" && horizon.includes("10+")) {
    return "Growth";
  }
  if (risk === "conservative") {
    return "Capital preservation";
  }
  if (lifeStage.includes("caregiver")) {
    return "Broad index / passive";
  }
  return "Broad index / passive";
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function optionalMoney(value: string, label: string): number | null {
  const trimmed = value.replace(/,/g, "").trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(`${label} must be a non-negative number such as 125,000.`);
  }
  return parsed;
}

function formatMoneyTyping(value: string): string | null {
  const ungrouped = value.replace(/[$,\s]/g, "");
  if (!ungrouped) {
    return "";
  }
  if (!/^\d*(?:\.\d{0,2})?$/.test(ungrouped)) {
    return null;
  }
  const [rawInteger = "", decimal] = ungrouped.split(".");
  const integer = rawInteger || "0";
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return decimal === undefined ? grouped : `${grouped}.${decimal}`;
}

function parseMoneyValue(value: string): number | null {
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function moneyInput(value: number | null): string {
  if (value === null) {
    return "";
  }
  return value.toLocaleString("en-US", {
    useGrouping: true,
    maximumFractionDigits: 2
  });
}

function optionalNumber(value: string): number | null {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
}

function nullableInput(value: number | null): string {
  return value === null ? "" : String(value);
}

function optionalPercent(value: string, label: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 75) {
    throw new Error(`${label} must be between 0% and 75%.`);
  }
  return parsed / 100;
}

function optionalSharePercent(value: string, label: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
    throw new Error(`${label} must be between 0% and 100%.`);
  }
  return parsed / 100;
}

function percentInput(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "";
  }
  const percent = Math.round(value * 1000) / 10;
  return Number.isInteger(percent) ? String(percent) : percent.toFixed(1);
}

function retirementAccountLabel(value: string | null): string {
  const labels: Record<string, string> = {
    traditional_401k: "Traditional 401(k) (pre-tax)",
    traditional_ira: "Traditional IRA / SEP (pre-tax)",
    roth: "Roth account (after-tax)",
    taxable_brokerage: "taxable brokerage (after-tax)",
    mixed: "Mixed Traditional + Roth accounts"
  };
  return value ? labels[value] ?? value : "account not selected";
}

function allocationDriftRows(
  allocation: AllocationSlice[],
  targetAllocation: Record<string, number>
) {
  const currentByClass = new Map<string, number>();
  const labelByClass = new Map<string, string>();
  for (const item of allocation) {
    const key = normalizeAssetClass(item.asset_class);
    if (key === "cash") {
      continue;
    }
    currentByClass.set(key, (currentByClass.get(key) ?? 0) + item.weight);
    labelByClass.set(key, item.asset_class);
  }

  const targetByClass = new Map<string, number>();
  for (const [assetClass, rawWeight] of Object.entries(targetAllocation)) {
    const weight = boundedWeight(rawWeight);
    if (weight <= 0) {
      continue;
    }
    const key = normalizeAssetClass(assetClass);
    targetByClass.set(key, weight);
    if (!labelByClass.has(key)) {
      labelByClass.set(key, assetClass);
    }
  }
  if (targetByClass.size === 0) {
    return [];
  }

  return Array.from(new Set([...currentByClass.keys(), ...targetByClass.keys()]))
    .map((key) => ({
      assetClass: labelByClass.get(key) ?? key,
      current: currentByClass.get(key) ?? 0,
      target: targetByClass.get(key) ?? 0
    }))
    .sort((left, right) => (
      Math.max(right.current, right.target) - Math.max(left.current, left.target)
    ));
}

function normalizeAssetClass(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/_/g, " ");
  const aliases: Record<string, string> = {
    stock: "equity",
    stocks: "equity",
    "us stock": "equity",
    "us equity": "equity",
    "equity etf": "equity",
    "stock etf": "equity",
    "us equity etf": "equity",
    bonds: "bond",
    "fixed income": "bond",
    "bond etf": "bond",
    "fixed income etf": "bond",
    "cash equivalent": "cash",
    "cash equivalents": "cash",
    "commodity / gold": "commodity",
    "commodity etf": "commodity",
    commodities: "commodity",
    gold: "commodity",
    "gold etf": "commodity",
    alternative: "alternatives",
    "alternative etf": "alternatives",
    "international stock": "international equity",
    "international stocks": "international equity",
    "international equity etf": "international equity",
    "non-us equity": "international equity"
  };
  return aliases[normalized] ?? normalized;
}

function boundedWeight(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

function chartColor(index: number): string {
  const colors = ["#2f7d62", "#4c7bd9", "#d68132", "#8b5cf6", "#c2415d", "#3d8f8f"];
  return colors[index % colors.length];
}

function todayInputValue(): string {
  const now = new Date();
  const localTime = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localTime.toISOString().slice(0, 10);
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(value);
}

function formatCurrencyPrecise(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

function formatOptionalCurrency(value: number | null): string {
  return value === null ? "Not set" : formatCurrencyPrecise(value);
}

function formatMonthCount(value: number): string {
  return `${value} ${value === 1 ? "month" : "months"}`;
}

function formatShares(value: number): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
    maximumFractionDigits: 4
  }).format(value);
}

function shareInstruction(item: {
  action?: string;
  asset_class: string;
  symbol: string | null;
  estimated_shares: number | null;
  reference_price?: number | null;
}): string {
  if (item.asset_class.trim().toLowerCase() === "cash") {
    return "No shares — cash reserve";
  }
  if (item.estimated_shares !== null) {
    return `${formatShares(item.estimated_shares)} shares`;
  }
  if (item.action === "REVIEW" && item.reference_price) {
    return "Below 1 whole share · no trade";
  }
  if (item.symbol === null) {
    return "No instrument assigned";
  }
  return "Current quote needed";
}

function formatCurrencyShort(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 1,
    notation: "compact"
  }).format(value);
}

function formatOptionalCompactNumber(value: number | null): string {
  if (value === null) {
    return "Unavailable";
  }
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

function formatMarketMove(value: number | null): string {
  if (value === null) {
    return "No change data";
  }
  const arrow = value > 0 ? "▲" : value < 0 ? "▼" : "•";
  const prefix = value > 0 ? "+" : "";
  return `${arrow} ${prefix}${value.toFixed(2)}%`;
}

function marketChangeClass(value: number | null): string {
  if (value === null) {
    return "change-unavailable";
  }
  if (value >= 1.5) {
    return "change-up-strong";
  }
  if (value >= 0.05) {
    return "change-up";
  }
  if (value <= -1.5) {
    return "change-down-strong";
  }
  if (value <= -0.05) {
    return "change-down";
  }
  return "change-flat";
}

function volumeActivityClass(value: number | null): string {
  if (value === null) {
    return "volume-unavailable";
  }
  if (value >= 3) {
    return "volume-unusual";
  }
  if (value >= 2) {
    return "volume-high";
  }
  if (value >= 1) {
    return "volume-elevated";
  }
  if (value <= -1.5) {
    return "volume-quiet";
  }
  return "volume-normal";
}

function volumeActivityLabelClass(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "unusual") return "activity-unusual";
  if (normalized === "high") return "activity-high";
  if (normalized === "elevated") return "activity-elevated";
  if (normalized === "quiet") return "activity-quiet";
  if (normalized === "normal") return "activity-normal";
  return "activity-unavailable";
}

function recommendationModeBadge(value: string): string {
  if (value === "diversifying_replacement") {
    return "⇄ REPLACE";
  }
  if (value === "existing_holding_review") {
    return "◎ REVIEW";
  }
  return "＋ NEW";
}

function recommendationModeLabel(value: string): string {
  if (value === "diversifying_replacement") {
    return "ETF replacement research · consider diversified exposure instead of adding to mapped single-stock concentration";
  }
  if (value === "existing_holding_review") {
    return "Existing ETF review · monitor the thesis and use the separate deterministic Rebalance section for any amount change";
  }
  return "New-exposure research · a bounded candidate for an exposure not directly held";
}

function volumeActivityMeaning(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "unusual") {
    return "Volume is extremely high relative to this ETF’s own recent history. Check the price direction and event context before interpreting it.";
  }
  if (normalized === "high") {
    return "Volume is distinctly above this ETF’s recent norm, so today’s move has unusually broad participation.";
  }
  if (normalized === "elevated") {
    return "Volume is moderately above this ETF’s recent norm. It can strengthen confidence that the price move attracted attention, but does not predict continuation.";
  }
  if (normalized === "quiet") {
    return "Volume is unusually light relative to recent sessions. Price moves may have weaker participation, although quiet trading is not automatically negative.";
  }
  if (normalized === "normal") {
    return "Volume is within this ETF’s typical recent range. There is no unusual participation signal from volume alone.";
  }
  return "Argus does not have enough supported completed-session history to classify this ETF’s volume activity.";
}

function formatCost(value: number): string {
  if (value === 0) {
    return "$0.00";
  }
  if (value < 0.0001) {
    return "<$0.0001";
  }
  if (value < 0.01) {
    return `$${value.toFixed(4)}`;
  }
  return `$${value.toFixed(2)}`;
}

function formatPerMillionPrice(value: number): string {
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4
  })}`;
}

function formatProviderName(provider: string): string {
  const labels: Record<string, string> = {
    deepseek: "DeepSeek",
    moonshot: "Kimi",
    exa: "Exa",
    google: "Gemini"
  };
  return labels[provider.toLowerCase()] ?? provider;
}

function formatProviderAmount(value: number, currency: string): string {
  return `${currency} ${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 8
  })}`;
}

function configuredModelPricing(
  modelOptions: ChatModelOption[],
  provider: string,
  model: string
): ChatModelOption | undefined {
  const providerModelId = `${provider}/${model}`.toLowerCase();
  const modelSuffix = `/${model}`.toLowerCase();
  return modelOptions.find((option) => {
    const optionId = option.id.toLowerCase();
    return optionId === providerModelId || optionId.endsWith(modelSuffix);
  });
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function cleanModelMarkdown(value: string): string {
  return value
    .replace(/\*\*/g, "")
    .replace(/^\s*\*\s+/gm, "- ")
    .replace(/\s+\*\s+/g, "; ")
    .replace(/:;/g, ":")
    .replace(/`/g, "")
    .trim();
}

function formatFileSize(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDocumentResourceError(detail: {
  code?: string;
  message?: string;
  stage?: string;
  observed?: number;
  limit?: number;
  next_action?: string;
}): string {
  const parts = [detail.message ?? "Document processing stopped."];
  if (detail.stage) {
    parts.push(`Stage: ${detail.stage}.`);
  }
  if (detail.observed !== undefined && detail.limit !== undefined) {
    const byteBased = detail.code?.includes("memory") || detail.code === "upload_too_large";
    const observed = byteBased ? formatFileSize(detail.observed) : detail.observed;
    const limit = byteBased ? formatFileSize(detail.limit) : detail.limit;
    parts.push(`Observed ${observed}; limit ${limit}.`);
  }
  if (detail.next_action) {
    parts.push(detail.next_action);
  }
  return parts.join(" ");
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1
  }).format(value);
}

function formatEvidenceCheckStatus(value: string): string {
  if (value === "passed") {
    return "Evidence looks sufficient";
  }
  if (value === "warning") {
    return "Evidence is weak";
  }
  if (value === "failed") {
    return "Needs source review";
  }
  return formatStatus(value);
}

function formatCashPlanStatus(value: string): string {
  if (value === "shortfall") {
    return "Monthly gap";
  }
  if (value === "feasible") {
    return "On track";
  }
  return "Needs inputs";
}

function providerQuotaMessage(_modelId: string): string {
  return "The selected model provider returned HTTP 429. Check its balance, quota, and rate-limit dashboard before retrying. Argus will not enable billing or switch models automatically.";
}

function riskScopeLabel(code: string): string {
  return code === "single_position_concentration"
    ? "Single holding"
    : code === "asset_class_concentration"
      ? "Asset class"
      : "Portfolio rule";
}

function formatStatus(value: string): string {
  return value.split("_").join(" ");
}

function formatExecutionOutcome(value: string): string {
  const labels: Record<string, string> = {
    cloud_completed: "source-backed cloud answer",
    local_completed: "local evidence answer",
    cloud_skipped_no_evidence: "model skipped because local evidence was insufficient",
    cloud_declined_unsupported: "model declined unsupported evidence",
    web_skipped_no_supported_evidence: "Evidence Gate stopped before the answer model",
    web_evidence_completed: "web evidence answer",
    hybrid_evidence_completed: "uploaded + web evidence answer"
  };
  return labels[value] ?? formatStatus(value);
}

function formatModelFailureCode(value: string | null): string {
  const labels: Record<string, string> = {
    provider_timeout: "provider timed out",
    provider_authentication_failed: "authentication failed",
    provider_quota_exhausted: "quota, balance, or rate limit reached",
    model_provider_error: "model provider error"
  };
  return value ? (labels[value] ?? formatStatus(value)) : "unknown provider failure";
}

function compactJson(value: Record<string, unknown>): string {
  const serialized = JSON.stringify(value);
  if (serialized.length <= 140) {
    return serialized;
  }
  return `${serialized.slice(0, 137)}...`;
}

function toolCallDescription(toolName: string): string {
  const descriptions: Record<string, string> = {
    exa_market_search_and_evidence_gate:
      "Searches public web evidence, then rejects passages that do not directly support the requested market claims.",
    exa_web_search:
      "Searches public web pages and returns direct-URL evidence for Argus validation.",
    retrieve_evidence:
      "Retrieves relevant passages from uploaded and indexed research sources.",
    evidence_gate:
      "Checks whether retrieved evidence is sufficiently relevant and complete before model synthesis."
  };
  return descriptions[toolName]
    ?? "Executes a bounded non-model operation recorded for audit and debugging.";
}

export default App;
