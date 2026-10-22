import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CyberArcTopology } from '../components/CyberArcTopology'
import * as api from '../services/api'

vi.mock('../services/api', () => ({
  fetchAnalyticsBreakdown: vi.fn(),
  fetchRuns: vi.fn(),
  fetchLiveProviders: vi.fn(),
}))

describe('CyberArcTopology Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.fetchAnalyticsBreakdown).mockResolvedValue({
      models: [
        {
          model: 'gpt-4o',
          cohort_size: 42,
          completion_rate: 0.95,
          total_cost: 0.25,
          cost_per_run: 0.005,
          cost_per_successful_task: 0.005,
          p50_latency_ms: 600,
          p95_latency_ms: 1200,
          avg_latency_ms: 700,
          total_tokens: 15000,
        },
      ],
      tools: [
        {
          tool_name: 'stripe_payment',
          cohort_size: 18,
          error_count: 2,
          error_rate: 0.11,
          retry_count: 0,
          retry_rate: 0.0,
          p50_latency_ms: 450,
          p95_latency_ms: 900,
          avg_latency_ms: 500,
          policy_block_count: 5,
          top_block_rule: 'block_large_payment',
        },
        {
          tool_name: 'sql_query',
          cohort_size: 30,
          error_count: 0,
          error_rate: 0.0,
          retry_count: 0,
          retry_rate: 0.0,
          p50_latency_ms: 120,
          p95_latency_ms: 300,
          avg_latency_ms: 150,
          policy_block_count: 0,
          top_block_rule: null,
        },
      ],
      prompt_versions: [],
      time_series: [],
    })

    vi.mocked(api.fetchRuns).mockResolvedValue({
      total: 2,
      runs: [
        {
          id: 'run-001',
          outcome: 'success',
          model: 'gpt-4o',
          total_cost: 0.004,
          total_tokens: 1200,
          latency_ms: 820,
          step_count: 4,
        },
        {
          id: 'run-002',
          outcome: 'blocked',
          model: 'claude-3-5-sonnet',
          total_cost: 0.001,
          total_tokens: 450,
          latency_ms: 15,
          step_count: 1,
        },
      ],
    })

    vi.mocked(api.fetchLiveProviders).mockResolvedValue({
      providers: [
        {
          id: 'weather_tool',
          name: 'Open-Meteo',
          category: 'weather',
          auth_required: false,
          configured: true,
          mode: 'live',
          detail: 'Current temperature and weather forecasts',
        },
      ],
      generated_at: new Date().toISOString(),
    })
  })

  it('renders the CyberArc header, status HUD, and filter buttons', async () => {
    render(<CyberArcTopology />)

    expect(screen.getByText(/CYBERARC/i)).toBeInTheDocument()
    expect(screen.getByText(/3D SECURITY TOPOLOGY/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ALL NODES/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ATTACK HOTSPOTS/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /LIVE NETWORK/i })).toBeInTheDocument()

    await waitFor(() => {
      expect(api.fetchAnalyticsBreakdown).toHaveBeenCalled()
      expect(api.fetchRuns).toHaveBeenCalled()
    })
  })

  it('gracefully provides 2D grid representation in JSDOM / non-WebGL environments', async () => {
    render(<CyberArcTopology />)

    // In JSDOM getContext('webgl') returns null, so the component falls back to the clean 2D node card view
    await waitFor(() => {
      expect(screen.getByText(/AgentShield Gateway/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/SQLGlot AST Guard/i)).toBeInTheDocument()
    expect(screen.getByText(/Stripe Payment Gateway/i)).toBeInTheDocument()
  })

  it('allows switching filter modes and filtering nodes', async () => {
    render(<CyberArcTopology />)

    await waitFor(() => {
      expect(screen.getByText(/Stripe Payment Gateway/i)).toBeInTheDocument()
    })

    // Click "ATTACK HOTSPOTS"
    const attackFilter = screen.getByRole('button', { name: /ATTACK HOTSPOTS/i })
    fireEvent.click(attackFilter)
    expect(attackFilter).toHaveClass('active')

    // Click "LIVE NETWORK"
    const liveFilter = screen.getByRole('button', { name: /LIVE NETWORK/i })
    fireEvent.click(liveFilter)
    expect(liveFilter).toHaveClass('active')
  })

  it('opens inspector drawer when a node card is clicked', async () => {
    render(<CyberArcTopology />)

    await waitFor(() => {
      expect(screen.getByText(/Stripe Payment Gateway/i)).toBeInTheDocument()
    })

    // Click on the Stripe Payment Gateway card
    const stripeNode = screen.getByTestId('node-tool-stripe_payment')
    expect(stripeNode).toBeInTheDocument()
    fireEvent.click(stripeNode)

    // Inspector drawer should be visible with node details
    await waitFor(() => {
      const inspector = screen.getByTestId('cyberarc-node-inspector')
      expect(inspector).toBeInTheDocument()
      expect(inspector).toHaveTextContent(/Stripe Payment Gateway/i)
      expect(inspector).toHaveTextContent(/Deflected Attacks/i)
    })

    // Close the drawer using test id
    const closeBtn = screen.getByTestId('btn-close-inspector')
    fireEvent.click(closeBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('cyberarc-node-inspector')).not.toBeInTheDocument()
    })
  })
})
