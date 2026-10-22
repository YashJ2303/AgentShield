import React from 'react'
import { Span } from '../types'

interface TraceWaterfallProps {
  spans: Span[]
  selectedSpanId: string | null
  onSelectSpan: (span: Span) => void
}

export function sortSpansDeterministically(spans: Span[]): Span[] {
  return [...spans].sort((a, b) => {
    if (a.sequence_number !== b.sequence_number) {
      return a.sequence_number - b.sequence_number
    }
    const tA = new Date(a.started_at).getTime()
    const tB = new Date(b.started_at).getTime()
    return tA - tB
  })
}

export function calculateTimelineBounds(spans: Span[]): { minStartTime: number; maxEndTime: number; totalDurationMs: number } {
  if (spans.length === 0) {
    const now = Date.now()
    return { minStartTime: now, maxEndTime: now + 1, totalDurationMs: 1 }
  }

  let minStart = Infinity
  let maxEnd = -Infinity

  for (const s of spans) {
    const start = new Date(s.started_at).getTime()
    const end = s.ended_at ? new Date(s.ended_at).getTime() : start + (s.latency_ms || 1)
    if (start < minStart) minStart = start
    if (end > maxEnd) maxEnd = end
  }

  const duration = Math.max(1, maxEnd - minStart)
  return { minStartTime: minStart, maxEndTime: maxEnd, totalDurationMs: duration }
}

export const TraceWaterfall: React.FC<TraceWaterfallProps> = ({
  spans,
  selectedSpanId,
  onSelectSpan,
}) => {
  const sorted = sortSpansDeterministically(spans)
  const { minStartTime, totalDurationMs } = calculateTimelineBounds(sorted)

  return (
    <div className="waterfall-container" data-testid="waterfall-container">
      <div className="waterfall-header">
        <div className="col-seq">#</div>
        <div className="col-info">Span / Operation</div>
        <div className="col-decision">Decision</div>
        <div className="col-timeline">Timeline Waterfall ({totalDurationMs}ms total)</div>
        <div className="col-latency">Latency</div>
      </div>

      <div className="waterfall-body">
        {sorted.map((span) => {
          const startMs = new Date(span.started_at).getTime()
          const durationMs = Math.max(1, span.latency_ms || 1)
          const offsetMs = Math.max(0, startMs - minStartTime)
          const leftPercent = Math.min(98, (offsetMs / totalDurationMs) * 100)
          const widthPercent = Math.max(2, Math.min(100 - leftPercent, (durationMs / totalDurationMs) * 100))

          const isSelected = span.id === selectedSpanId
          const decisionClass = span.policy_decision === 'allow'
            ? 'decision-allow'
            : span.policy_decision === 'deny'
            ? 'decision-deny'
            : span.policy_decision === 'require_approval' || span.policy_decision === 'pending'
            ? 'decision-approval'
            : 'decision-neutral'

          return (
            <div
              key={span.id}
              className={`waterfall-row ${isSelected ? 'row-selected' : ''}`}
              onClick={() => onSelectSpan(span)}
              data-testid={`span-row-${span.id}`}
            >
              <div className="col-seq font-mono text-slate-400">
                #{span.sequence_number}
              </div>

              <div className="col-info">
                <span className={`badge-type badge-${span.span_type}`}>
                  {span.span_type}
                </span>
                <span className="span-name font-medium">{span.name}</span>
                {span.redaction_count > 0 && (
                  <span className="badge-redaction" title={`${span.redaction_count} secrets redacted`}>
                    🛡️ {span.redaction_count}
                  </span>
                )}
              </div>

              <div className="col-decision">
                <span className={`badge-decision ${decisionClass}`}>
                  {span.policy_decision || 'none'}
                </span>
              </div>

              <div className="col-timeline">
                <div className="waterfall-track">
                  <div
                    className={`waterfall-bar ${decisionClass} bar-${span.span_type}`}
                    style={{
                      left: `${leftPercent}%`,
                      width: `${widthPercent}%`,
                    }}
                    title={`${span.name}: ${durationMs}ms at +${offsetMs}ms`}
                  />
                </div>
              </div>

              <div className="col-latency font-mono text-slate-300">
                {span.latency_ms}ms
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
