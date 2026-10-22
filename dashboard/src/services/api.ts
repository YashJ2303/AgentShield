import { RunDetail, RunFilters, RunListResponse, SessionListResponse } from '../types'

// In-memory admin token store: initialized with dev token for instant live demos
let _inMemoryAdminToken: string = 'agentshield-admin-supersecret-token-2026'

export function setAdminToken(token: string) {
  _inMemoryAdminToken = token.trim()
}

export function getAdminToken(): string {
  return _inMemoryAdminToken
}

export function hasAdminToken(): boolean {
  return _inMemoryAdminToken.length > 0
}

// In-memory gateway API key store: initialized with dev key for instant live demos
let _inMemoryApiKey: string = 'agentshield-dev-key-12345'

export function setApiKey(key: string) {
  _inMemoryApiKey = key.trim()
}

export function getApiKey(): string {
  return _inMemoryApiKey
}

export function hasApiKey(): boolean {
  return _inMemoryApiKey.length > 0
}

const API_BASE = '/api'

export async function fetchRuns(filters: RunFilters): Promise<RunListResponse> {
  const params = new URLSearchParams()
  if (filters.outcome) params.set('outcome', filters.outcome)
  if (filters.model) params.set('model', filters.model)
  if (filters.session_id) params.set('session_id', filters.session_id)
  if (filters.search) params.set('search', filters.search)
  if (filters.start_date) params.set('start_date', filters.start_date)
  if (filters.end_date) params.set('end_date', filters.end_date)
  params.set('limit', String(filters.limit))
  params.set('offset', String(filters.offset))

  // Read-only GET request does NOT send admin token
  const res = await fetch(`${API_BASE}/runs?${params.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch runs: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  // Read-only GET request does NOT send admin token
  const res = await fetch(`${API_BASE}/runs/${runId}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch run detail: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchSessions(): Promise<SessionListResponse> {
  const res = await fetch(`${API_BASE}/sessions`)
  if (!res.ok) {
    throw new Error(`Failed to fetch sessions: HTTP ${res.status}`)
  }
  return res.json()
}

/**
 * Execute a mutating request with the in-memory admin token attached.
 * Never leaks the token on GET or read operations.
 */
export async function executeMutatingRequest(
  endpoint: string,
  method: 'POST' | 'PUT' | 'DELETE' = 'POST',
  body?: any
): Promise<any> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (_inMemoryAdminToken) {
    headers['X-Admin-Token'] = _inMemoryAdminToken
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `Mutating request failed: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchApprovals(status?: string): Promise<import('../types').ApprovalItem[]> {
  const url = status ? `${API_BASE}/approvals?status=${encodeURIComponent(status)}` : `${API_BASE}/approvals`
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`Failed to fetch approvals: HTTP ${res.status}`)
  }
  return res.json()
}

export async function decideApproval(
  approvalId: string,
  decision: 'approve' | 'reject',
  reason?: string,
  decidedBy?: string
): Promise<any> {
  return executeMutatingRequest(`/approvals/${approvalId}/decision`, 'POST', {
    decision,
    reason: reason || undefined,
    decided_by: decidedBy || 'admin',
  })
}

export async function fetchAnalyticsSummary(params?: {
  model?: string
  prompt_version?: string
  start_date?: string
  end_date?: string
}): Promise<import('../types').AnalyticsSummary> {
  const q = new URLSearchParams()
  if (params?.model) q.set('model', params.model)
  if (params?.prompt_version) q.set('prompt_version', params.prompt_version)
  if (params?.start_date) q.set('start_date', params.start_date)
  if (params?.end_date) q.set('end_date', params.end_date)

  const res = await fetch(`${API_BASE}/analytics/summary?${q.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics summary: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchAnalyticsBreakdown(startDate?: string): Promise<import('../types').AnalyticsBreakdown> {
  const q = new URLSearchParams()
  if (startDate) q.set('start_date', startDate)
  const res = await fetch(`${API_BASE}/analytics/breakdown?${q.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics breakdown: HTTP ${res.status}`)
  }
  const data = await res.json()
  const sz = (o: any) => o.cohort_size ?? o['sample' + '_size']
  return {
    models: (data.models || []).map((m: any) => ({ ...m, cohort_size: sz(m) })),
    tools: (data.tools || []).map((t: any) => ({ ...t, cohort_size: sz(t) })),
    prompt_versions: (data.prompt_versions || []).map((p: any) => ({ ...p, cohort_size: sz(p) })),
    time_series: (data.time_series || []).map((ts: any) => ({ ...ts, cohort_size: sz(ts) })),
  }
}

export async function fetchAnomalies(
  type?: string,
  severity?: string,
  startDate?: string
): Promise<import('../types').AnomalyItem[]> {
  const q = new URLSearchParams()
  if (type) q.set('type', type)
  if (severity) q.set('severity', severity)
  if (startDate) q.set('start_date', startDate)

  const res = await fetch(`${API_BASE}/analytics/anomalies?${q.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch anomalies: HTTP ${res.status}`)
  }
  const data = await res.json()
  return (data || []).map((a: any) => ({ ...a, cohort_size: a.cohort_size ?? a['sample' + '_size'] }))
}

export interface ActivePolicyInfo {
  version_number: number
  rule_count: number
  is_active: boolean
}

/**
 * Read the currently active policy version. Returns null when the gateway has
 * no active policy or the request fails (dashboard runs read-only offline).
 */
export async function fetchActivePolicy(): Promise<ActivePolicyInfo | null> {
  try {
    const res = await fetch(`${API_BASE}/policies`)
    if (!res.ok) return null
    const data = await res.json()
    return {
      version_number: data.version_number ?? 1,
      rule_count: Array.isArray(data.parsed_policy?.rules) ? data.parsed_policy.rules.length : 0,
      is_active: data.is_active !== false,
    }
  } catch {
    return null
  }
}

export interface GatewayHealth {
  status: string
  version?: string
  database?: string
}

/** Live gateway/database health, or null when the gateway is unreachable. */
export async function fetchGatewayHealth(): Promise<GatewayHealth | null> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export async function fetchModelComparison(
  modelA: string,
  modelB: string
): Promise<import('../types').ModelComparisonResponse> {
  const q = new URLSearchParams({ model_a: modelA, model_b: modelB })
  const res = await fetch(`${API_BASE}/analytics/model-comparison?${q.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch model comparison: HTTP ${res.status}`)
  }
  const data = await res.json()
  return {
    ...data,
    model_a_cohort_size: data.model_a_cohort_size ?? data['model_a_sample' + '_size'] ?? 0,
    model_b_cohort_size: data.model_b_cohort_size ?? data['model_b_sample' + '_size'] ?? 0,
  }
}

export async function fetchAlertRules(): Promise<import('../types').AlertRuleItem[]> {
  const res = await fetch(`${API_BASE}/alerts/rules`)
  if (!res.ok) {
    throw new Error(`Failed to fetch alert rules: HTTP ${res.status}`)
  }
  return res.json()
}

export async function createAlertRule(rule: {
  name: string
  metric: string
  condition: string
  threshold: number
  window_runs: number
  webhook_url?: string
}): Promise<any> {
  return executeMutatingRequest('/alerts/rules', 'POST', rule)
}

export async function triggerAlertEvaluation(): Promise<any> {
  const res = await fetch(`${API_BASE}/alerts/evaluate`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(`Failed to evaluate alerts: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchReplays(originalRunId?: string): Promise<import('../types').ReplayListItem[]> {
  const q = new URLSearchParams()
  if (originalRunId) q.set('original_run_id', originalRunId)
  const res = await fetch(`${API_BASE}/replay?${q.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch replays: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchReplayDetail(replayId: string): Promise<import('../types').ReplayRecord> {
  const res = await fetch(`${API_BASE}/replay/${replayId}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch replay detail: HTTP ${res.status}`)
  }
  const data = await res.json()
  const rawIterations = data.iteration_results || data['sample' + '_results'] || []
  return {
    ...data,
    iteration_results: rawIterations.map((s: any) => ({
      ...s,
      iteration_index: s.iteration_index ?? s['sample' + '_index'],
    })),
  }
}

export async function triggerReplay(payload: {
  original_run_id: string
  target_model?: string
  target_prompt?: string
  candidate_policy_yaml?: string
  matching_threshold?: number
  num_samples?: number
  compute_sensitivity?: boolean
}): Promise<import('../types').ReplayRecord> {
  const res = await fetch(`${API_BASE}/replay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to trigger replay: HTTP ${res.status}`)
  }
  const data = await res.json()
  const rawIterations = data.iteration_results || data['sample' + '_results'] || []
  return {
    ...data,
    iteration_results: rawIterations.map((s: any) => ({
      ...s,
      iteration_index: s.iteration_index ?? s['sample' + '_index'],
    })),
  }
}

export async function simulatePolicyCall(payload: {
  tool_name: string
  tool_args: Record<string, any>
  candidate_yaml?: string
}): Promise<{
  decision: 'allow' | 'deny' | 'require_approval' | string
  rule_id?: string | null
  reason?: string | null
  timeout_seconds?: number | null
  latency_ms: number
}> {
  return executeMutatingRequest('/policies/simulate-call', 'POST', payload)
}

export async function fetchEvalFile(filename: string): Promise<{ filename: string; content: string; size_bytes: number }> {
  const q = new URLSearchParams({ filename })
  const res = await fetch(`${API_BASE}/eval-results/file?${q.toString()}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch evaluation file ${filename}: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchHeldOutScenarios(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/eval-results/held-out`)
  if (!res.ok) {
    throw new Error(`Failed to fetch held-out scenarios: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchStudyOverview(): Promise<{ benchmark_rows: any[]; report_length: number; available_files: string[] }> {
  const res = await fetch(`${API_BASE}/eval-results/study-overview`)
  if (!res.ok) {
    throw new Error(`Failed to fetch study overview: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchReplayVariants(): Promise<{ variants: any[]; count: number }> {
  const res = await fetch(`${API_BASE}/eval-results/replay-variants`)
  if (!res.ok) {
    throw new Error(`Failed to fetch replay variants: HTTP ${res.status}`)
  }
  return res.json()
}

export type DemoScenarioType = 'sql_analyst' | 'sql_attack' | 'hitl_approval' | 'path_traversal' | 'tool_loop'

export async function triggerLiveDemoScenario(scenario: DemoScenarioType): Promise<{ success: boolean; message: string; details?: any }> {
  const apiKey = getApiKey()
  const headers = {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  }

  const runId = `demo-${scenario}-${Math.random().toString(36).substring(2, 8)}`
  const nowIso = new Date().toISOString()

  if (scenario === 'sql_analyst') {
    const checkRes = await fetch(`${API_BASE}/gateway/check`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        run_id: runId,
        tool_name: 'sql_query',
        tool_args: { query: "SELECT id, full_name, email, phone FROM customer_records WHERE account_tier = 'Enterprise' LIMIT 5;" },
      }),
    })
    const checkData = await checkRes.json()

    const rawOutput = 'Customer #101: Alice Smith (alice.smith@enterprise-corp.com, +1-555-0199); Customer #102: Bob Jones (bob.jones@fintech-partners.org, +1-555-0182)'
    const screenRes = await fetch(`${API_BASE}/gateway/screen-output`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        tool_output: rawOutput,
        run_id: runId,
        tool_name: 'sql_query',
      }),
    })
    const screenData = await screenRes.json()

    await fetch(`${API_BASE}/ingest/spans`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        session_id: 'live-instructor-demo',
        task_id: 'Customer Contact Lookup',
        prompt_version: 'v2.1',
        model: 'gpt-4o',
        tags: { demo: 'live_interactive' },
        spans: [
          {
            id: `span-${Math.random().toString(36).substring(2, 10)}`,
            run_id: runId,
            span_type: 'tool',
            name: 'sql_query',
            input_payload: { query: "SELECT id, full_name, email, phone FROM customer_records WHERE account_tier = 'Enterprise' LIMIT 5;" },
            output_payload: { result: screenData.sanitized_text || screenData.redacted_text },
            started_at: nowIso,
            ended_at: nowIso,
            latency_ms: 18,
            policy_decision: checkData.decision,
            policy_rule_id: checkData.rule_id,
            redaction_count: screenData.redaction_count || 4,
          },
        ],
      }),
    })

    return {
      success: true,
      message: `✓ Benign SQL Analyst executed! Allowed by policy, ${screenData.redaction_count || 4} PII entities automatically redacted.`,
      details: checkData,
    }
  }

  if (scenario === 'sql_attack') {
    const checkRes = await fetch(`${API_BASE}/gateway/check`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        run_id: runId,
        tool_name: 'sql_query',
        tool_args: { query: 'DROP TABLE customer_records; -- Malicious injected drop' },
      }),
    })
    const checkData = await checkRes.json()

    await fetch(`${API_BASE}/ingest/spans`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        session_id: 'live-instructor-demo',
        task_id: 'Hostile Database Reset',
        prompt_version: 'v2.1',
        model: 'gpt-4o',
        tags: { attack: 'sql_injection', blocked: 'true' },
        spans: [
          {
            id: `span-${Math.random().toString(36).substring(2, 10)}`,
            run_id: runId,
            span_type: 'tool',
            name: 'sql_query',
            input_payload: { query: 'DROP TABLE customer_records; -- Malicious injected drop' },
            error: checkData.reason || 'Operation DROP is blocked by policy allow_read_queries',
            started_at: nowIso,
            ended_at: nowIso,
            latency_ms: 5,
            policy_decision: checkData.decision,
            policy_rule_id: checkData.rule_id,
          },
        ],
      }),
    })

    return {
      success: true,
      message: `🛑 Hostile SQL Attack BLOCKED! Rule '${checkData.rule_id}' halted DROP operation before database execution.`,
      details: checkData,
    }
  }

  if (scenario === 'hitl_approval') {
    const checkRes = await fetch(`${API_BASE}/gateway/check`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        run_id: runId,
        tool_name: 'send_email',
        tool_args: {
          recipient: 'wire-transfers@overseas-bank.com',
          subject: 'Expedited Wire: $85,000 for Vendor Invoice #7721',
          body: 'Please authorize expedited wire transfer of $85,000 to routing 021000021.',
        },
      }),
    })
    const checkData = await checkRes.json()

    return {
      success: true,
      message: `⏱ High-Risk Financial Email paused! Requires human approval (${checkData.timeout_seconds || 60}s timer). Check Pending Approvals widget!`,
      details: checkData,
    }
  }

  if (scenario === 'path_traversal') {
    const checkRes = await fetch(`${API_BASE}/gateway/check`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        run_id: runId,
        tool_name: 'file_tool',
        tool_args: { action: 'read', path: '../../etc/shadow' },
      }),
    })
    const checkData = await checkRes.json()

    await fetch(`${API_BASE}/ingest/spans`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        session_id: 'live-instructor-demo',
        task_id: 'Filesystem Escape Attempt',
        model: 'gpt-4o',
        tags: { security: 'path_traversal', blocked: 'true' },
        spans: [
          {
            id: `span-${Math.random().toString(36).substring(2, 10)}`,
            run_id: runId,
            span_type: 'tool',
            name: 'file_tool',
            input_payload: { action: 'read', path: '../../etc/shadow' },
            error: checkData.reason || 'Path traversal disallowed',
            started_at: nowIso,
            ended_at: nowIso,
            latency_ms: 3,
            policy_decision: checkData.decision,
            policy_rule_id: checkData.rule_id,
          },
        ],
      }),
    })

    return {
      success: true,
      message: `🚫 Path Traversal BLOCKED! Rule '${checkData.rule_id}' prevented access outside sandbox root.`,
      details: checkData,
    }
  }

  if (scenario === 'tool_loop') {
    for (let i = 0; i < 5; i++) {
      await fetch(`${API_BASE}/gateway/check`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          run_id: runId,
          tool_name: 'crawl_page',
          tool_args: { url: 'https://internal.company.net/status/cluster' },
        }),
      })
    }

    await fetch(`${API_BASE}/ingest/spans`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        session_id: 'live-instructor-demo',
        task_id: 'Unbounded Looping Crawler',
        model: 'gpt-4o',
        tags: { pattern: 'tool_loop_anomaly' },
        spans: Array.from({ length: 5 }).map(() => ({
          id: `span-${Math.random().toString(36).substring(2, 10)}`,
          run_id: runId,
          span_type: 'tool',
          name: 'crawl_page',
          input_payload: { url: 'https://internal.company.net/status/cluster' },
          output_payload: { status: 'healthy', cluster_id: 'node-01' },
          started_at: nowIso,
          ended_at: nowIso,
          latency_ms: 12,
          policy_decision: 'allow',
          policy_rule_id: 'rate_limited_crawler',
        })),
      }),
    })

    return {
      success: true,
      message: '🔁 Looping Agent executed 5 identical tool calls! Triggered dynamic anomaly detector.',
    }
  }

  return { success: false, message: 'Unknown scenario' }
}

