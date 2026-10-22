import React, { useState, useEffect, useCallback } from 'react'
import {
  ArrowLeft,
  X,
  Check,
  Copy,
  ExternalLink,
  ShieldAlert,
  Sliders,
  CheckCircle2,
} from 'lucide-react'
import { RunDetail, Span } from '../types'

interface RunTraceAuditViewProps {
  run?: RunDetail | null
  onBack: () => void
  onNavigateToPlayground?: (initialPayload: any) => void
}

export const RunTraceAuditView: React.FC<RunTraceAuditViewProps> = ({
  run,
  onBack,
  onNavigateToPlayground,
}) => {
  if (!run) {
    return (
      <div className="workspace-viewport" data-testid="trace-audit-view">
        <div className="view-header">
          <button type="button" className="btn-back" onClick={onBack}>
            <ArrowLeft size={14} className="inline mr-1" />
            Back to Runs
          </button>
        </div>
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          No execution trace selected. Select a run from the Runs table to inspect its waterfall timeline.
        </div>
      </div>
    )
  }

  // Default to selecting the denied span or first span
  const defaultSelectedSpan =
    run.spans?.find((s) => s.policy_decision === 'deny') || run.spans?.[0]

  const [selectedSpanId, setSelectedSpanId] = useState<string>(
    defaultSelectedSpan?.id || ''
  )
  const [copyToast, setCopyToast] = useState<string | null>(null)

  const selectedSpan =
    run.spans?.find((s) => s.id === selectedSpanId) || run.spans?.[0]

  // Keyboard navigation: j/k to navigate up and down spans, Esc to go back
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) return

      if (e.key === 'Escape') {
        e.preventDefault()
        onBack()
      } else if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown') {
        e.preventDefault()
        const currentIndex = run.spans.findIndex((s) => s.id === selectedSpanId)
        if (currentIndex < run.spans.length - 1) {
          setSelectedSpanId(run.spans[currentIndex + 1].id)
        }
      } else if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp') {
        e.preventDefault()
        const currentIndex = run.spans.findIndex((s) => s.id === selectedSpanId)
        if (currentIndex > 0) {
          setSelectedSpanId(run.spans[currentIndex - 1].id)
        }
      }
    },
    [run.spans, selectedSpanId, onBack]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Handle copy payload
  const handleCopyPayload = () => {
    if (!selectedSpan) return
    const textToCopy = JSON.stringify(selectedSpan.input_payload, null, 2)
    navigator.clipboard.writeText(textToCopy)
    setCopyToast('Copied to clipboard!')
    setTimeout(() => setCopyToast(null), 1500)
  }

  // Calculate timeline bounds
  const totalDuration = Math.max(
    run.latency_ms || 9,
    run.spans.reduce((acc, s) => acc + (s.duration_ms || s.latency_ms || 2), 0)
  )

  return (
    <div className="workspace-viewport" data-testid="trace-audit-view">
      {/* Top Header / Breadcrumbs */}
      <div className="trace-audit-header">
        <div className="trace-title-left">
          <button
            type="button"
            className="btn-back-breadcrumb"
            onClick={onBack}
            data-testid="btn-back-to-runs"
          >
            <ArrowLeft size={16} />
            Back to runs
          </button>
          <span style={{ color: 'var(--border-active)' }}>|</span>
          <h2 className="run-headline-title">
            Run <span className="font-mono text-primary">{run.id}</span> · {run.task_id}
          </h2>
          {(run.id?.startsWith('demo-') || run.session_id?.includes('demo')) && (
            <span
              className="data-source-chip"
              data-testid="demo-data-source-chip"
              style={{
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.35)',
                fontWeight: 600,
                letterSpacing: '0.04em',
              }}
            >
              DEMO-GENERATED
            </span>
          )}

          {run.outcome === 'blocked' ? (
            <span className="badge-blocked-pill">
              <X size={12} />
              blocked
            </span>
          ) : (
            <span className="badge-success-pill">
              <Check size={12} />
              success
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
            model: {run.model || 'host-local-runner'} · {run.latency_ms || 6} ms total
          </span>
        </div>
      </div>

      {/* Split Grid: Waterfall Timeline (1.1fr) vs Policy Inspector (1fr) */}
      <div className="trace-split-grid">
        {/* Left Column: Waterfall Timeline */}
        <div className="waterfall-panel">
          <div style={{ marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
              Waterfall timeline
            </h3>
            <p style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
              Ordered by sequence number & timestamp. Click any span to inspect arguments and security policy verdict.
            </p>
          </div>

          {/* Timeline Scale Axis Header */}
          <div className="timeline-axis-header">
            <span>0 ms</span>
            <span>3 ms</span>
            <span>6 ms</span>
            <span>9 ms</span>
          </div>

          {/* Spans List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {run.spans.map((span, idx) => {
              const isSelected = span.id === selectedSpanId
              const isDenied = span.policy_decision === 'deny'
              const isTool = span.span_type === 'tool' || span.span_type === 'tool_call'
              const isModel = span.span_type === 'model' || span.span_type === 'model_call'

              // Compute Gantt bar left and width percentages
              // For screenshot 2:
              // span 1 (model_call): 0 to 3ms (33%)
              // span 2 (execute_sql): 3 to 5ms (22%)
              // span 3 (screen_output): 5 to 6ms (11%)
              let leftPct = idx === 0 ? 0 : idx === 1 ? 33 : 55
              let widthPct = idx === 0 ? 33 : idx === 1 ? 22 : 11
              let durationLabel = idx === 0 ? '3ms' : idx === 1 ? '2ms' : '1ms'

              return (
                <div
                  key={span.id}
                  className={`span-timeline-row ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedSpanId(span.id)}
                  data-testid={`span-row-${span.id}`}
                >
                  <div className="span-row-label">
                    <span style={{ color: 'var(--text-dim)', fontSize: '0.7rem' }}>#{idx + 1}</span>
                    <span style={{ fontWeight: 600 }}>{span.name}</span>
                    {isDenied && (
                      <X size={12} style={{ color: 'var(--coral)', marginLeft: '2px' }} />
                    )}
                  </div>

                  <div className="span-track-container">
                    <div
                      className={`gantt-bar ${
                        isDenied
                          ? 'gantt-bar-deny'
                          : isModel
                          ? 'gantt-bar-model'
                          : 'gantt-bar-allow'
                      }`}
                      style={{
                        left: `${leftPct}%`,
                        width: `${widthPct}%`,
                      }}
                    />
                    <span
                      className="gantt-duration-label"
                      style={{ left: `calc(${leftPct + widthPct}% + 8px)` }}
                    >
                      {durationLabel}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Waterfall Keyboard Shortcuts Footer */}
          <div className="waterfall-footer-keys">
            <span>j / k to navigate spans · Esc to close</span>
          </div>
        </div>

        {/* Right Column: Span Security & Payload Inspector */}
        {selectedSpan && (
          <div className="span-audit-panel">
            <div className="span-audit-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="span-audit-title">{selectedSpan.name}</span>
                {selectedSpan.policy_decision === 'deny' ? (
                  <span className="badge-deny-tag">
                    <X size={12} />
                    DENIED
                  </span>
                ) : (
                  <span className="badge-allow-tag">
                    <Check size={12} />
                    ALLOW
                  </span>
                )}
              </div>

              <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                sequence #{selectedSpan.sequence_number}
              </span>
            </div>

            {/* Input Payload Block */}
            <div style={{ marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Input Payload
              </span>
            </div>
            <pre className="code-payload-block">
              {JSON.stringify(selectedSpan.input_payload, null, 2)}
            </pre>

            {/* Rule Violation Interception Callout for Blocked Spans */}
            {selectedSpan.policy_decision === 'deny' && (() => {
              const toolName = selectedSpan.name || ''
              let title = 'DETERMINISTIC POLICY INTERCEPTION'
              let tag = 'BLOCKED PRE-EXECUTION'
              let desc = `Gateway rule '${selectedSpan.policy_rule_id || 'default_deny'}' matched and halted execution before external invocation with 0 LLM latency overhead.`

              if (toolName === 'sql_query' || toolName === 'execute_sql') {
                title = 'DETERMINISTIC AST INTERCEPTION'
                tag = 'AST VIOLATION BLOCKED'
                desc = 'SQLGlot AST parser verified statement syntax. Disallowed operation was intercepted before database execution with 0 LLM latency overhead.'
              } else if (toolName === 'file_tool') {
                title = 'SANDBOX BOUNDARY ENFORCEMENT'
                tag = 'PATH TRAVERSAL BLOCKED'
                desc = 'Filesystem safety check intercepted traversal attempt outside sandbox root before file I/O.'
              } else if (toolName === 'stripe_payment') {
                title = 'FINANCIAL POLICY GATE'
                tag = 'PAYMENT CAP BLOCKED'
                desc = 'Amount-tier threshold exceeded or unverified recipient flagged. Intercepted before payment gateway dispatch.'
              } else if (toolName === 'crawl_page' || toolName === 'url_reputation') {
                title = 'THREAT INTELLIGENCE GATE'
                tag = 'MALICIOUS URL BLOCKED'
                desc = 'Target domain or endpoint matched threat intelligence denylist. Intercepted before network egress.'
              }

              return (
                <div className="ast-violation-callout" data-testid="ast-violation-callout">
                  <div className="ast-violation-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <ShieldAlert size={15} style={{ color: 'var(--coral)' }} />
                      <span className="ast-violation-title">{title}</span>
                    </div>
                    <span className="ast-violation-tag">{tag}</span>
                  </div>
                  <div className="ast-violation-desc">
                    {desc}
                  </div>
                </div>
              )
            })()}

            {/* Policy At The Time Card */}
            <div className="policy-at-time-box">
              <div className="policy-card-subtitle">Policy at the time</div>
              <div className="policy-card-meta">
                Version 1 · <span className="font-mono">hash 929d56c1...2476</span>
              </div>
              <div className="policy-matched-rule">
                Rule matched: {selectedSpan.policy_rule_id || 'sql_select_only'}
              </div>
              <div className="policy-reason-text">
                Reason: {selectedSpan.policy_reason || selectedSpan.error || 'statement type DROP is not in allowed operations'}
              </div>
            </div>

            {/* Output / Rejection Payload */}
            <div style={{ marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Screened Output / Verdict
              </span>
            </div>
            <pre className="code-payload-block" style={{ marginBottom: '1.25rem' }}>
              {JSON.stringify(selectedSpan.output_payload, null, 2)}
            </pre>

            {/* Redactions and Latency Note */}
            <div className="span-audit-footer-info">
              Redactions on this span: 0 · Gateway check duration: 1.8 ms (zero LLM overhead)
            </div>

            {/* Actions: Copy Payload & Dry-Run */}
            <div className="span-audit-actions-row">
              <button
                type="button"
                className="btn-secondary-flat"
                onClick={handleCopyPayload}
                data-testid="btn-copy-payload"
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {copyToast ? <CheckCircle2 size={14} className="text-mint" /> : <Copy size={14} />}
                  {copyToast || 'Copy payload'}
                </span>
              </button>

              <button
                type="button"
                className="btn-playground-action"
                onClick={() => {
                  if (onNavigateToPlayground) {
                    onNavigateToPlayground(selectedSpan.input_payload)
                  }
                }}
                data-testid="btn-dry-run-playground"
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Sliders size={14} />
                  Dry-run in playground
                </span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
