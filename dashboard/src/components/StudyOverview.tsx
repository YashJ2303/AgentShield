import React, { useState, useEffect } from 'react'
import { fetchStudyOverview, fetchReplayVariants } from '../services/api'
import { AlertCircle, RefreshCw, Sliders, Info } from 'lucide-react'

interface BenchmarkRow {
  Agent: string
  Condition: string
  Unsafe_Prevented: string
  Unsafe_Total: string
  Unsafe_Prev_Rate: string
  Unsafe_Prev_CI_Low: string
  Unsafe_Prev_CI_High: string
  False_Blocks: string
  Benign_Total: string
  False_Block_Rate: string
  Benign_Success_Rate: string
}

interface ReplayVariant {
  variant_id: string
  split: string
  agent: string
  variant_type: string
  category_by_construction: string
  composite_fidelity: number
  s_tool: number
  s_args: number
  s_out: number
}

export const StudyOverview: React.FC = () => {
  const [rows, setRows] = useState<BenchmarkRow[]>([])
  const [variants, setVariants] = useState<ReplayVariant[]>([])
  const [threshold, setThreshold] = useState<number>(0.80)
  const [selectedVariant, setSelectedVariant] = useState<ReplayVariant | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<string>('ALL')

  useEffect(() => {
    let isMounted = true
    const load = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const [overviewData, variantsData] = await Promise.all([
          fetchStudyOverview(),
          fetchReplayVariants().catch(() => ({ variants: [], count: 0 })),
        ])
        if (isMounted) {
          setRows(overviewData.benchmark_rows || [])
          setVariants(variantsData.variants || [])
          if (variantsData.variants && variantsData.variants.length > 0) {
            setSelectedVariant(variantsData.variants[0])
          }
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Failed to load study overview from eval_results')
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }
    load()
    return () => {
      isMounted = false
    }
  }, [])

  const filteredRows = selectedAgent === 'ALL'
    ? rows
    : rows.filter((r) => r.Agent.toUpperCase() === selectedAgent)

  // Calculations based on current threshold slider
  const regressions = variants.filter((v) => v.composite_fidelity < threshold)
  const tolerated = variants.filter((v) => v.composite_fidelity >= threshold)

  return (
    <div className="workspace-viewport" data-testid="study-overview-view">
      {/* Header */}
      <div className="view-header">
        <div className="view-title-wrap">
          <div>
            <div className="evaluate-header-title">3 · Evaluate: Study Overview</div>
            <h2 className="view-title" style={{ marginTop: '0.2rem' }}>
              Evaluation Results & Confidence Intervals
            </h2>
          </div>
        </div>

        <div className="header-badges-wrap">
          <div className="badge-scripted-agents">
            Loaded from eval_results/ · Wilson score 95% CIs
          </div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <RefreshCw size={24} className="animate-spin text-mint" style={{ margin: '0 auto 1rem' }} />
          <div>Loading study benchmark data from read-only evaluation API...</div>
        </div>
      ) : error ? (
        <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--coral)', borderRadius: 'var(--radius-md)', color: 'var(--coral-light)' }}>
          <AlertCircle size={16} className="inline mr-2" />
          {error}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Top Grid: Forest Plot + Benchmark Table */}
          <div className="study-overview-grid" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
            {/* Col 1: Forest Plot rendered dynamically from CSV data */}
            <div className="panel-card">
              <div className="panel-header">
                <h3 className="panel-title">Active Attacks Prevented Rate (%)</h3>
                <div style={{ display: 'flex', gap: '6px' }}>
                  {['ALL', 'SQL', 'WEB', 'FILE_SHELL'].map((agent) => (
                    <button
                      key={agent}
                      type="button"
                      onClick={() => setSelectedAgent(agent)}
                      className={`btn btn-secondary ${selectedAgent === agent ? 'active' : ''}`}
                      style={{ fontSize: '0.7rem', padding: '2px 8px' }}
                    >
                      {agent}
                    </button>
                  ))}
                </div>
              </div>
              <p className="chart-subtitle-note">
                Point estimate and 95% Wilson score interval loaded from eval_results/evaluation_results.csv
              </p>

              <div className="forest-plot-container">
                {filteredRows.map((item, idx) => {
                  const rate = parseFloat(item.Unsafe_Prev_Rate) || 0
                  const ciLow = parseFloat(item.Unsafe_Prev_CI_Low) || 0
                  const ciHigh = parseFloat(item.Unsafe_Prev_CI_High) || 0
                  const isGateway = item.Condition.toLowerCase().includes('gateway')
                  const isBlocklist = item.Condition.toLowerCase().includes('blocklist')
                  const color = isGateway ? '#2dd4bf' : isBlocklist ? '#f59e0b' : '#ef4444'

                  return (
                    <div key={idx} className="forest-plot-row">
                      <span className="forest-row-label">
                        {item.Agent}: {item.Condition.split(':')[1]?.trim() || item.Condition}
                      </span>
                      <div className="forest-axis-track">
                        {/* Confidence Interval Line */}
                        <div
                          className="forest-ci-bar"
                          style={{
                            left: `${ciLow}%`,
                            width: `${Math.max(2, ciHigh - ciLow)}%`,
                            backgroundColor: color,
                            opacity: 0.45,
                          }}
                        />
                        {/* Point Estimate Dot */}
                        <div
                          className="forest-dot"
                          style={{
                            left: `${rate}%`,
                            backgroundColor: color,
                            boxShadow: `0 0 8px ${color}`,
                          }}
                          title={`${item.Agent} (${item.Condition}): ${rate}% [${ciLow}%, ${ciHigh}%]`}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Scale Axis */}
              <div className="forest-axis-scale">
                <span>0%</span>
                <span>25%</span>
                <span>50%</span>
                <span>75%</span>
                <span>100%</span>
              </div>
            </div>

            {/* Col 2: Structured Benchmark Table */}
            <div className="panel-card">
              <div className="panel-header">
                <h3 className="panel-title">Evaluation Metrics Table</h3>
              </div>
              <p className="chart-subtitle-note">
                Complete evaluation run statistics directly parsed from disk
              </p>

              <div style={{ overflowX: 'auto' }}>
                <table className="rules-table" style={{ fontSize: '0.75rem' }}>
                  <thead>
                    <tr>
                      <th>Agent</th>
                      <th>Condition</th>
                      <th style={{ textAlign: 'right' }}>Prevented</th>
                      <th style={{ textAlign: 'right' }}>Prev %</th>
                      <th style={{ textAlign: 'right' }}>False Blk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((r, idx) => (
                      <tr key={idx}>
                        <td><span className="tool-chip">{r.Agent}</span></td>
                        <td style={{ maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.Condition}>
                          {r.Condition.split(':')[1]?.trim() || r.Condition}
                        </td>
                        <td style={{ textAlign: 'right' }}>{r.Unsafe_Prevented}/{r.Unsafe_Total}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600, color: parseFloat(r.Unsafe_Prev_Rate) >= 90 ? 'var(--mint)' : 'var(--coral)' }}>
                          {r.Unsafe_Prev_Rate}%
                        </td>
                        <td style={{ textAlign: 'right' }}>{r.False_Blocks}/{r.Benign_Total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Bottom Card: Replay Similarity & Threshold Sensitivity Explorer */}
          {variants.length > 0 && (
            <div className="panel-card" data-testid="replay-similarity-explorer">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">decision threshold on composite fidelity, post-hoc</h3>
                  <p className="chart-subtitle-note" style={{ margin: '2px 0 0 0' }}>
                    Data dynamically loaded per-variant from eval_results/replay_regression_results.csv (N={variants.length})
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                    decision threshold on composite fidelity, post-hoc: τ = <strong style={{ color: '#38bdf8' }}>{threshold.toFixed(2)}</strong>
                  </span>
                  <input
                    type="range"
                    min="0.0"
                    max="1.0"
                    step="0.01"
                    value={threshold}
                    onChange={(e) => setThreshold(parseFloat(e.target.value))}
                    data-testid="fidelity-threshold-slider"
                    style={{ width: '150px', cursor: 'pointer' }}
                  />
                </div>
              </div>

              {/* Dot Strip Visualization */}
              <div style={{ marginTop: '1rem', position: 'relative', padding: '1.5rem 0' }}>
                <div
                  style={{
                    height: '24px',
                    backgroundColor: '#0f172a',
                    borderRadius: '12px',
                    position: 'relative',
                    border: '1px solid #334155',
                    overflow: 'visible',
                  }}
                >
                  {/* Threshold cutoff marker */}
                  <div
                    style={{
                      position: 'absolute',
                      left: `${threshold * 100}%`,
                      top: '-10px',
                      bottom: '-10px',
                      width: '2px',
                      backgroundColor: '#38bdf8',
                      boxShadow: '0 0 8px #38bdf8',
                      zIndex: 10,
                    }}
                    title={`Decision boundary τ = ${threshold.toFixed(2)}`}
                  />

                  {/* Per-variant dots positioned by composite_fidelity */}
                  {variants.map((v) => {
                    const isFlagged = v.composite_fidelity < threshold
                    const dotColor = isFlagged ? '#ef4444' : '#10b981'
                    const isSelected = selectedVariant?.variant_id === v.variant_id

                    return (
                      <div
                        key={v.variant_id}
                        onClick={() => setSelectedVariant(v)}
                        title={`${v.variant_id} (${v.variant_type}): fidelity=${v.composite_fidelity.toFixed(4)} [${isFlagged ? 'FLAGGED REGRESSION' : 'TOLERATED BENIGN'}]`}
                        data-testid={`variant-dot-${v.variant_id}`}
                        style={{
                          position: 'absolute',
                          left: `${Math.min(99, Math.max(1, v.composite_fidelity * 100))}%`,
                          top: '50%',
                          transform: 'translate(-50%, -50%)',
                          width: isSelected ? '14px' : '10px',
                          height: isSelected ? '14px' : '10px',
                          borderRadius: '50%',
                          backgroundColor: dotColor,
                          border: isSelected ? '2px solid #ffffff' : '1px solid rgba(0,0,0,0.5)',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                          zIndex: isSelected ? 20 : 5,
                        }}
                      />
                    )
                  })}
                </div>

                {/* Scale Axis */}
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b', marginTop: '6px' }}>
                  <span>0.00 (Fidelity min)</span>
                  <span>0.25</span>
                  <span>0.50</span>
                  <span>0.75</span>
                  <span>1.00 (Perfect fidelity)</span>
                </div>
              </div>

              {/* Classification Summary & Inspector */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1rem', marginTop: '0.75rem', backgroundColor: '#0f172a', padding: '12px 16px', borderRadius: '6px', border: '1px solid #1e293b' }}>
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', marginBottom: '6px' }}>
                    Classification at τ = {threshold.toFixed(2)}
                  </div>
                  <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.82rem' }}>
                    <div>
                      <span style={{ color: '#ef4444', fontWeight: 700 }}>{regressions.length}</span> / {variants.length} Flagged Regressions (<span style={{ color: '#ef4444' }}>{((regressions.length / variants.length) * 100).toFixed(1)}%</span>)
                    </div>
                    <div>
                      <span style={{ color: '#10b981', fontWeight: 700 }}>{tolerated.length}</span> / {variants.length} Tolerated Variations (<span style={{ color: '#10b981' }}>{((tolerated.length / variants.length) * 100).toFixed(1)}%</span>)
                    </div>
                  </div>
                </div>

                {selectedVariant && (
                  <div style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>
                    <div style={{ fontWeight: 600, color: '#f8fafc' }}>
                      Selected: <code>{selectedVariant.variant_id}</code> ({selectedVariant.category_by_construction})
                    </div>
                    <div style={{ color: '#94a3b8', marginTop: '2px' }}>
                      Type: {selectedVariant.variant_type} · Agent: {selectedVariant.agent} · Fidelity: <strong>{selectedVariant.composite_fidelity.toFixed(4)}</strong>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
