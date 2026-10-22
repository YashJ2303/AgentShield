import React from 'react'
import { Span } from '../types'
import { SafePayloadViewer } from './SafePayloadViewer'

interface SpanDetailPanelProps {
  span: Span | null
  onClose: () => void
}

export const SpanDetailPanel: React.FC<SpanDetailPanelProps> = ({ span, onClose }) => {
  if (!span) {
    return (
      <div className="span-panel-empty">
        <p className="text-slate-400">Select a span from the waterfall timeline to view payload details and security metrics.</p>
      </div>
    )
  }

  const decisionClass = span.policy_decision === 'allow'
    ? 'text-emerald-400'
    : span.policy_decision === 'deny'
    ? 'text-rose-400'
    : span.policy_decision === 'require_approval' || span.policy_decision === 'pending'
    ? 'text-amber-400'
    : 'text-slate-300'

  return (
    <div className="span-panel" data-testid="span-detail-panel">
      <div className="span-panel-header">
        <div>
          <span className={`badge-type badge-${span.span_type} mr-2`}>
            {span.span_type.toUpperCase()}
          </span>
          <h3 className="span-title inline font-mono text-lg font-semibold">{span.name}</h3>
        </div>
        <button
          onClick={onClose}
          className="btn-close"
          data-testid="close-panel-btn"
          aria-label="Close span details"
        >
          ✕
        </button>
      </div>

      <div className="span-metadata-grid">
        <div className="meta-card">
          <div className="meta-label">Policy Decision</div>
          <div className={`meta-value font-semibold ${decisionClass}`} data-testid="span-policy-decision">
            {span.policy_decision ? span.policy_decision.toUpperCase() : 'NONE'}
          </div>
        </div>

        <div className="meta-card">
          <div className="meta-label">Matched Rule ID</div>
          <div className="meta-value font-mono text-xs" data-testid="span-rule-id">
            {span.policy_rule_id || 'default_action'}
          </div>
        </div>

        <div className="meta-card">
          <div className="meta-label">Policy Version</div>
          <div className="meta-value font-mono text-xs" data-testid="span-policy-version">
            {span.policy_version_id || 'N/A'}
          </div>
        </div>

        <div className="meta-card">
          <div className="meta-label">Redactions Count</div>
          <div className="meta-value font-semibold" data-testid="span-redaction-count">
            {span.redaction_count > 0 ? (
              <span className="text-emerald-400">🛡️ {span.redaction_count} redacted</span>
            ) : (
              <span className="text-slate-400">0</span>
            )}
          </div>
        </div>

        <div className="meta-card">
          <div className="meta-label">Sequence #</div>
          <div className="meta-value font-mono">{span.sequence_number}</div>
        </div>

        <div className="meta-card">
          <div className="meta-label">Execution Latency</div>
          <div className="meta-value font-mono">{span.latency_ms} ms</div>
        </div>
      </div>

      {span.token_counts && Object.keys(span.token_counts).length > 0 && (
        <div className="tokens-summary">
          <span className="text-slate-400 text-xs">Tokens: </span>
          <span className="font-mono text-xs text-slate-200">
            Prompt: {span.token_counts.prompt_tokens || 0} | Completion: {span.token_counts.completion_tokens || 0} | Total: {span.token_counts.total_tokens || 0}
          </span>
        </div>
      )}

      {span.error && (
        <div className="error-banner" data-testid="span-error-banner">
          <div className="font-semibold text-rose-300 text-sm mb-1">Execution / Policy Error:</div>
          <pre className="error-text font-mono text-xs text-rose-200">{span.error}</pre>
        </div>
      )}

      {span.injection_flag && (
        <div className="injection-alert-banner p-3 my-3 rounded-lg border border-rose-500/30 bg-rose-950/20" data-testid="span-injection-alert">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-rose-400 font-bold text-sm">🛡️ PROMPT INJECTION DETECTED</span>
            <span className="badge-action bg-rose-900/60 text-rose-300 text-xs px-2 py-0.5 rounded font-mono uppercase">
              Action: {span.injection_details?.action_taken || span.injection_details?.action || 'BLOCK'}
            </span>
          </div>
          {span.injection_details?.reason && (
            <div className="text-xs text-rose-200/90 mb-2 font-mono">
              Reason: {span.injection_details.reason}
            </div>
          )}
          {span.injection_details?.matches && Array.isArray(span.injection_details.matches) && (
            <div className="injection-matches mt-2">
              <div className="text-xs font-semibold text-slate-300 mb-1">Matched Patterns ({span.injection_details.matches.length}):</div>
              <div className="space-y-1">
                {span.injection_details.matches.map((m: any, idx: number) => (
                  <div key={idx} className="text-xs font-mono bg-slate-900/80 px-2 py-1 rounded text-slate-300 border border-slate-700/50 flex justify-between">
                    <span>
                      <span className="text-amber-400 font-semibold">[{m.category}]</span> {m.pattern_name}
                    </span>
                    <span className="text-slate-400 text-[11px]">
                      via {m.detector} (offsets {m.start_offset}-{m.end_offset})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="payloads-section">
        <div className="payload-block">
          <h4 className="section-title">Input Payload (Redacted & Truncatable)</h4>
          <SafePayloadViewer payload={span.input_payload} label="Tool / Model Input Arguments" />
        </div>

        <div className="payload-block">
          <h4 className="section-title">Output Payload</h4>
          <SafePayloadViewer payload={span.output_payload} label="Return Result / Response" />
        </div>
      </div>
    </div>
  )
}