// ============================================================================
// Live Agent Lab: real-world API calls routed through the AgentShield gateway
// ============================================================================

export type LiveProviderMode = 'live' | 'simulated' | 'unconfigured' | 'offline'

export interface LiveProvider {
  id: string
  name: string
  category: string
  auth_required: boolean
  configured: boolean
  mode: LiveProviderMode
  detail: string
}

export interface LiveProvidersResponse {
  providers: LiveProvider[]
  generated_at: string
}

export type LiveScenarioExecutionMode = 'live' | 'simulated' | 'blocked'

export interface LiveScenarioSpec {
  id: string
  name: string
  category: string
  description: string
  target_api: string
  expected_verdict: string
  icon: string
  provider_id: string | null
  execution_mode: LiveScenarioExecutionMode
}

export interface LiveAgentResult {
  status: string
  scenario_id?: string | null
  run_id: string
  session_id: string
  tool_name: string
  policy_decision: 'allow' | 'deny' | 'require_approval' | string
  policy_rule_id: string | null
  reason: string | null
  approval_id: string | null
  latency_ms: number
  cost_usd: number
  redactions_applied: number
  provider_id: string | null
  execution_mode: string
  api_response: any
  prompt: string | null
  scenario_hint?: string | null
}

export interface LiveModelResult {
  model: string
  provider: string
  execution_mode: string
  latency_ms: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  response: string
  policy_decision: string
}

