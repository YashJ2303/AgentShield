import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import React from 'react'
import { LiveAgentLab } from '../components/LiveAgentLab'

const PROVIDERS_PAYLOAD = {
  providers: [
    {
      id: 'github',
      name: 'GitHub Public REST API',
      category: 'Public API (Zero-Auth)',
      auth_required: false,
      configured: true,
      mode: 'live',
      detail: 'Unauthenticated; 60 requests/hour rate limit.',
    },
    {
      id: 'stripe',
      name: 'Stripe Payments API',
      category: 'Fintech (Credential)',
      auth_required: true,
      configured: false,
      mode: 'simulated',
      detail: 'No credentials present; high-fidelity local simulation.',
    },
    {
      id: 'twilio',
      name: 'Twilio SMS',
      category: 'Messaging (Credential)',
      auth_required: true,
      configured: false,
      mode: 'unconfigured',
      detail: 'Missing account SID and auth token.',
    },
    {
      id: 'openai',
      name: 'OpenAI Chat Completions',
      category: 'LLM Provider',
      auth_required: true,
      configured: true,
      mode: 'offline',
      detail: 'Credentials present but network unreachable.',
    },
  ],
  generated_at: '2026-10-21T12:00:00+00:00',
}

const SCENARIOS_PAYLOAD = [
  {
    id: 'weather_live',
    name: 'Live Weather Query',
    category: 'Public REST API (Zero-Auth)',
    description: 'Query the open-meteo API for a real forecast.',
    target_api: 'https://api.open-meteo.com/v1/forecast',
    expected_verdict: 'allow',
    icon: '🌦️',
    provider_id: 'open_meteo',
    execution_mode: 'live',
  },
  {
    id: 'stripe_charge_block',
    name: 'Blocked Stripe Charge',
    category: 'Fintech Guardrail',
    description: 'Attempt a charge that policy should deny.',
    target_api: 'https://api.stripe.com/v1/charges',
    expected_verdict: 'deny',
    icon: '💳',
    provider_id: 'stripe',
    execution_mode: 'blocked',
  },
]

const EXECUTE_RESULT = {
  status: 'completed',
  scenario_id: 'weather_live',
  run_id: 'live-weather_live-ab12cd',
  session_id: 'sess-live-real-world-apis',
  tool_name: 'weather_tool',
  policy_decision: 'allow',
  policy_rule_id: 'allow_weather_read',
  reason: "Matched policy rule 'allow_weather_read'",
  approval_id: null,
  latency_ms: 412,
  cost_usd: 0.0,
  redactions_applied: 0,
  provider_id: 'open_meteo',
  execution_mode: 'live',
  api_response: { temperature_2m: 21.4 },
  prompt: 'Get the current weather for Lisbon.',
}

const COMPARE_RESULT = {
  prompt: 'Compare these two policies.',
  results: [
    {
      model: 'gemini-2.5-flash',
      provider: 'gemini',
      execution_mode: 'simulated',
      latency_ms: 130,
      prompt_tokens: 14,
      completion_tokens: 30,
      total_tokens: 44,
      cost_usd: 0.000011,
      response: 'Gemini says the second policy is stricter.',
      policy_decision: 'allow',
    },
    {
      model: 'gpt-4o',
      provider: 'openai',
      execution_mode: 'simulated',
      latency_ms: 770,
      prompt_tokens: 14,
      completion_tokens: 42,
      total_tokens: 56,
      cost_usd: 0.000291,
      response: 'GPT-4o agrees with the assessment.',
      policy_decision: 'deny',
    },
  ],
  comparison: {
    cheaper_model: 'gemini-2.5-flash',
    faster_model: 'gemini-2.5-flash',
    cost_delta_usd: 0.00028,
    latency_delta_ms: 640,
  },
}

type FetchCall = [input: string, init?: RequestInit]

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => data,
  } as unknown as Response
}

