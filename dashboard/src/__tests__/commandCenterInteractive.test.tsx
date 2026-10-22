import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CommandCenter } from '../components/CommandCenter'
import * as api from '../services/api'

/**
 * These tests pin the Command Center to the gateway payload contract:
 * every number rendered must come from the live API responses, and every
 * interactive control must reach the navigation/search surface it advertises.
 */

const SUMMARY = {
  total_runs: 50,
  successful_runs: 45,
  failed_runs: 2,
  blocked_runs: 3,
  timed_out_runs: 0,
  task_completion_rate: 0.9,
  total_cost: 0.0123,
  cost_per_run: 0.000246,
  cost_per_successful_task: 0.000273,
  total_tokens: 1200,
  prompt_tokens: 700,
  completion_tokens: 500,
  avg_tokens_per_run: 24,
  p50_latency_ms: 0,
  p95_latency_ms: 9935.55,
  avg_latency_ms: 1331.64,
  total_tool_calls: 66,
  tool_error_rate: 0.2,
}

const TOOLS = [
  {
    tool_name: 'sql_query',
    cohort_size: 21,
    error_count: 0,
    error_rate: 0,
    retry_count: 0,
    retry_rate: 0,
    p50_latency_ms: 1,
    p95_latency_ms: 2,
    avg_latency_ms: 1,
    policy_block_count: 8,
    top_block_rule: 'allow_read_queries',
  },
  {
    tool_name: 'crawl_page',
    cohort_size: 30,
    error_count: 0,
    error_rate: 0,
    retry_count: 0,
    retry_rate: 0,
    p50_latency_ms: 40,
    p95_latency_ms: 90,
    avg_latency_ms: 45,
    policy_block_count: 0,
    top_block_rule: null,
  },
  {
    tool_name: 'file_tool',
    cohort_size: 6,
    error_count: 0,
    error_rate: 0,
    retry_count: 0,
    retry_rate: 0,
    p50_latency_ms: 2,
    p95_latency_ms: 3,
    avg_latency_ms: 2,
    policy_block_count: 6,
    top_block_rule: 'sandbox_filesystem',
  },
]

const RUNS = [
  {
    id: 'run-abc123def',
    task_id: 'sql injection probe',
    agent_label: 'sql-agent',
    model: 'host-local',
    outcome: 'blocked',
    total_cost: 0,
    total_tokens: 10,
    latency_ms: 12,
    step_count: 2,
  },
  {
    id: 'run-def456ghi',
    task_id: 'github repo lookup',
    agent_label: 'research-agent',
    model: 'host-local',
    outcome: 'success',
    total_cost: 0,
    total_tokens: 20,
    latency_ms: 120,
    step_count: 3,
  },
]

const ANOMALIES = [
  { type: 'repeated_tool_loop', severity: 'high', message: 'sql_query repeated 5 times', run_id: 'run-abc123def' },
  { type: 'latency_outlier', severity: 'medium', message: 'p95 latency outlier' },
  { type: 'cost_spike', severity: 'medium', message: 'cost spike' },
  { type: 'retry_storm', severity: 'medium', message: 'retry storm' },
  { type: 'error_rate', severity: 'medium', message: 'error rate elevated' },
  { type: 'tool_loop', severity: 'medium', message: 'tool loop' },
]

vi.mock('../services/api', () => ({
  decideApproval: vi.fn(),
  fetchActivePolicy: vi.fn(),
  fetchApprovals: vi.fn(),
  fetchAnalyticsSummary: vi.fn(),
  fetchAnomalies: vi.fn(),
  fetchAnalyticsBreakdown: vi.fn(),
  fetchGatewayHealth: vi.fn(),
  fetchRuns: vi.fn(),
  triggerLiveDemoScenario: vi.fn(),
}))

const mockApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks()
  mockApi.fetchAnalyticsSummary.mockResolvedValue(SUMMARY as any)
  mockApi.fetchApprovals.mockResolvedValue([])
  mockApi.fetchAnomalies.mockResolvedValue(ANOMALIES as any)
  mockApi.fetchAnalyticsBreakdown.mockResolvedValue({
    models: [],
    tools: TOOLS,
    prompt_versions: [],
    time_series: [],
  } as any)
  mockApi.fetchRuns.mockImplementation((params: any) => {
    const runs = params?.search
      ? RUNS.filter((r) => `${r.id} ${r.task_id}`.toLowerCase().includes(String(params.search).toLowerCase()))
      : RUNS
    return Promise.resolve({ total: runs.length, runs } as any)
  })
  mockApi.fetchActivePolicy.mockResolvedValue({ version_number: 1, rule_count: 13, is_active: true })
  mockApi.fetchGatewayHealth.mockResolvedValue({ status: 'healthy', database: 'connected' } as any)
  mockApi.decideApproval.mockResolvedValue({ status: 'approved' } as any)
})