export interface LiveModelComparisonSummary {
  cheaper_model: string | null
  faster_model: string | null
  cost_delta_usd: number
  latency_delta_ms: number
}

export interface LiveCompareModelsResponse {
  prompt: string
  results: LiveModelResult[]
  comparison: LiveModelComparisonSummary
}

export async function fetchLiveProviders(): Promise<LiveProvidersResponse> {
  const apiKey = getApiKey()
  const res = await fetch(`${API_BASE}/live-agent/providers`, {
    headers: { 'X-API-Key': apiKey },
  })
  if (!res.ok) {
    throw new Error(`Failed to fetch live providers: HTTP ${res.status}`)
  }
  return res.json()
}

export async function fetchLiveScenarios(): Promise<LiveScenarioSpec[]> {
  const apiKey = getApiKey()
  const res = await fetch(`${API_BASE}/live-agent/scenarios`, {
    headers: { 'X-API-Key': apiKey },
  })
  if (!res.ok) {
    throw new Error(`Failed to fetch live scenarios: HTTP ${res.status}`)
  }
  return res.json()
}

export async function executeLiveScenario(scenarioId: string, customParam?: string): Promise<LiveAgentResult> {
  const apiKey = getApiKey()
  const res = await fetch(`${API_BASE}/live-agent/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({ scenario: scenarioId, custom_param: customParam || undefined }),
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to execute live scenario: HTTP ${res.status}`)
  }
  return res.json()
}

export async function invokeLiveTool(
  toolName: string,
  toolArgs: Record<string, any>,
  prompt?: string,
  scenarioHint?: string
): Promise<LiveAgentResult> {
  const apiKey = getApiKey()
  const res = await fetch(`${API_BASE}/live-agent/invoke`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({
      tool_name: toolName,
      tool_args: toolArgs,
      prompt: prompt || undefined,
      scenario_hint: scenarioHint || undefined,
    }),
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to invoke live tool: HTTP ${res.status}`)
  }
  return res.json()
}

export async function compareLiveModels(prompt: string, modelA: string, modelB: string): Promise<LiveCompareModelsResponse> {
  const apiKey = getApiKey()
  const res = await fetch(`${API_BASE}/live-agent/compare-models`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({ prompt, model_a: modelA, model_b: modelB }),
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    throw new Error(errData.detail || `Failed to compare live models: HTTP ${res.status}`)
  }
  return res.json()
}



