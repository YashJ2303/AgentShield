import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { ReplayView } from '../components/ReplayView'
import * as api from '../services/api'
import { ReplayRecord, ReplayListItem } from '../types'

describe('ReplayView Component', () => {
  const mockReplayList: ReplayListItem[] = [
    {
      id: 'replay-test-12345',
      original_run_id: 'run-orig-abcde',
      target_model: 'claude-3-5-sonnet',
      target_prompt_version: 'v2-strict',
      fidelity_score: 0.85,
      cache_miss_rate: 0.0,
      outcome: 'success',
      created_at: new Date().toISOString(),
    },
  ]

  const mockReplayDetail: any = {
    replay_id: 'replay-test-12345',
    original_run_id: 'run-orig-abcde',
    target_model: 'claude-3-5-sonnet',
    target_prompt_version: 'v2-strict',
    candidate_policy_version_id: null,
    outcome: 'success',
    fidelity_score: 0.85,
    cache_miss_rate: 0.0,
    fidelity_spread: 0.0,
    regression_detected: false,
    regression_reasons: [],
    sample_results: [
      {
        sample_index: 1,
        fidelity_score: 0.85,
        s_tool: 1.0,
        s_args: 0.5,
        s_outcome: 1.0,
        cache_miss_rate: 0.0,
        replayed_outcome: 'success',
        replayed_tools: ['database_query'],
      },
    ],
    trajectory_diff: [
      {
        step_number: 1,
        tool_name_recorded: 'database_query',
        tool_name_replayed: 'database_query',
        tool_match: true,
        args_recorded: {
          sql: "SELECT * FROM users WHERE note = '<script>alert(\"xss\")</script>'",
        },
        args_replayed: {
          sql: "SELECT * FROM users WHERE note = '<img src=x onerror=alert(1)>'",
        },
        arg_similarity: 0.5,
        output_recorded: { rows: [{ id: 1, name: 'Alice' }] },
        output_replayed: { rows: [{ id: 1, name: 'Alice' }] },
        policy_decision_recorded: 'allow',
        policy_decision_replayed: 'allow',
        is_cache_miss: false,
      },
    ],
    sensitivity_table: [
      { threshold: 0.75, fidelity_score: 0.85, cache_miss_rate: 0.0, cache_misses: 0, total_calls: 1 },
      { threshold: 0.85, fidelity_score: 0.85, cache_miss_rate: 0.0, cache_misses: 0, total_calls: 1 },
      { threshold: 0.95, fidelity_score: 0.40, cache_miss_rate: 1.0, cache_misses: 1, total_calls: 1 },
    ],
    created_at: new Date().toISOString(),
  }

  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'fetchReplays').mockResolvedValue(mockReplayList)
    vi.spyOn(api, 'fetchReplayDetail').mockResolvedValue(mockReplayDetail)
  })

  it('renders executive metrics, sensitivity table, and trajectory diff', async () => {
    render(<ReplayView />)

    await waitFor(() => {
      expect(screen.getByText('Incident Replay Engine (RQ2)')).toBeInTheDocument()
      expect(screen.getAllByText('85.0%').length).toBeGreaterThan(0)
      expect(screen.getByText('CLEAN / REPRODUCED')).toBeInTheDocument()
    })

    // Verify sensitivity table
    expect(screen.getByText('Fuzzy Matching Sensitivity Analysis (Thresholds 0.75, 0.85, 0.95)')).toBeInTheDocument()
    expect(screen.getByText('0.85 (Default)')).toBeInTheDocument()

    // Verify trajectory diff steps
    expect(screen.getByText('Step #1')).toBeInTheDocument()
    expect(screen.getByText('TOOL MATCH')).toBeInTheDocument()
  })

  it('renders hostile script and img tags strictly as plain text', async () => {
    render(<ReplayView />)

    await waitFor(() => {
      expect(screen.getByText('Incident Replay Engine (RQ2)')).toBeInTheDocument()
      expect(screen.queryByText('CLEAN / REPRODUCED')).toBeInTheDocument()
    })

    // Wait for payload content to appear
    await waitFor(() => {
      const payloadElements = screen.getAllByTestId('safe-payload-content')
      expect(payloadElements.length).toBeGreaterThan(0)
    })

    const payloadElements = screen.getAllByTestId('safe-payload-content')
    const textContentCombined = payloadElements.map((el) => el.textContent).join(' ')
    expect(textContentCombined).toContain('<script>alert(\\"xss\\")</script>')
    expect(textContentCombined).toContain('<img src=x onerror=alert(1)>')

    // Confirm that NO executable script element was injected into DOM
    const scripts = document.querySelectorAll('script')
    const hasInjectedScript = Array.from(scripts).some((s) => s.textContent?.includes('alert("xss")'))
    expect(hasInjectedScript).toBe(false)
  })
})