describe('CommandCenter live interactivity', () => {
  it('draws the topology from live counters and drills into blocked runs', async () => {
    const onNavigateToRuns = vi.fn()
    render(<CommandCenter onSelectRun={() => {}} onNavigateToRuns={onNavigateToRuns} />)

    const blockedNode = await screen.findByTestId('topo-node-blocked')
    await waitFor(() => expect(blockedNode.getAttribute('aria-label')).toBe('Blocked: 14'))
    expect(screen.getByTestId('topo-node-allowed').getAttribute('aria-label')).toBe('Allowed: 52')
    expect(screen.getByTestId('topo-node-guard').getAttribute('aria-label')).toBe('AST Guard: v1 · 13 rules')

    fireEvent.click(blockedNode)
    fireEvent.click(await screen.findByTestId('topo-detail-action'))
    expect(onNavigateToRuns).toHaveBeenCalledWith({ outcome: 'blocked' })
  })

  it('navigates from the metric cards to the matching views', async () => {
    const onNavigateToRuns = vi.fn()
    const onNavigateToAnalytics = vi.fn()
    render(
      <CommandCenter
        onSelectRun={() => {}}
        onNavigateToRuns={onNavigateToRuns}
        onNavigateToAnalytics={onNavigateToAnalytics}
      />
    )

    fireEvent.click(await screen.findByTestId('metric-card-tool-calls'))
    expect(onNavigateToAnalytics).toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('metric-card-denied'))
    expect(onNavigateToRuns).toHaveBeenCalledWith({ outcome: 'blocked' })
  })

  it('re-queries the window when the time range changes', async () => {
    render(<CommandCenter onSelectRun={() => {}} />)

    await waitFor(() => expect(mockApi.fetchAnalyticsSummary).toHaveBeenCalled())
    const firstArgs = mockApi.fetchAnalyticsSummary.mock.calls[0][0] as any
    expect(firstArgs?.start_date).toBeTruthy()

    fireEvent.click(screen.getByTestId('time-range-pill'))
    fireEvent.click(screen.getByTestId('time-range-option-all'))

    await waitFor(() => {
      const lastArgs = mockApi.fetchAnalyticsSummary.mock.calls.at(-1)?.[0] as any
      expect(lastArgs).toBeUndefined()
    })

    fireEvent.click(screen.getByTestId('time-range-pill'))
    fireEvent.click(screen.getByTestId('time-range-option-7d'))

    await waitFor(() => {
      const lastArgs = mockApi.fetchAnalyticsSummary.mock.calls.at(-1)?.[0] as any
      expect(lastArgs?.start_date).toBeTruthy()
    })
  })

  it('searches runs against the gateway and opens the selected run', async () => {
    const onSelectRun = vi.fn()
    render(<CommandCenter onSelectRun={onSelectRun} />)

    const input = await screen.findByTestId('cc-search-input')
    fireEvent.change(input, { target: { value: 'sql' } })

    const result = await screen.findByTestId('cc-search-result-run-abc123def', {}, { timeout: 2000 })
    fireEvent.click(result)
    expect(onSelectRun).toHaveBeenCalledWith('run-abc123def')
  })

  it('opens the notification panel with live queue counts', async () => {
    const onNavigateToRuns = vi.fn()
    render(<CommandCenter onSelectRun={() => {}} onNavigateToRuns={onNavigateToRuns} />)

    fireEvent.click(await screen.findByTestId('cc-notifications-btn'))
    const panel = await screen.findByTestId('cc-notifications-panel')
    expect(panel.textContent).toContain('0 pending approvals')
    expect(panel.textContent).toContain('3 runs blocked')

    const blockedItem = within(panel).getByRole('button', { name: /3 runs blocked/ })
    fireEvent.click(blockedItem)
    expect(onNavigateToRuns).toHaveBeenCalledWith({ outcome: 'blocked' })
  })

  it('exposes the transparent health-score composition', async () => {
    render(<CommandCenter onSelectRun={() => {}} />)

    const gauge = await screen.findByTestId('health-gauge')
    await waitFor(() => expect(gauge.textContent).toContain('78'))
    expect(gauge.textContent).toContain('Operational')

    fireEvent.click(gauge)
    const breakdown = await screen.findByTestId('health-score-breakdown')
    expect(breakdown.textContent).toContain('Allow rate (weight 60)')
    expect(breakdown.textContent).toContain('56/60')
    expect(breakdown.textContent).toContain('10/10')
    expect(breakdown.textContent).toContain('12/15')
    expect(breakdown.textContent).toContain('no model is involved')
  })

  it('shows real p50/p95 latency instead of the old zero-overhead claim', async () => {
    render(<CommandCenter onSelectRun={() => {}} />)

    expect(await screen.findByText(/p95 9936ms · avg 1332ms · n=50/)).toBeInTheDocument()
    expect(screen.queryByText(/Zero LLM overhead/)).toBeNull()
  })

  it('renders no fabricated score when the gateway has no telemetry', async () => {
    mockApi.fetchAnalyticsSummary.mockResolvedValue({
      ...SUMMARY,
      total_runs: 0,
      blocked_runs: 0,
      total_tool_calls: 0,
      p50_latency_ms: 0,
      p95_latency_ms: 0,
      avg_latency_ms: 0,
    } as any)
    mockApi.fetchAnomalies.mockResolvedValue([])
    mockApi.fetchRuns.mockResolvedValue({ total: 0, runs: [] } as any)

    render(<CommandCenter onSelectRun={() => {}} />)

    const gauge = await screen.findByTestId('health-gauge')
    await waitFor(() => expect(gauge.textContent).toContain('No telemetry'))
    expect(gauge.textContent).toContain('—')
    expect(gauge.textContent).not.toContain('92')
  })
})
