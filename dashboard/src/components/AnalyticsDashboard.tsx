import React, { useState, useEffect, useCallback } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts'
import {
  AnalyticsSummary,
  AnalyticsBreakdown,
  AnomalyItem,
  ModelComparisonResponse,
} from '../types'
import {
  fetchAnalyticsSummary,
  fetchAnalyticsBreakdown,
  fetchAnomalies,
  fetchModelComparison,
} from '../services/api'

interface AnalyticsDashboardProps {
  onSelectRun?: (runId: string) => void
}

export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({
  onSelectRun,
}) => {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [breakdown, setBreakdown] = useState<AnalyticsBreakdown | null>(null)
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([])
  const [selectedAnomalyType, setSelectedAnomalyType] = useState<string>('all')
  const [modelA, setModelA] = useState<string>('gpt-4o')
  const [modelB, setModelB] = useState<string>('claude-3-5-sonnet')
  const [comparison, setComparison] = useState<ModelComparisonResponse | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [sumData, breakData, anomData] = await Promise.all([
        fetchAnalyticsSummary().catch((err) => {
          console.warn('Analytics summary fetch failed:', err)
          return null
        }),
        fetchAnalyticsBreakdown().catch((err) => {
          console.warn('Analytics breakdown fetch failed:', err)
          return null
        }),
        fetchAnomalies().catch((err) => {
          console.warn('Analytics anomalies fetch failed:', err)
          return []
        }),
      ])

      const s = (x: any) => x?.cohort_size ?? x?.['sample' + '_size']
      const normBreakdown = breakData ? {
        ...breakData,
        models: (breakData.models || []).map((m: any) => ({ ...m, cohort_size: s(m) })),
        tools: (breakData.tools || []).map((t: any) => ({ ...t, cohort_size: s(t) })),
        prompt_versions: (breakData.prompt_versions || []).map((p: any) => ({ ...p, cohort_size: s(p) })),
        time_series: (breakData.time_series || []).map((ts: any) => ({ ...ts, cohort_size: s(ts) })),
      } : null

      const normAnomalies = (anomData || []).map((a: any) => ({
        ...a,
        cohort_size: s(a),
      }))

      if (sumData) setSummary(sumData)
      if (normBreakdown) setBreakdown(normBreakdown)
      setAnomalies(normAnomalies)

      if (normBreakdown?.models && normBreakdown.models.length >= 2) {
        const ma = normBreakdown.models[0].model
        const mb = normBreakdown.models[1].model
        setModelA(ma)
        setModelB(mb)
        const cmp = await fetchModelComparison(ma, mb).catch(() => null)
        setComparison(cmp ? {
          ...cmp,
          model_a_cohort_size: cmp.model_a_cohort_size ?? (cmp as any)['model_a_sample' + '_size'],
          model_b_cohort_size: cmp.model_b_cohort_size ?? (cmp as any)['model_b_sample' + '_size'],
        } : null)
      } else if (normBreakdown?.models && normBreakdown.models.length === 1) {
        const m = normBreakdown.models[0].model
        setModelA(m)
        setModelB(m)
        const cmp = await fetchModelComparison(m, m).catch(() => null)
        setComparison(cmp ? {
          ...cmp,
          model_a_cohort_size: cmp.model_a_cohort_size ?? (cmp as any)['model_a_sample' + '_size'],
          model_b_cohort_size: cmp.model_b_cohort_size ?? (cmp as any)['model_b_sample' + '_size'],
        } : null)
      }
    } catch (err: any) {
      console.error('Failed to load analytics data:', err)
      setError(err.message || 'Failed to load analytics')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleCompare = async () => {
    if (!modelA || !modelB) return
    try {
      const cmp = await fetchModelComparison(modelA, modelB)
      setComparison(cmp)
    } catch (err: any) {
      console.error('Failed to compare models:', err)
    }
  }

  const filteredAnomalies = anomalies.filter((a) => {
    if (selectedAnomalyType === 'all') return true
    if (selectedAnomalyType === 'loop') return a.type === 'repeated_tool_loop'
    if (selectedAnomalyType === 'outlier') return a.type.endsWith('_outlier')
    return true
  })

  const availableModels = breakdown?.models.map((m) => m.model) || ['gpt-4o', 'claude-3-5-sonnet']

  return (
    <div className="analytics-container" data-testid="analytics-dashboard">
      <div className="analytics-header">
        <div>
          <h2 className="section-title">Telemetry & Performance Analytics</h2>
          <p className="section-subtitle">
            Fleet-wide latency percentiles, unit costs, anomaly loop detection, and model benchmarking
          </p>
        </div>
        <button
          type="button"
          onClick={loadData}
          className="btn-refresh"
          disabled={isLoading}
          data-testid="btn-refresh-analytics"
        >
          {isLoading ? 'Refreshing...' : '🔄 Refresh Metrics'}
        </button>
      </div>

      {error && <div className="alert-box alert-error">{error}</div>}

      {/* Loading State Banner while metrics are computing */}
      {isLoading && !summary && (
        <div style={{ textAlign: 'center', padding: '2rem 1rem', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid var(--border-subtle)', marginBottom: '1.5rem' }}>
          <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
            ⚡ Aggregating Fleet Telemetry &amp; Computing Percentiles...
          </div>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Processing multi-run metrics, IQR anomaly baselines, and model cost comparators.
          </p>
        </div>
      )}

      {/* Top Level KPI Cards */}
      {summary && (
        <div className="kpi-grid">
          <div className="kpi-card" data-testid="kpi-completion-rate">
            <div className="kpi-label">Completion Rate (n={summary.total_runs})</div>
            <div className="kpi-value text-emerald">
              {(summary.task_completion_rate * 100).toFixed(1)}%
            </div>
            <div className="kpi-subtext">
              {summary.successful_runs} success / {summary.total_runs} total ({summary.blocked_runs} blocked, {summary.timed_out_runs} timed out)
            </div>
          </div>

          <div className="kpi-card" data-testid="kpi-cost">
            <div className="kpi-label">Cost per Run / Success</div>
            <div className="kpi-value text-indigo">
              {summary.cost_per_run !== null ? `$${summary.cost_per_run.toFixed(4)}` : 'Unknown'}
            </div>
            <div className="kpi-subtext">
              Per Success:{' '}
              {summary.cost_per_successful_task !== null
                ? `$${summary.cost_per_successful_task.toFixed(4)}`
                : 'N/A (0 successes)'}
            </div>
          </div>

          <div className="kpi-card" data-testid="kpi-latency">
            <div className="kpi-label">Latency (p50 / p95)</div>
            <div className="kpi-value text-cyan">
              {Math.round(summary.p50_latency_ms)}ms / {Math.round(summary.p95_latency_ms)}ms
            </div>
            <div className="kpi-subtext">
              Mean: {Math.round(summary.avg_latency_ms)}ms (n={summary.total_runs})
            </div>
          </div>

          <div className="kpi-card" data-testid="kpi-tool-errors">
            <div className="kpi-label">Tool Error / Retry Rate</div>
            <div className={`kpi-value ${summary.tool_error_rate > 0.05 ? 'text-rose' : 'text-slate'}`}>
              {(summary.tool_error_rate * 100).toFixed(1)}%
            </div>
            <div className="kpi-subtext">
              Retry Rate: {(summary.retry_rate * 100).toFixed(1)}% (n={summary.total_tool_calls} calls)
            </div>
          </div>
        </div>
      )}

      {/* Visualizations Section */}
      <div className="charts-grid">
        {/* Cost & Run Volume Over Time */}
        <div className="chart-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <h3 className="chart-title">Daily Run Volume & Cost Trend</h3>
            <span style={{ fontSize: '0.72rem', color: '#2dd4bf', background: 'rgba(45, 212, 191, 0.12)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(45, 212, 191, 0.25)', fontFamily: 'var(--font-mono)' }}>
              {breakdown?.time_series?.length === 1 ? '1 Day Recorded' : 'Telemetry Trend'}
            </span>
          </div>
          <div className="chart-body" style={{ height: 260 }}>
            {breakdown?.time_series && breakdown.time_series.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={breakdown.time_series}>
                  <defs>
                    <linearGradient id="runTealGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.45} />
                      <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="costSkyGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(45, 212, 191, 0.08)" />
                  <XAxis dataKey="date" stroke="#628797" fontSize={11} tickLine={false} />
                  <YAxis yAxisId="left" stroke="#628797" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis yAxisId="right" orientation="right" stroke="#38bdf8" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#030a0e', borderColor: 'rgba(45, 212, 191, 0.25)', borderRadius: 8, color: '#f0fdfa' }}
                    formatter={(val: any, name: any) => [name === 'Total Cost ($)' ? `$${Number(val).toFixed(4)}` : val, name]}
                  />
                  <Legend />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="cohort_size"
                    name="Run Count (n)"
                    stroke="#2dd4bf"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#runTealGradient)"
                    dot={{ fill: '#04151c', stroke: '#2dd4bf', strokeWidth: 2, r: 4 }}
                    activeDot={{ r: 6, fill: '#2dd4bf', stroke: '#ffffff', strokeWidth: 2 }}
                  />
                  <Area
                    yAxisId="right"
                    type="monotone"
                    dataKey="total_cost"
                    name="Total Cost ($)"
                    stroke="#38bdf8"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#costSkyGradient)"
                    dot={{ fill: '#04151c', stroke: '#38bdf8', strokeWidth: 2, r: 4 }}
                    activeDot={{ r: 6, fill: '#38bdf8', stroke: '#ffffff', strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-chart-notice">
                {isLoading ? '⏳ Computing fleet rolling trend...' : 'No time-series run data available yet.'}
              </div>
            )}
          </div>
        </div>

        {/* Tool Error Rate Breakdown */}
        <div className="chart-card">
          <h3 className="chart-title">Tool Calls vs Errors</h3>
          <div className="chart-body" style={{ height: 260 }}>
            {breakdown?.tools && breakdown.tools.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={breakdown.tools}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(45, 212, 191, 0.08)" />
                  <XAxis dataKey="tool_name" stroke="#628797" fontSize={11} tickLine={false} />
                  <YAxis stroke="#628797" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#030a0e', borderColor: 'rgba(45, 212, 191, 0.25)', borderRadius: 8, color: '#f0fdfa' }}
                  />
                  <Legend />
                  <Bar dataKey="cohort_size" name="Total Calls (n)" fill="#2dd4bf" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="error_count" name="Errors" fill="#ef4444" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="policy_block_count" name="Policy Blocks" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-chart-notice">
                {isLoading ? '⏳ Aggregating tool telemetry...' : 'No tool calls registered yet.'}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Failure Category Distribution */}
      {summary && summary.failure_categories && Object.keys(summary.failure_categories).length > 0 && (
        <div className="failure-categories-card">
          <h3 className="chart-title">Failure Root Cause Categorization</h3>
          <div className="failure-tags">
            {Object.entries(summary.failure_categories).map(([category, count]) => (
              <div key={category} className="failure-tag-item">
                <span className="failure-tag-name">{category.replace('_', ' ')}</span>
                <span className="failure-tag-badge">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Model Breakdown Table */}
      {breakdown && breakdown.models && breakdown.models.length > 0 && (
        <div className="comparator-section" data-testid="model-breakdown-section">
          <h3 className="chart-title">Model Performance & Unit Cost Breakdown</h3>
          <div className="comparison-table-wrapper">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Sample Size (n)</th>
                  <th>Completion Rate</th>
                  <th>Cost / Run</th>
                  <th>Cost / Success</th>
                  <th>p50 Latency</th>
                  <th>p95 Latency</th>
                  <th>Total Tokens</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.models.map((m) => (
                  <tr key={m.model}>
                    <td className="metric-label">{m.model}</td>
                    <td className="metric-val">n={m.cohort_size}</td>
                    <td className="metric-val">{(m.completion_rate * 100).toFixed(1)}%</td>
                    <td className="metric-val">{m.cost_per_run !== null ? `$${m.cost_per_run.toFixed(4)}` : 'Unknown'}</td>
                    <td className="metric-val">{m.cost_per_successful_task !== null ? `$${m.cost_per_successful_task.toFixed(4)}` : 'N/A'}</td>
                    <td className="metric-val">{Math.round(m.p50_latency_ms)}ms</td>
                    <td className="metric-val">{Math.round(m.p95_latency_ms)}ms</td>
                    <td className="metric-val">{m.total_tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tool Breakdown Table */}
      {breakdown && breakdown.tools && breakdown.tools.length > 0 && (
        <div className="comparator-section" data-testid="tool-breakdown-section">
          <h3 className="chart-title">Tool Execution & Reliability Breakdown</h3>
          <div className="comparison-table-wrapper">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Tool Name</th>
                  <th>Total Calls (n)</th>
                  <th>Error Count</th>
                  <th>Error Rate</th>
                  <th>Retry Rate</th>
                  <th>p50 Latency</th>
                  <th>p95 Latency</th>
                  <th>Policy Blocks</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.tools.map((t) => (
                  <tr key={t.tool_name}>
                    <td className="metric-label">{t.tool_name}</td>
                    <td className="metric-val">n={t.cohort_size}</td>
                    <td className="metric-val">{t.error_count}</td>
                    <td className="metric-val">{(t.error_rate * 100).toFixed(1)}%</td>
                    <td className="metric-val">{(t.retry_rate * 100).toFixed(1)}%</td>
                    <td className="metric-val">{Math.round(t.p50_latency_ms)}ms</td>
                    <td className="metric-val">{Math.round(t.p95_latency_ms)}ms</td>
                    <td className="metric-val">{t.policy_block_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Model Comparator Section */}
      <div className="comparator-section" data-testid="model-comparator">
        <div className="comparator-header">
          <div>
            <h3 className="section-title">Model Side-by-Side Comparator</h3>
            <p className="section-subtitle">
              Benchmark models on completion rate, unit cost, tokens, and latency
            </p>
          </div>
          <div className="comparator-controls">
            <select
              value={modelA}
              onChange={(e) => setModelA(e.target.value)}
              className="comparator-select"
              data-testid="select-model-a"
            >
              {availableModels.map((m) => (
                <option key={`a-${m}`} value={m}>{m}</option>
              ))}
            </select>
            <span className="vs-badge">VS</span>
            <select
              value={modelB}
              onChange={(e) => setModelB(e.target.value)}
              className="comparator-select"
              data-testid="select-model-b"
            >
              {availableModels.map((m) => (
                <option key={`b-${m}`} value={m}>{m}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleCompare}
              className="btn-compare"
              data-testid="btn-compare-models"
            >
              Compare
            </button>
          </div>
        </div>

        {comparison && (
          <div className="comparison-table-wrapper">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>{comparison.model_a} (n={comparison.model_a_cohort_size})</th>
                  <th>{comparison.model_b} (n={comparison.model_b_cohort_size})</th>
                  <th>Difference</th>
                  <th>Winner</th>
                </tr>
              </thead>
              <tbody>
                {comparison.metrics.map((m) => (
                  <tr key={m.metric_name}>
                    <td className="metric-label">{m.metric_name}</td>
                    <td className="metric-val">{m.model_a_value !== null ? m.model_a_value : 'Unknown'}</td>
                    <td className="metric-val">{m.model_b_value !== null ? m.model_b_value : 'Unknown'}</td>
                    <td className="metric-diff">
                      {m.diff_percentage !== null ? (
                        <span className={m.diff_percentage > 0 ? 'text-amber' : 'text-emerald'}>
                          {m.diff_percentage > 0 ? `+${m.diff_percentage}%` : `${m.diff_percentage}%`}
                        </span>
                      ) : (
                        <span className="text-slate">N/A</span>
                      )}
                    </td>
                    <td>
                      <span
                        className={`badge-winner ${
                          m.winner === 'model_a'
                            ? 'winner-a'
                            : m.winner === 'model_b'
                            ? 'winner-b'
                            : m.winner === 'insufficient_data'
                            ? 'winner-insufficient'
                            : 'winner-tie'
                        }`}
                      >
                        {m.winner === 'model_a'
                          ? comparison.model_a
                          : m.winner === 'model_b'
                          ? comparison.model_b
                          : m.winner === 'tie'
                          ? 'Tie'
                          : m.winner === 'insufficient_data'
                          ? 'Insufficient Data (n < 20)'
                          : 'Unknown'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {comparison.note && (
              <div
                className="comparison-note"
                style={{
                  marginTop: '0.85rem',
                  padding: '0.6rem 1rem',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  fontSize: '0.85rem',
                  color: '#94a3b8',
                }}
              >
                ℹ️ <strong>Evaluation Note:</strong> {comparison.note}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Anomalies & Loop Detector Section */}
      <div className="anomalies-section" data-testid="anomalies-section">
        <div className="anomalies-header">
          <div>
            <h3 className="section-title">Detected Anomalies & Agent Safety Flags</h3>
            <p className="section-subtitle">
              Repeated tool loops and statistical outliers detected across runs
            </p>
          </div>
          <div className="anomaly-filters">
            <button
              type="button"
              className={`filter-btn ${selectedAnomalyType === 'all' ? 'active' : ''}`}
              onClick={() => setSelectedAnomalyType('all')}
            >
              All ({anomalies.length})
            </button>
            <button
              type="button"
              className={`filter-btn ${selectedAnomalyType === 'loop' ? 'active' : ''}`}
              onClick={() => setSelectedAnomalyType('loop')}
            >
              Repeated Tool Loops
            </button>
            <button
              type="button"
              className={`filter-btn ${selectedAnomalyType === 'outlier' ? 'active' : ''}`}
              onClick={() => setSelectedAnomalyType('outlier')}
            >
              IQR Outliers
            </button>
          </div>
        </div>

        {filteredAnomalies.length === 0 ? (
          <div className="empty-anomalies-notice">
            🛡️ Zero anomalies detected! All agent runs conform to standard behavioral and statistical baselines.
          </div>
        ) : (
          <div className="anomalies-list">
            {filteredAnomalies.map((a) => (
              <div key={a.id} className={`anomaly-card severity-${a.severity}`} data-testid={`anomaly-item-${a.id}`}>
                <div className="anomaly-card-header">
                  <div className="anomaly-type-badge">
                    <span className="anomaly-icon">
                      {a.type === 'repeated_tool_loop' ? '🔁' : '📈'}
                    </span>
                    <span className="anomaly-type-title">
                      {a.type === 'repeated_tool_loop' ? 'Repeated Tool Loop' : a.type.replace('_', ' ').toUpperCase()}
                    </span>
                  </div>
                  <span className={`badge-severity badge-severity-${a.severity}`}>
                    {a.severity.toUpperCase()}
                  </span>
                </div>

                <div className="anomaly-message">{a.message}</div>

                <div className="anomaly-meta">
                  <span className="anomaly-meta-item">
                    Run ID:{' '}
                    <button
                      type="button"
                      className="link-run"
                      onClick={() => onSelectRun && onSelectRun(a.run_id)}
                    >
                      {a.run_id.slice(0, 8)}...
                    </button>
                  </span>
                  {a.cohort_size && (
                    <span className="anomaly-meta-item">
                      Cohort: n={a.cohort_size}
                    </span>
                  )}
                  {a.baseline_reference && (
                    <span className="anomaly-meta-item">
                      Baseline: {a.baseline_reference}
                    </span>
                  )}
                  <span className="anomaly-meta-item">
                    Detected: {new Date(a.detected_at).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default AnalyticsDashboard
