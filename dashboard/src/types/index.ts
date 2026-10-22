export type RunOutcome = 'success' | 'failure' | 'blocked' | 'timed_out' | 'in_progress'

export interface Run {
  id: string
  session_id?: string | null
  external_session_id?: string | null
  agent_label?: string | null
  task_id?: string | null
  prompt_version?: string | null
  model?: string | null
  outcome: RunOutcome | string
  failure_category?: string | null
  total_cost: number
  total_tokens: number
  prompt_tokens?: number
  completion_tokens?: number
  latency_ms: number
  step_count: number
  error_message?: string | null
  tags?: Record<string, any>
  started_at?: string
  created_at?: string
  ended_at?: string | null
}

export interface Span {
  id: string
  run_id: string
  sequence_number: number
  parent_span_id?: string | null
  policy_version_id?: string | null
  span_type: 'model' | 'tool' | string
  name: string
  input_payload: any
  output_payload: any
  started_at?: string
  ended_at?: string | null
  latency_ms?: number
  duration_ms?: number
  token_counts?: Record<string, number>
  error?: string | null
  redaction_count?: number
  policy_decision: 'allow' | 'deny' | 'require_approval' | 'pending' | 'bypassed' | string | null
  policy_rule_id?: string | null
  policy_reason?: string | null
  injection_flag?: boolean
  injection_details?: Record<string, any>
}

export interface RunDetail extends Run {
  spans: Span[]
}

export interface SessionItem {
  id: string
  session_id: string
  name: string | null
  session_metadata?: Record<string, any>
  run_count: number
  created_at: string
}

export interface RunListResponse {
  total: number
  runs: Run[]
}

export interface SessionListResponse {
  total: number
  sessions: SessionItem[]
}

export interface RunFilters {
  outcome?: string
  model?: string
  session_id?: string
  search?: string
  start_date?: string
  end_date?: string
  limit: number
  offset: number
}

export interface ApprovalItem {
  id: string
  run_id: string
  session_id?: string | null
  agent_id?: string | null
  span_id?: string | null
  tool_name: string
  tool_args?: Record<string, any>
  arguments?: Record<string, any>
  call_hash: string
  status: 'pending' | 'approved' | 'rejected' | 'timed_out' | string
  timeout_seconds: number
  remaining_seconds: number
  requested_at?: string
  created_at?: string
  decided_at?: string | null
  decision_reason?: string | null
  decided_by?: string | null
  is_consumed?: boolean
}

export interface AnalyticsSummary {
  total_runs: number
  successful_runs: number
  failed_runs: number
  blocked_runs: number
  timed_out_runs: number
  task_completion_rate: number
  total_cost: number | null
  cost_per_run: number | null
  cost_per_successful_task: number | null
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  avg_tokens_per_run: number
  p50_latency_ms: number
  p95_latency_ms: number
  avg_latency_ms: number
  total_tool_calls: number
  tool_error_rate: number
  retry_rate: number
  policy_block_rate: number
  failure_categories: Record<string, number>
}

export interface ModelBreakdownItem {
  model: string
  cohort_size: number
  completion_rate: number
  total_cost: number | null
  cost_per_run: number | null
  cost_per_successful_task: number | null
  p50_latency_ms: number
  p95_latency_ms: number
  avg_latency_ms: number
  total_tokens: number
}

export interface ToolBreakdownItem {
  tool_name: string
  cohort_size: number
  error_count: number
  error_rate: number
  retry_count: number
  retry_rate: number
  p50_latency_ms: number
  p95_latency_ms: number
  avg_latency_ms: number
  policy_block_count: number
  top_block_rule?: string | null
}

export interface PromptVersionBreakdownItem {
  prompt_version: string
  cohort_size: number
  completion_rate: number
  total_cost: number | null
  cost_per_run: number | null
  cost_per_successful_task: number | null
  p50_latency_ms: number
  p95_latency_ms: number
  avg_latency_ms: number
}

export interface TimeSeriesDataPoint {
  date: string
  cohort_size: number
  total_cost: number | null
  avg_latency_ms: number
  success_rate: number
  tool_calls?: number
  blocked_runs?: number
}

export interface AnalyticsBreakdown {
  models: ModelBreakdownItem[]
  tools: ToolBreakdownItem[]
  prompt_versions: PromptVersionBreakdownItem[]
  time_series: TimeSeriesDataPoint[]
}

export interface AnomalyItem {
  id: string
  run_id: string
  type: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  metric: string
  value: any
  cohort_size?: number | null
  baseline_reference?: string | null
  message: string
  detected_at: string
}

export interface ModelComparisonMetric {
  metric_name: string
  model_a_value: number | null
  model_b_value: number | null
  diff_percentage: number | null
  winner: 'model_a' | 'model_b' | 'tie' | 'unknown' | string | null
}

export interface ModelComparisonResponse {
  model_a: string
  model_b: string
  model_a_cohort_size: number
  model_b_cohort_size: number
  metrics: ModelComparisonMetric[]
  note?: string | null
}

export interface AlertRuleItem {
  id: string
  name: string
  metric: string
  condition: string
  threshold: number
  window_runs: number
  webhook_url?: string | null
  is_active: boolean
  last_triggered_at?: string | null
  created_at: string
}

export interface TrajectoryStepDiff {
  step_number: number
  tool_name_recorded: string | null
  tool_name_replayed: string | null
  tool_match: boolean
  args_recorded: Record<string, any> | null
  args_replayed: Record<string, any> | null
  arg_similarity: number
  output_recorded: any
  output_replayed: any
  policy_decision_recorded: string | null
  policy_decision_replayed: string | null
  is_cache_miss: boolean
}

export interface ReplayIteration {
  iteration_index: number
  fidelity_score: number
  s_tool: number
  s_args: number
  s_outcome: number
  cache_miss_rate: number
  replayed_outcome: string
  replayed_tools: string[]
}

export interface SensitivityPoint {
  threshold: number
  fidelity_score: number
  cache_miss_rate: number
  cache_misses: number
  total_calls: number
}

export interface ReplayRecord {
  replay_id: string
  original_run_id: string
  target_model: string | null
  target_prompt_version: string | null
  candidate_policy_version_id: string | null
  outcome: string
  fidelity_score: number
  cache_miss_rate: number
  fidelity_spread: number
  regression_detected: boolean
  regression_reasons: string[]
  iteration_results: ReplayIteration[]
  trajectory_diff: TrajectoryStepDiff[]
  sensitivity_table?: SensitivityPoint[] | null
  created_at: string
}

export interface ReplayListItem {
  id: string
  original_run_id: string
  target_model: string | null
  target_prompt_version: string | null
  fidelity_score: number
  cache_miss_rate: number
  outcome: string
  created_at: string | null
}



