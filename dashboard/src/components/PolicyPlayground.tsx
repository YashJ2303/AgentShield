import React, { useState } from 'react'
import {
  Check,
  X,
  Shield,
  RefreshCw,
  Flame,
  Terminal,
  Zap,
  AlertTriangle,
} from 'lucide-react'
import { simulatePolicyCall } from '../services/api'

interface PolicyPlaygroundProps {
  initialPayload?: any
}

interface AttackPreset {
  id: string
  name: string
  tool: string
  rule: string
  category: string
  payload: any
  expectedVerdict: 'deny' | 'require_approval' | 'allow'
}

const ATTACK_PRESETS: AttackPreset[] = [
  {
    id: 'atk-sql-drop',
    name: 'Destructive DDL DROP',
    tool: 'execute_sql',
    rule: 'sql_select_only',
    category: 'SQL Injection',
    payload: { query: 'DROP TABLE users; -- comment' },
    expectedVerdict: 'deny',
  },
  {
    id: 'atk-sql-comment',
    name: 'Recursive Comment Bypass',
    tool: 'execute_sql',
    rule: 'sql_select_only',
    category: 'SQL Injection',
    payload: { query: 'SELECT * FROM accounts WHERE id=1 /*!50000; TRUNCATE users*/;' },
    expectedVerdict: 'deny',
  },
  {
    id: 'atk-ssrf-decimal',
    name: 'Decimal SSRF (2852039166)',
    tool: 'http_request',
    rule: 'allow_whitelisted_http',
    category: 'Network SSRF',
    payload: { url: 'http://2852039166/latest/meta-data/credentials' },
    expectedVerdict: 'deny',
  },
  {
    id: 'atk-path-traversal',
    name: 'Path Traversal (../../etc/passwd)',
    tool: 'file_system',
    rule: 'sandbox_filesystem',
    category: 'Local File Inclusion',
    payload: { path: '../../../../etc/shadow', action: 'read' },
    expectedVerdict: 'deny',
  },
  {
    id: 'atk-wire-high',
    name: 'High-Value Wire Transfer ($250k)',
    tool: 'wire_transfer',
    rule: 'require_approval_high_value',
    category: 'Excessive Agency',
    payload: { amount: 250000.0, recipient: 'acct_unauthorized_offshore' },
    expectedVerdict: 'require_approval',
  },
  {
    id: 'benign-select',
    name: 'Benign Read-Only SELECT',
    tool: 'execute_sql',
    rule: 'sql_select_only',
    category: 'Authorized Workload',
    payload: { query: 'SELECT id, username, email FROM users WHERE active = true LIMIT 50;' },
    expectedVerdict: 'allow',
  },
]

