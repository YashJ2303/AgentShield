import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import React from 'react'
import { AnalyticsDashboard } from '../components/AnalyticsDashboard'
import * as api from '../services/api'
import {
  AnalyticsSummary,
  AnalyticsBreakdown,
  AnomalyItem,
  ModelComparisonResponse,
} from '../types'

describe('AnalyticsDashboard Component', () => {
  const mockSummary: AnalyticsSummary = {
    total_runs: 50,
    successful_runs: 45,
    failed_runs: 5,
    blocked_runs: 3,
    timed_out_runs: 1,
    task_completion_rate: 0.9,
    total_cost: 1.254,
    cost_per_run: 0.02508,
    cost_per_successful_task: 0.02787,
    total_tokens: 125000,
    prompt_tokens: 100000,
    completion_tokens: 25000,
    avg_tokens_per_run: 2500,
    p50_latency_ms: 850.5,
    p95_latency_ms: 2450.0,
    avg_latency_ms: 920.0,
    total_tool_calls: 120,
    tool_error_rate: 0.0417,
    retry_rate: 0.025,
    policy_block_rate: 0.06,
    failure_categories: {
      policy_block: 3,
      timeout: 1,
      tool_error: 1,
    },
  }

  const mockBreakdown: any = {
    models: [
      {
        model: 'gpt-4o',
        sample_size: 30,
        completion_rate: 0.9333,
        total_cost: 0.95,
        cost_per_run: 0.0316,
        cost_per_successful_task: 0.0339,
        p50_latency_ms: 950.0,
        p95_latency_ms: 2200.0,
        avg_latency_ms: 950.0,
        total_tokens: 90000,
      },
      {
        model: 'claude-3-5-sonnet',
        sample_size: 20,
        completion_rate: 0.85,
        total_cost: 0.304,
        cost_per_run: 0.0152,
        cost_per_successful_task: 0.0178,
        p50_latency_ms: 875.0,
        p95_latency_ms: 2100.0,
        avg_latency_ms: 875.0,
        total_tokens: 35000,
      },
    ],
    tools: [
      {
        tool_name: 'bash_exec',
        sample_size: 60,
        error_count: 2,
        error_rate: 0.0333,
        retry_count: 1,
        retry_rate: 0.0167,
        p50_latency_ms: 120.0,
        p95_latency_ms: 350.0,
        avg_latency_ms: 120.0,
        policy_block_count: 3,
      },
      {
        tool_name: 'web_search',
        sample_size: 40,
        error_count: 1,
        error_rate: 0.025,
        retry_count: 0,
        retry_rate: 0.0,
        p50_latency_ms: 450.0,
        p95_latency_ms: 900.0,
        avg_latency_ms: 450.0,
        policy_block_count: 0,
      },
    ],
    prompt_versions: [
      {
        prompt_version: 'v1.0',
        sample_size: 35,
        completion_rate: 0.8857,
        total_cost: 0.85,
        cost_per_run: 0.0242,
        cost_per_successful_task: 0.0274,
        p50_latency_ms: 910.0,
        p95_latency_ms: 2150.0,
        avg_latency_ms: 910.0,
      },
    ],
    time_series: [
      {
        date: '2026-10-15',
        sample_size: 20,
        total_cost: 0.52,
        avg_latency_ms: 880.0,
        success_rate: 0.9,
      },
      {
        date: '2026-10-16',
        sample_size: 30,
        total_cost: 0.734,
        avg_latency_ms: 940.0,
        success_rate: 0.9,
      },
    ],
  }

  const mockAnomalies: any = [
    {
      id: 'anom-loop-1',
      run_id: 'run-998877',
      type: 'repeated_tool_loop',
      severity: 'critical',
      metric: 'consecutive_calls',
      value: 4,
      sample_size: 12,
      baseline_reference: 'Max allowable identical consecutive calls is 2',
      message: "Tool 'bash_exec' invoked 4 times consecutively with identical arguments.",
      detected_at: new Date().toISOString(),
    },
    {
      id: 'anom-outlier-1',
      run_id: 'run-112233',
      type: 'latency_outlier',
      severity: 'high',
      metric: 'latency_ms',
      value: 12500,
      sample_size: 50,
      baseline_reference: 'Q3=1200ms, IQR=400ms, Threshold=1800ms',
      message: 'Run run-1122 exhibited statistical outlier in Latency (ms): 12500 exceeds upper bound 1800.00.',
      detected_at: new Date().toISOString(),
    },
    {
      id: 'anom-xss-test',
      run_id: 'run-xss-44',
      type: 'repeated_tool_loop',
      severity: 'critical',
      metric: 'xss_payload',
      value: 3,
      sample_size: 5,
      baseline_reference: null,
      message: "<script>alert('xss_anomaly')</script><img src=x onerror=alert(2)>",
      detected_at: new Date().toISOString(),
    },
  ]

  const mockComparison: any = {
    model_a: 'gpt-4o',
    model_b: 'claude-3-5-sonnet',
    model_a_sample_size: 30,
    model_b_sample_size: 20,
    metrics: [
      {
        metric_name: 'Task Completion Rate',
        model_a_value: 0.9333,
        model_b_value: 0.85,
        diff_percentage: -8.93,
        winner: 'model_a',
      },
      {
        metric_name: 'Cost per Run ($)',
        model_a_value: 0.0316,
        model_b_value: 0.0152,
        diff_percentage: -51.9,
        winner: 'model_b',
      },
    ],
  }

  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'fetchAnalyticsSummary').mockResolvedValue(mockSummary)
    vi.spyOn(api, 'fetchAnalyticsBreakdown').mockResolvedValue(mockBreakdown)
    vi.spyOn(api, 'fetchAnomalies').mockResolvedValue(mockAnomalies)
    vi.spyOn(api, 'fetchModelComparison').mockResolvedValue(mockComparison)
  })

  it('renders summary KPI metrics with sample sizes and unit costs correctly', async () => {
    render(<AnalyticsDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('kpi-completion-rate')).toHaveTextContent('90.0%')
      expect(screen.getByTestId('kpi-completion-rate')).toHaveTextContent('n=50')
      expect(screen.getByTestId('kpi-cost')).toHaveTextContent('$0.0251')
      expect(screen.getByTestId('kpi-latency')).toHaveTextContent('851ms / 2450ms')
      expect(screen.getByTestId('kpi-tool-errors')).toHaveTextContent('4.2%')
    })
  })

  it('renders model comparator table and winners with sample sizes correctly', async () => {
    render(<AnalyticsDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('model-comparator')).toBeInTheDocument()
      expect(screen.getByText('Task Completion Rate')).toBeInTheDocument()
      expect(screen.getByText('Cost per Run ($)')).toBeInTheDocument()
      expect(screen.getByText('gpt-4o (n=30)')).toBeInTheDocument()
      expect(screen.getByText('claude-3-5-sonnet (n=20)')).toBeInTheDocument()
      expect(screen.getByText('-51.9%')).toBeInTheDocument()
    })
  })

  it('renders breakdown tables with plain text numbers and sample sizes', async () => {
    render(<AnalyticsDashboard />)

    await waitFor(() => {
      expect(screen.getByTestId('model-breakdown-section')).toBeInTheDocument()
      expect(screen.getByTestId('tool-breakdown-section')).toBeInTheDocument()
      expect(screen.getByText('bash_exec')).toBeInTheDocument()
      expect(screen.getByText('n=60')).toBeInTheDocument()
    })
  })

  it('renders anomalies feed and allows filtering', async () => {
    render(<AnalyticsDashboard />)

    await waitFor(() => {
      expect(screen.getByText(/Tool 'bash_exec' invoked 4 times consecutively/i)).toBeInTheDocument()
      expect(screen.getByText(/exhibited statistical outlier in Latency/i)).toBeInTheDocument()
    })

    // Click filter to Repeated Tool Loops
    const loopFilterBtn = screen.getByRole('button', { name: /Repeated Tool Loops/i })
    fireEvent.click(loopFilterBtn)

    await waitFor(() => {
      expect(screen.getByText(/Tool 'bash_exec' invoked 4 times consecutively/i)).toBeInTheDocument()
      expect(screen.queryByText(/exhibited statistical outlier in Latency/i)).not.toBeInTheDocument()
    })
  })

  it('renders payloads safely as plain text without XSS injection', async () => {
    const { container } = render(<AnalyticsDashboard />)

    await waitFor(() => {
      expect(container.querySelector('script')).toBeNull()
      expect(container.querySelector('img[onerror]')).toBeNull()
      // Plain text must contain the raw string safely escaped
      expect(container.textContent).toContain("<script>alert('xss_anomaly')</script>")
    })
  })
})