describe('LiveAgentLab Component', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    // Route-aware default mock covering every live-agent endpoint
    fetchMock.mockImplementation(async (url: string) => {
      const u = String(url)
      if (u.includes('/live-agent/providers')) return jsonResponse(PROVIDERS_PAYLOAD)
      if (u.includes('/live-agent/scenarios')) return jsonResponse(SCENARIOS_PAYLOAD)
      if (u.includes('/live-agent/execute')) return jsonResponse(EXECUTE_RESULT)
      if (u.includes('/live-agent/invoke')) return jsonResponse(EXECUTE_RESULT)
      if (u.includes('/live-agent/compare-models')) return jsonResponse(COMPARE_RESULT)
      return jsonResponse({})
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders provider cards with color-coded modes and auth indicators', async () => {
    render(<LiveAgentLab />)

    await waitFor(() => {
      expect(screen.getByTestId('provider-card-github')).toBeInTheDocument()
      expect(screen.getByTestId('provider-card-stripe')).toBeInTheDocument()
      expect(screen.getByTestId('provider-card-twilio')).toBeInTheDocument()
      expect(screen.getByTestId('provider-card-openai')).toBeInTheDocument()
    })

    expect(screen.getByTestId('provider-mode-github')).toHaveTextContent('LIVE')
    expect(screen.getByTestId('provider-mode-stripe')).toHaveTextContent('SIMULATED')
    expect(screen.getByTestId('provider-mode-twilio')).toHaveTextContent('UNCONFIGURED')
    expect(screen.getByTestId('provider-mode-openai')).toHaveTextContent('OFFLINE')

    // Auth indicators
    const githubCard = screen.getByTestId('provider-card-github')
    expect(within(githubCard).getByText('Zero-auth')).toBeInTheDocument()
    const stripeCard = screen.getByTestId('provider-card-stripe')
    expect(within(stripeCard).getByText('Auth required')).toBeInTheDocument()
  })

  it('renders scenario cards with target API and expected verdict', async () => {
    render(<LiveAgentLab />)

    await waitFor(() => {
      expect(screen.getByTestId('scenario-card-weather_live')).toBeInTheDocument()
      expect(screen.getByTestId('scenario-card-stripe_charge_block')).toBeInTheDocument()
    })

    expect(screen.getByText('Live Weather Query')).toBeInTheDocument()
    expect(screen.getByText('https://api.open-meteo.com/v1/forecast')).toBeInTheDocument()
    expect(screen.getByTestId('scenario-mode-weather_live')).toHaveTextContent('LIVE')
    expect(screen.getByTestId('scenario-mode-stripe_charge_block')).toHaveTextContent('BLOCKED')
  })

  it('runs a scenario on click, POSTs to execute endpoint, and renders the decision badge', async () => {
    render(<LiveAgentLab />)

    const runBtn = await screen.findByTestId('btn-run-scenario-weather_live')
    fireEvent.click(runBtn)

    await waitFor(() => {
      expect(screen.getByTestId('scenario-result-weather_live')).toBeInTheDocument()
    })

    // Verify the execute POST happened with the right body
    const executeCall = (fetchMock.mock.calls as FetchCall[]).find(
      ([url]) => String(url).includes('/live-agent/execute')
    )
    expect(executeCall).toBeTruthy()
    expect(executeCall![1]?.method).toBe('POST')
    const body = JSON.parse(String(executeCall![1]?.body))
    expect(body.scenario).toBe('weather_live')

    // Decision badge rendered
    expect(screen.getByTestId('scenario-result-weather_live-decision')).toHaveTextContent('ALLOW')
    expect(screen.getByTestId('scenario-result-weather_live-mode')).toHaveTextContent('LIVE')
  })

  it('shows an inline JSON error and does NOT fetch when tool args are invalid JSON', async () => {
    render(<LiveAgentLab />)

    // Wait for the initial provider/scenario fetches to settle
    await screen.findByTestId('btn-invoke-tool')
    await waitFor(() => expect(screen.getByTestId('provider-card-github')).toBeInTheDocument())
    fetchMock.mockClear()

    fireEvent.change(screen.getByTestId('textarea-tool-args'), {
      target: { value: '{ this is not valid json' },
    })
    fireEvent.click(screen.getByTestId('btn-invoke-tool'))

    expect(screen.getByTestId('tool-json-error')).toHaveTextContent('valid JSON')
    // No network call was made for the invalid payload
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits the model comparator and renders per-model rows and comparison summary', async () => {
    render(<LiveAgentLab />)

    const compareBtn = await screen.findByTestId('btn-compare-models')
    fireEvent.click(compareBtn)

    await waitFor(() => {
      expect(screen.getByTestId('compare-results')).toBeInTheDocument()
    })

    // Verify the POST body
    const compareCall = (fetchMock.mock.calls as FetchCall[]).find(
      ([url]) => String(url).includes('/live-agent/compare-models')
    )
    expect(compareCall).toBeTruthy()
    const body = JSON.parse(String(compareCall![1]?.body))
    expect(body.model_a).toBe('gemini-2.5-flash')
    expect(body.model_b).toBe('gpt-4o')
    expect(typeof body.prompt).toBe('string')

    // Per-model rows with metrics
    expect(screen.getByTestId('compare-row-gemini-2.5-flash')).toHaveTextContent('130 ms')
    expect(screen.getByTestId('compare-row-gpt-4o')).toHaveTextContent('770 ms')

    // Comparison summary
    expect(screen.getByText(/Cheaper:/)).toBeInTheDocument()
    expect(screen.getByText(/Faster:/)).toBeInTheDocument()
    expect(screen.getByText(/Δcost/)).toBeInTheDocument()
    expect(screen.getByText(/Δlatency 640 ms/)).toBeInTheDocument()
  })

  it('dispatches a free-form tool invocation and renders the verdict', async () => {
    render(<LiveAgentLab />)

    const invokeBtn = await screen.findByTestId('btn-invoke-tool')
    fireEvent.change(screen.getByTestId('input-tool-name'), { target: { value: 'github_tool' } })
    fireEvent.click(invokeBtn)

    await waitFor(() => {
      expect(screen.getByTestId('tool-invoke-result')).toBeInTheDocument()
    })

    const invokeCall = (fetchMock.mock.calls as FetchCall[]).find(
      ([url]) => String(url).includes('/live-agent/invoke')
    )
    expect(invokeCall).toBeTruthy()
    const body = JSON.parse(String(invokeCall![1]?.body))
    expect(body.tool_name).toBe('github_tool')
    expect(body.tool_args).toEqual({ owner: 'pallets', repo: 'flask' })

    expect(screen.getByTestId('tool-invoke-result-decision')).toHaveTextContent('ALLOW')
  })
})