export const PolicyPlayground: React.FC<PolicyPlaygroundProps> = ({ initialPayload }) => {
  const [toolName, setToolName] = useState<string>('execute_sql')
  const [payloadText, setPayloadText] = useState<string>(
    initialPayload
      ? JSON.stringify(initialPayload, null, 2)
      : JSON.stringify({ query: 'DROP TABLE users;' }, null, 2)
  )
  const [activeRule, setActiveRule] = useState<string>('sql_select_only')
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [terminalLogs, setTerminalLogs] = useState<string[]>([])

  const [result, setResult] = useState<{
    verdict: string
    rule: string
    reason: string
    latency_ms: number
    redactions: number
  } | null>(null)
  const [evaluating, setEvaluating] = useState<boolean>(false)

  const handleSelectPreset = (preset: AttackPreset) => {
    setActivePreset(preset.id)
    setToolName(preset.tool)
    setActiveRule(preset.rule)
    setPayloadText(JSON.stringify(preset.payload, null, 2))
    setResult(null)
    setTerminalLogs([])
  }

  const handleEvaluate = async () => {
    setEvaluating(true)
    let parsed: any = {}
    try {
      parsed = JSON.parse(payloadText)
    } catch (e) {
      parsed = { query: payloadText }
    }

    setTerminalLogs([
      `Ingress tool invocation dispatched: tool="${toolName}"`,
      `Evaluating payload against live AgentShield policy engine...`,
    ])

    try {
      const res = await simulatePolicyCall({
        tool_name: toolName,
        tool_args: parsed,
      })

      const verdict = res.decision
      const reason = res.reason || (verdict === 'allow' ? 'Invocation passed all policy checks' : 'Invocation rejected by policy check')
      const rule = res.rule_id || activeRule

      setTerminalLogs((prev) => [
        ...prev,
        `Gateway response: ${verdict.toUpperCase()}`,
        res.rule_id ? `Matched rule: ${res.rule_id}` : `No blocking rule matched`,
        `Reason: ${reason}`,
        `Check latency: ${res.latency_ms ?? 0} ms`,
      ])

      setResult({
        verdict,
        rule,
        reason,
        latency_ms: res.latency_ms ?? 0,
        redactions: 0,
      })
    } catch (err: any) {
      setTerminalLogs((prev) => [
        ...prev,
        `Gateway evaluation failed: ${err.message || 'Network / server error'}`,
      ])
    } finally {
      setEvaluating(false)
    }
  }

  return (
    <div className="workspace-viewport" data-testid="policy-playground-view">
      {/* Header */}
      <div className="view-header">
        <div className="view-title-wrap">
          <div>
            <div className="evaluate-header-title">Operate: Live Gateway Policy Verification</div>
            <h2 className="view-title" style={{ marginTop: '0.2rem' }}>
              Policy Playground
            </h2>
          </div>
        </div>
        <div className="header-badges-wrap">
          <div className="badge-status-online">
            <span className="status-dot-green"></span>
            Live Gateway AST Engine
          </div>
        </div>
      </div>

      {/* Attack Presets */}
      <div className="panel-card" style={{ marginBottom: '1.25rem' }}>
        <div className="panel-header">
          <h3 className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Flame size={15} className="text-crimson" />
            Attack & Benign Test Payloads
          </h3>
        </div>
        <p className="chart-subtitle-note">
          Select an attack preset to populate the arguments and verify live AST enforcement against the running policy engine.
        </p>

        <div className="arsenal-chips-bar">
          {ATTACK_PRESETS.map((preset) => {
            const isSelected = activePreset === preset.id
            const isDeny = preset.expectedVerdict === 'deny'
            const isApproval = preset.expectedVerdict === 'require_approval'
            return (
              <button
                key={preset.id}
                type="button"
                className={`arsenal-chip ${isSelected ? 'arsenal-chip-active' : ''}`}
                onClick={() => handleSelectPreset(preset)}
                data-testid={`btn-preset-${preset.id}`}
              >
                <span className={`chip-badge ${isDeny ? 'chip-red' : isApproval ? 'chip-amber' : 'chip-green'}`}>
                  {preset.category}
                </span>
                <span className="chip-name">{preset.name}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="middle-grid" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
        {/* Input Configuration Panel */}
        <div className="panel-card">
          <div className="panel-header">
            <h3 className="panel-title">Invocation Arguments Payload</h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
                Target Tool
              </label>
              <select
                value={toolName}
                onChange={(e) => {
                  const val = e.target.value
                  setToolName(val)
                  if (val === 'execute_sql') {
                    setActiveRule('sql_select_only')
                    setPayloadText(JSON.stringify({ query: 'DROP TABLE users;' }, null, 2))
                  } else if (val === 'wire_transfer') {
                    setActiveRule('require_approval_high_value')
                    setPayloadText(JSON.stringify({ amount: 250000.0, recipient: 'acct_892147' }, null, 2))
                  } else if (val === 'http_request') {
                    setActiveRule('allow_whitelisted_http')
                    setPayloadText(JSON.stringify({ url: 'http://169.254.169.254/latest/meta-data/' }, null, 2))
                  } else {
                    setActiveRule('sandbox_filesystem')
                    setPayloadText(JSON.stringify({ path: '../../etc/passwd', action: 'read' }, null, 2))
                  }
                  setActivePreset(null)
                }}
                className="select-field"
                style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
                data-testid="select-target-tool"
              >
                <option value="execute_sql">execute_sql</option>
                <option value="wire_transfer">wire_transfer</option>
                <option value="http_request">http_request</option>
                <option value="file_system">file_system</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
                Enforced Security Rule
              </label>
              <input
                type="text"
                readOnly
                value={activeRule}
                className="input-field"
                style={{ width: '100%', fontFamily: 'var(--font-mono)', color: 'var(--mint-light)' }}
              />
            </div>
          </div>

          <div style={{ marginBottom: '1rem', flex: 1, display: 'flex', flexDirection: 'column' }}>
            <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Input Arguments (JSON)
            </label>
            <textarea
              value={payloadText}
              onChange={(e) => setPayloadText(e.target.value)}
              rows={8}
              className="input-field font-mono"
              style={{ width: '100%', resize: 'vertical' }}
              data-testid="textarea-payload"
            />
          </div>

          <button
            type="button"
            className="btn-approve-primary"
            onClick={handleEvaluate}
            disabled={evaluating}
            style={{ width: '100%', height: '42px', fontSize: '0.9rem', gap: '0.5rem' }}
            data-testid="btn-evaluate-policy"
          >
            {evaluating ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Zap size={16} className="text-mint" />
            )}
            Evaluate via Live Gateway Check
          </button>
        </div>

        {/* Verdict & Audit Output Panel */}
        <div className="panel-card">
          <div className="panel-header">
            <h3 className="panel-title">Gateway Verdict & Live Trace</h3>
          </div>

          {result ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.85rem 1rem',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor:
                    result.verdict === 'allow'
                      ? 'rgba(16, 185, 129, 0.1)'
                      : result.verdict === 'deny'
                      ? 'rgba(239, 68, 68, 0.1)'
                      : 'rgba(245, 158, 11, 0.1)',
                  border: `1px solid ${
                    result.verdict === 'allow'
                      ? 'var(--mint)'
                      : result.verdict === 'deny'
                      ? 'var(--coral)'
                      : 'var(--amber)'
                  }`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {result.verdict === 'allow' && <Check size={18} className="text-mint" />}
                  {result.verdict === 'deny' && <X size={18} className="text-coral" />}
                  {result.verdict === 'require_approval' && <AlertTriangle size={18} className="text-amber" />}
                  <span
                    style={{
                      fontWeight: 700,
                      fontSize: '0.95rem',
                      textTransform: 'uppercase',
                      color:
                        result.verdict === 'allow'
                          ? 'var(--mint)'
                          : result.verdict === 'deny'
                          ? 'var(--coral-light)'
                          : 'var(--amber-light)',
                    }}
                  >
                    {result.verdict.replace('_', ' ')}
                  </span>
                </div>

                <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  {result.latency_ms} ms check
                </span>
              </div>

              <div className="policy-at-time-box">
                <div className="policy-card-subtitle">AST Evaluator Summary</div>
                <div className="policy-matched-rule">
                  Rule evaluated: <strong className="text-mint">{result.rule}</strong>
                </div>
                <div className="policy-reason-text">
                  {result.reason}
                </div>
              </div>

              {/* Terminal Trace Log */}
              <div className="terminal-trace-box font-mono">
                <div className="terminal-trace-header">
                  <Terminal size={12} className="text-mint" />
                  <span>Gateway Trace Log</span>
                </div>
                <div className="terminal-trace-lines">
                  {terminalLogs.map((log, i) => (
                    <div key={i} className="terminal-trace-line">{log}</div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '280px',
                color: 'var(--text-muted)',
                fontSize: '0.8rem',
              }}
            >
              <Shield size={38} style={{ marginBottom: '0.75rem', opacity: 0.3 }} />
              <span>Select an attack preset or click "Evaluate via Live Gateway Check"</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
