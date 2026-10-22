import React, { useState, useEffect } from 'react'
import { RunDetail, Span } from '../types'
import { TraceWaterfall, sortSpansDeterministically } from './TraceWaterfall'
import { SpanDetailPanel } from './SpanDetailPanel'

interface RunDetailViewProps {
  run: RunDetail
  onBack: () => void
}

export const RunDetailView: React.FC<RunDetailViewProps> = ({ run, onBack }) => {
  const [selectedSpan, setSelectedSpan] = useState<Span | null>(null)

  // Auto-select first span on initial load if available
  useEffect(() => {
    if (run.spans && run.spans.length > 0 && !selectedSpan) {
      const sorted = sortSpansDeterministically(run.spans)
      setSelectedSpan(sorted[0])
    }
  }, [run.spans])

  const outcomeClass =
    run.outcome === 'success'
      ? 'badge-success'
      : run.outcome === 'blocked'
      ? 'badge-blocked'
      : run.outcome === 'failure'
      ? 'badge-failure'
      : 'badge-neutral'

  return (
    <div className="run-detail-container" data-testid="run-detail-view">
      {/* Detail Header */}
      <div className="run-detail-header">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="btn-secondary" data-testid="btn-back-to-runs">
            ← Back to Runs
          </button>
          <span className={`badge-outcome ${outcomeClass}`} data-testid="detail-outcome">
            {run.outcome.toUpperCase()}
          </span>
          <h2 className="run-task-title font-semibold text-lg text-slate-100">
            {run.task_id || 'Agent Execution Trace'}
          </h2>
          <span className="font-mono text-xs text-slate-400">({run.id})</span>
        </div>

        <div className="run-summary-stats">
          <div className="stat-pill">
            <span className="stat-label">Model:</span>
            <span className="stat-value font-mono">{run.model || 'N/A'}</span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Cost:</span>
            <span className="stat-value font-mono">
              {run.total_cost !== null && run.total_cost !== undefined ? `$${run.total_cost.toFixed(4)}` : 'Unknown'}
            </span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Tokens:</span>
            <span className="stat-value font-mono">{run.total_tokens.toLocaleString()}</span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Steps:</span>
            <span className="stat-value font-mono">{run.step_count}</span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Duration:</span>
            <span className="stat-value font-mono">{run.latency_ms}ms</span>
          </div>
        </div>
      </div>

      {run.error_message && (
        <div className="error-banner mb-4" data-testid="run-error-message">
          <div className="font-semibold text-sm text-rose-300">Run Failure / Blocked Reason:</div>
          <p className="font-mono text-xs text-rose-200 mt-1">{run.error_message}</p>
        </div>
      )}

      {/* Split layout: Waterfall timeline on the left, Span panel on the right */}
      <div className="trace-split-view">
        <div className="waterfall-section">
          <h3 className="section-heading">Waterfall Trace Timeline</h3>
          <p className="section-subtext">
            Ordered by sequence number & timestamp. Click any span to inspect arguments and security policy verdict.
          </p>
          <TraceWaterfall
            spans={run.spans || []}
            selectedSpanId={selectedSpan?.id || null}
            onSelectSpan={(s) => setSelectedSpan(s)}
          />
        </div>

        <div className="span-panel-section">
          <h3 className="section-heading">Span Security & Payload Inspector</h3>
          <p className="section-subtext">
            Plain-text payload rendering and policy check audit details.
          </p>
          <SpanDetailPanel span={selectedSpan} onClose={() => setSelectedSpan(null)} />
        </div>
      </div>
    </div>
  )
}
