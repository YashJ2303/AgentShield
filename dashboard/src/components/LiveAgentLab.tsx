import React, { useState, useEffect, useCallback } from 'react'
import {
  RefreshCw,
  Zap,
  Bot,
  Check,
  X,
  AlertTriangle,
  Clock,
  Server,
  Terminal,
  KeyRound,
  GitCompareArrows,
} from 'lucide-react'
import {
  fetchLiveProviders,
  fetchLiveScenarios,
  executeLiveScenario,
  invokeLiveTool,
  compareLiveModels,
  LiveProvider,
  LiveProviderMode,
  LiveScenarioSpec,
  LiveAgentResult,
  LiveCompareModelsResponse,
} from '../services/api'
import { SafePayloadViewer } from './SafePayloadViewer'

interface LiveAgentLabProps {
  onNavigateToApprovals?: () => void
}

const MODE_STYLES: Record<LiveProviderMode | string, { color: string; bg: string; border: string; label: string }> = {
  live: { color: 'var(--mint)', bg: 'rgba(16, 185, 129, 0.1)', border: 'rgba(16, 185, 129, 0.4)', label: 'LIVE' },
  simulated: { color: 'var(--amber)', bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.4)', label: 'SIMULATED' },
  unconfigured: { color: 'var(--text-muted)', bg: 'rgba(86, 120, 135, 0.08)', border: 'rgba(86, 120, 135, 0.3)', label: 'UNCONFIGURED' },
  offline: { color: 'var(--coral)', bg: 'rgba(239, 68, 68, 0.1)', border: 'rgba(239, 68, 68, 0.4)', label: 'OFFLINE' },
  blocked: { color: 'var(--coral)', bg: 'rgba(239, 68, 68, 0.1)', border: 'rgba(239, 68, 68, 0.4)', label: 'BLOCKED' },
}

const DECISION_STYLES: Record<string, { color: string; bg: string; border: string; label: string }> = {
  allow: { color: 'var(--mint)', bg: 'rgba(16, 185, 129, 0.1)', border: 'var(--mint)', label: 'ALLOW' },
  deny: { color: 'var(--coral-light)', bg: 'rgba(239, 68, 68, 0.1)', border: 'var(--coral)', label: 'DENY' },
  require_approval: { color: 'var(--amber-light)', bg: 'rgba(245, 158, 11, 0.1)', border: 'var(--amber)', label: 'REQUIRE_APPROVAL' },
}

const FALLBACK_DECISION = { color: 'var(--text-secondary)', bg: 'rgba(86, 120, 135, 0.08)', border: 'var(--text-muted)', label: 'UNKNOWN' }

const ModeBadge: React.FC<{ mode: string; testId?: string }> = ({ mode, testId }) => {
  const style = MODE_STYLES[mode] || MODE_STYLES.unconfigured
  return (
    <span
      data-testid={testId}
      style={{
        fontSize: '0.62rem',
        fontWeight: 700,
        letterSpacing: '0.06em',
        padding: '2px 8px',
        borderRadius: 'var(--radius-pill)',
        color: style.color,
        backgroundColor: style.bg,
        border: `1px solid ${style.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      {style.label}
    </span>
  )
}

/**
 * Shared result renderer for scenario execution, free-form tool invocation.
 * Shows the policy decision, matched rule, latency/cost metrics, execution mode,
 * and the provider API response in a safe collapsible viewer.
 */
export const LiveRunResultCard: React.FC<{
  result: LiveAgentResult
  onNavigateToApprovals?: () => void
  testId?: string
}> = ({ result, onNavigateToApprovals, testId = 'live-run-result' }) => {
  const decision = DECISION_STYLES[result.policy_decision] || FALLBACK_DECISION
  return (
    <div
      data-testid={testId}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        padding: '0.9rem 1rem',
        borderRadius: 'var(--radius-md)',
        backgroundColor: 'var(--bg-code)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {/* Decision + mode header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {result.policy_decision === 'allow' && <Check size={16} style={{ color: decision.color }} />}
          {result.policy_decision === 'deny' && <X size={16} style={{ color: decision.color }} />}
          {result.policy_decision === 'require_approval' && <AlertTriangle size={16} style={{ color: decision.color }} />}
          <span
            data-testid={`${testId}-decision`}
            style={{ fontWeight: 700, fontSize: '0.85rem', letterSpacing: '0.03em', color: decision.color }}
          >
            {decision.label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <ModeBadge mode={result.execution_mode} testId={`${testId}-mode`} />
          {result.tool_name && (
            <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              {result.tool_name}
            </span>
          )}
        </div>
      </div>

      {/* Rule & reason */}
      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
        {result.policy_rule_id ? (
          <span>
            Rule: <strong style={{ color: 'var(--mint-light)', fontFamily: 'var(--font-mono)' }}>{result.policy_rule_id}</strong>
          </span>
        ) : (
          <span>No blocking rule matched</span>
        )}
        {result.reason && <div style={{ marginTop: '0.25rem', color: 'var(--text-muted)' }}>{result.reason}</div>}
      </div>

      {/* Metrics row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
        <span data-testid={`${testId}-latency`}>{result.latency_ms ?? 0} ms</span>
        <span data-testid={`${testId}-cost`}>${(result.cost_usd ?? 0).toFixed(6)}</span>
        <span data-testid={`${testId}-redactions`}>{result.redactions_applied ?? 0} redactions</span>
        {result.run_id && <span>run: {result.run_id}</span>}
      </div>

      {/* Approval handoff hint */}
      {result.approval_id && (
        <div
          data-testid={`${testId}-approval`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.5rem 0.75rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'rgba(245, 158, 11, 0.08)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            fontSize: '0.75rem',
            color: 'var(--amber-light)',
          }}
        >
          <Clock size={13} />
          <span>
            Approval <strong style={{ fontFamily: 'var(--font-mono)' }}>{result.approval_id}</strong> is pending — review it in the
            Approvals tab.
          </span>
          {onNavigateToApprovals && (
            <button
              type="button"
              onClick={onNavigateToApprovals}
              style={{
                marginLeft: 'auto',
                background: 'transparent',
                border: '1px solid rgba(245, 158, 11, 0.4)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--amber-light)',
                fontSize: '0.7rem',
                padding: '3px 10px',
                cursor: 'pointer',
              }}
            >
              Go to Approvals
            </button>
          )}
        </div>
      )}

      {/* Provider API payload */}
      {result.api_response !== undefined && result.api_response !== null && (
        <SafePayloadViewer payload={result.api_response} label="Provider API Response" maxChars={600} />
      )}
    </div>
  )
}

export const LiveAgentLab: React.FC<LiveAgentLabProps> = ({ onNavigateToApprovals }) => {
  // ---- Provider strip state ----
  const [providers, setProviders] = useState<LiveProvider[]>([])
  const [providersLoading, setProvidersLoading] = useState<boolean>(false)
  const [providersError, setProvidersError] = useState<string | null>(null)

  // ---- Scenario launcher state ----
  const [scenarios, setScenarios] = useState<LiveScenarioSpec[]>([])
  const [scenariosLoading, setScenariosLoading] = useState<boolean>(false)
  const [scenariosError, setScenariosError] = useState<string | null>(null)
  const [scenarioResults, setScenarioResults] = useState<Record<string, LiveAgentResult>>({})
  const [scenarioErrors, setScenarioErrors] = useState<Record<string, string>>({})
  const [runningScenarios, setRunningScenarios] = useState<Record<string, boolean>>({})
  const [runningAll, setRunningAll] = useState<boolean>(false)

  // ---- Live Test Agent state ----
  const [toolName, setToolName] = useState<string>('github_tool')
  const [toolArgsText, setToolArgsText] = useState<string>('{\n  "owner": "pallets",\n  "repo": "flask"\n}')
  const [toolIntent, setToolIntent] = useState<string>('')
  const [toolJsonError, setToolJsonError] = useState<string | null>(null)
  const [toolResult, setToolResult] = useState<LiveAgentResult | null>(null)
  const [toolError, setToolError] = useState<string | null>(null)
  const [invoking, setInvoking] = useState<boolean>(false)

  // ---- Model comparator state ----
  const [comparePrompt, setComparePrompt] = useState<string>('Compare the security posture of these two policies for SQL tool access.')
  const [modelA, setModelA] = useState<string>('gemini-2.5-flash')
  const [modelB, setModelB] = useState<string>('gpt-4o')
  const [compareResult, setCompareResult] = useState<LiveCompareModelsResponse | null>(null)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [comparing, setComparing] = useState<boolean>(false)

  const loadProviders = useCallback(async () => {
    setProvidersLoading(true)
    setProvidersError(null)
    try {
      const data = await fetchLiveProviders()
      setProviders(data.providers || [])
    } catch (err: any) {
      setProvidersError(err.message || 'Failed to load providers')
      setProviders([])
    } finally {
      setProvidersLoading(false)
    }
  }, [])

  const loadScenarios = useCallback(async () => {
    setScenariosLoading(true)
    setScenariosError(null)
    try {
      const data = await fetchLiveScenarios()
      setScenarios(data || [])
    } catch (err: any) {
      setScenariosError(err.message || 'Failed to load scenarios')
      setScenarios([])
    } finally {
      setScenariosLoading(false)
    }
  }, [])

  useEffect(() => {
    loadProviders()
    loadScenarios()
  }, [loadProviders, loadScenarios])

  const handleRunScenario = useCallback(
    async (scenarioId: string) => {
      setRunningScenarios((prev) => ({ ...prev, [scenarioId]: true }))
      setScenarioErrors((prev) => {
        const next = { ...prev }
        delete next[scenarioId]
        return next
      })
      try {
        const result = await executeLiveScenario(scenarioId)
        setScenarioResults((prev) => ({ ...prev, [scenarioId]: result }))
      } catch (err: any) {
        setScenarioErrors((prev) => ({ ...prev, [scenarioId]: err.message || 'Failed to execute scenario' }))
      } finally {
        setRunningScenarios((prev) => ({ ...prev, [scenarioId]: false }))
      }
    },
    []
  )

  const handleRunAllScenarios = useCallback(async () => {
    if (scenarios.length === 0) return
    setRunningAll(true)
    for (const scenario of scenarios) {
      await handleRunScenario(scenario.id)
    }
    setRunningAll(false)
  }, [scenarios, handleRunScenario])

  const handleInvokeTool = useCallback(async () => {
    setToolJsonError(null)
    setToolError(null)

    if (!toolName.trim()) {
      setToolError('Tool name is required.')
      return
    }

    let parsedArgs: Record<string, any>
    try {
      parsedArgs = JSON.parse(toolArgsText || '{}')
      if (typeof parsedArgs !== 'object' || parsedArgs === null || Array.isArray(parsedArgs)) {
        setToolJsonError('Tool args must be a JSON object.')
        return
      }
    } catch {
      setToolJsonError('Tool args must be valid JSON.')
      return
    }

    setInvoking(true)
    try {
      const result = await invokeLiveTool(
        toolName.trim(),
        parsedArgs,
        toolIntent.trim() || undefined
      )
      setToolResult(result)
    } catch (err: any) {
      setToolResult(null)
      setToolError(err.message || 'Failed to invoke tool')
    } finally {
      setInvoking(false)
    }
  }, [toolName, toolArgsText, toolIntent])

  const handleCompareModels = useCallback(async () => {
    if (!comparePrompt.trim()) {
      setCompareError('Prompt is required.')
      return
    }
    if (!modelA.trim() || !modelB.trim()) {
      setCompareError('Both model IDs are required.')
      return
    }
    setComparing(true)
    setCompareError(null)
    try {
      const data = await compareLiveModels(comparePrompt.trim(), modelA.trim(), modelB.trim())
      setCompareResult(data)
    } catch (err: any) {
      setCompareResult(null)
      setCompareError(err.message || 'Failed to compare models')
    } finally {
      setComparing(false)
    }
  }, [comparePrompt, modelA, modelB])

  return (
    <div className="workspace-viewport" data-testid="live-agent-lab-view">
      {/* Header */}
      <div className="view-header">
        <div className="view-title-wrap">
          <div>
            <div className="evaluate-header-title">Operate: Real-World API Calls Through the Gateway</div>
            <h2 className="view-title" style={{ marginTop: '0.2rem' }}>
              Live Agent Lab
            </h2>
          </div>
        </div>
        <div className="header-badges-wrap">
          <div className="badge-status-online">
            <span className="status-dot-green"></span>
            Guardrails Enforced In-Path
          </div>
        </div>
      </div>

      {/* ================= Provider Status Strip ================= */}
      <div className="panel-card" style={{ marginBottom: '1.25rem' }}>
        <div className="panel-header">
          <h3 className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Server size={15} style={{ color: 'var(--mint)' }} />
            Provider Connectivity
          </h3>
          <button
            type="button"
            onClick={loadProviders}
            disabled={providersLoading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              background: 'transparent',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-secondary)',
              fontSize: '0.72rem',
              padding: '5px 12px',
              cursor: 'pointer',
            }}
            data-testid="btn-refresh-providers"
          >
            <RefreshCw size={12} className={providersLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {providersLoading && providers.length === 0 ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }} data-testid="providers-loading">
            Loading provider connectivity status...
          </div>
        ) : providersError ? (
          <div
            style={{
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: 'var(--coral-light)',
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
            data-testid="providers-error"
          >
            <AlertTriangle size={14} />
            {providersError}
          </div>
        ) : providers.length === 0 ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }} data-testid="providers-empty">
            No providers registered on the gateway.
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
              gap: '0.75rem',
            }}
            data-testid="providers-strip"
          >
            {providers.map((provider) => (
              <div
                key={provider.id}
                data-testid={`provider-card-${provider.id}`}
                style={{
                  padding: '0.85rem 1rem',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--bg-code)',
                  border: `1px solid ${(MODE_STYLES[provider.mode] || MODE_STYLES.unconfigured).border}`,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.4rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3 }}>
                    {provider.name}
                  </span>
                  <ModeBadge mode={provider.mode} testId={`provider-mode-${provider.id}`} />
                </div>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{provider.category}</span>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>{provider.detail}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '0.15rem' }}>
                  {provider.auth_required ? (
                    <>
                      <KeyRound size={11} style={{ color: 'var(--amber)' }} />
                      <span style={{ fontSize: '0.66rem', color: 'var(--amber)' }}>Auth required</span>
                    </>
                  ) : (
                    <>
                      <KeyRound size={11} style={{ color: 'var(--text-dim)' }} />
                      <span style={{ fontSize: '0.66rem', color: 'var(--text-dim)' }}>Zero-auth</span>
                    </>
                  )}
                  {!provider.configured && (
                    <span style={{ fontSize: '0.66rem', color: 'var(--text-dim)', marginLeft: 'auto' }}>not configured</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ================= Scenario Launcher ================= */}
      <div className="panel-card" style={{ marginBottom: '1.25rem' }}>
        <div className="panel-header">
          <h3 className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Zap size={15} style={{ color: 'var(--amber)' }} />
            Scenario Launcher
          </h3>
          <button
            type="button"
            onClick={handleRunAllScenarios}
            disabled={runningAll || scenarios.length === 0}
            className="btn-approve-primary"
            style={{ padding: '0.45rem 1rem', fontSize: '0.75rem' }}
            data-testid="btn-run-all-scenarios"
          >
            {runningAll ? <RefreshCw size={13} className="animate-spin" /> : <Zap size={13} />}
            {runningAll ? 'Running all...' : 'Run all scenarios'}
          </button>
        </div>
        <p className="chart-subtitle-note">
          Fire a real-world API request through the AgentShield gateway and watch the guardrail verdict on the same card.
        </p>

        {scenariosLoading && scenarios.length === 0 ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }} data-testid="scenarios-loading">
            Loading scenarios...
          </div>
        ) : scenariosError ? (
          <div
            style={{
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: 'var(--coral-light)',
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
            data-testid="scenarios-error"
          >
            <AlertTriangle size={14} />
            {scenariosError}
          </div>
        ) : scenarios.length === 0 ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }} data-testid="scenarios-empty">
            No scenarios available.
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '0.85rem',
            }}
          >
            {scenarios.map((scenario) => {
              const isRunning = !!runningScenarios[scenario.id]
              const result = scenarioResults[scenario.id]
              const runError = scenarioErrors[scenario.id]
              return (
                <div
                  key={scenario.id}
                  data-testid={`scenario-card-${scenario.id}`}
                  style={{
                    padding: '1rem',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: 'var(--bg-code)',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.5rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '1.15rem' }}>{scenario.icon}</span>
                      <div>
                        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>{scenario.name}</div>
                        <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>{scenario.category}</div>
                      </div>
                    </div>
                    <ModeBadge mode={scenario.execution_mode} testId={`scenario-mode-${scenario.id}`} />
                  </div>

                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                    {scenario.description}
                  </span>

                  <div style={{ fontSize: '0.66rem', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', wordBreak: 'break-all' }}>
                    {scenario.target_api}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', marginTop: '0.25rem' }}>
                    <span style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>
                      expected:{' '}
                      <strong
                        style={{
                          color:
                            scenario.expected_verdict === 'allow'
                              ? 'var(--mint)'
                              : scenario.expected_verdict === 'deny'
                              ? 'var(--coral-light)'
                              : 'var(--amber-light)',
                          textTransform: 'uppercase',
                        }}
                      >
                        {scenario.expected_verdict}
                      </strong>
                    </span>
                    <button
                      type="button"
                      onClick={() => handleRunScenario(scenario.id)}
                      disabled={isRunning || runningAll}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.35rem',
                        background: 'transparent',
                        border: '1px solid var(--border-active)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--mint-light)',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        padding: '4px 12px',
                        cursor: isRunning ? 'wait' : 'pointer',
                      }}
                      data-testid={`btn-run-scenario-${scenario.id}`}
                    >
                      {isRunning ? <RefreshCw size={11} className="animate-spin" /> : <Zap size={11} />}
                      {isRunning ? 'Running...' : 'Run'}
                    </button>
                  </div>

                  {runError && (
                    <div
                      style={{
                        padding: '0.5rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        color: 'var(--coral-light)',
                        fontSize: '0.72rem',
                      }}
                      data-testid={`scenario-error-${scenario.id}`}
                    >
                      {runError}
                    </div>
                  )}

                  {result && (
                    <LiveRunResultCard
                      result={result}
                      onNavigateToApprovals={onNavigateToApprovals}
                      testId={`scenario-result-${scenario.id}`}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ================= Live Test Agent (free-form invocation) ================= */}
      <div className="middle-grid" style={{ gridTemplateColumns: '1.1fr 1fr', marginBottom: '1.25rem' }}>
        <div className="panel-card">
          <div className="panel-header">
            <h3 className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Bot size={15} style={{ color: 'var(--mint)' }} />
              Live Test Agent
            </h3>
          </div>
          <p className="chart-subtitle-note">
            Type any gateway tool name with raw JSON arguments and dispatch it through the live policy engine.
          </p>

          <div style={{ marginBottom: '0.85rem' }}>
            <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Tool Name
            </label>
            <input
              type="text"
              value={toolName}
              onChange={(e) => setToolName(e.target.value)}
              className="input-field"
              style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
              placeholder="e.g. github_tool"
              data-testid="input-tool-name"
            />
          </div>

          <div style={{ marginBottom: '0.85rem' }}>
            <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Tool Arguments (JSON)
            </label>
            <textarea
              value={toolArgsText}
              onChange={(e) => {
                setToolArgsText(e.target.value)
                setToolJsonError(null)
              }}
              rows={7}
              className="input-field font-mono"
              style={{
                width: '100%',
                resize: 'vertical',
                borderColor: toolJsonError ? 'var(--coral)' : undefined,
              }}
              data-testid="textarea-tool-args"
            />
            {toolJsonError && (
              <div
                style={{ marginTop: '0.35rem', fontSize: '0.72rem', color: 'var(--coral-light)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                data-testid="tool-json-error"
              >
                <AlertTriangle size={12} />
                {toolJsonError}
              </div>
            )}
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Agent Intent (optional)
            </label>
            <input
              type="text"
              value={toolIntent}
              onChange={(e) => setToolIntent(e.target.value)}
              className="input-field"
              style={{ width: '100%' }}
              placeholder="What is the agent trying to accomplish?"
              data-testid="input-tool-intent"
            />
          </div>

          <button
            type="button"
            onClick={handleInvokeTool}
            disabled={invoking}
            className="btn-approve-primary"
            style={{ width: '100%', height: '40px', fontSize: '0.85rem', gap: '0.5rem' }}
            data-testid="btn-invoke-tool"
          >
            {invoking ? <RefreshCw size={15} className="animate-spin" /> : <Terminal size={15} />}
            {invoking ? 'Dispatching through gateway...' : 'Dispatch Live Tool Call'}
          </button>
        </div>

        <div className="panel-card">
          <div className="panel-header">
            <h3 className="panel-title">Invocation Verdict</h3>
          </div>

          {toolError && (
            <div
              style={{
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: 'var(--coral-light)',
                fontSize: '0.78rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '0.75rem',
              }}
              data-testid="tool-invoke-error"
            >
              <AlertTriangle size={14} />
              {toolError}
            </div>
          )}

          {toolResult ? (
            <LiveRunResultCard
              result={toolResult}
              onNavigateToApprovals={onNavigateToApprovals}
              testId="tool-invoke-result"
            />
          ) : !toolError ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '260px',
                color: 'var(--text-muted)',
                fontSize: '0.8rem',
                textAlign: 'center',
              }}
              data-testid="tool-invoke-empty"
            >
              <Bot size={36} style={{ marginBottom: '0.75rem', opacity: 0.3 }} />
              <span>Dispatch a tool call to see the live guardrail verdict.</span>
            </div>
          ) : null}
        </div>
      </div>

      {/* ================= Model Comparator ================= */}
      <div className="panel-card" data-testid="live-model-comparator">
        <div className="panel-header">
          <h3 className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <GitCompareArrows size={15} style={{ color: 'var(--blue, #38bdf8)' }} />
            Live Model Comparator
          </h3>
        </div>
        <p className="chart-subtitle-note">
          Send the same prompt through two models and compare latency, token usage, and cost side by side.
        </p>

        <div style={{ marginBottom: '0.85rem' }}>
          <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
            Comparison Prompt
          </label>
          <textarea
            value={comparePrompt}
            onChange={(e) => setComparePrompt(e.target.value)}
            rows={3}
            className="input-field"
            style={{ width: '100%', resize: 'vertical' }}
            data-testid="textarea-compare-prompt"
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '0.75rem', alignItems: 'end', marginBottom: '1rem' }}>
          <div>
            <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Model A
            </label>
            <input
              type="text"
              value={modelA}
              onChange={(e) => setModelA(e.target.value)}
              className="input-field"
              style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
              data-testid="input-model-a"
            />
          </div>
          <div>
            <label style={{ fontSize: '0.725rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Model B
            </label>
            <input
              type="text"
              value={modelB}
              onChange={(e) => setModelB(e.target.value)}
              className="input-field"
              style={{ width: '100%', fontFamily: 'var(--font-mono)' }}
              data-testid="input-model-b"
            />
          </div>
          <button
            type="button"
            onClick={handleCompareModels}
            disabled={comparing}
            className="btn-approve-primary"
            style={{ padding: '0.55rem 1.1rem', fontSize: '0.78rem', whiteSpace: 'nowrap' }}
            data-testid="btn-compare-models"
          >
            {comparing ? <RefreshCw size={14} className="animate-spin" /> : <GitCompareArrows size={14} />}
            {comparing ? 'Comparing...' : 'Compare'}
          </button>
        </div>

        {compareError && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: 'var(--coral-light)',
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '0.75rem',
            }}
            data-testid="compare-error"
          >
            <AlertTriangle size={14} />
            {compareError}
          </div>
        )}

        {compareResult ? (
          <div data-testid="compare-results">
            {/* Comparison summary badges */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.85rem' }}>
              <span
                style={{
                  fontSize: '0.72rem',
                  padding: '4px 10px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  color: 'var(--mint-light)',
                }}
              >
                Cheaper: <strong>{compareResult.comparison.cheaper_model || 'n/a'}</strong>
              </span>
              <span
                style={{
                  fontSize: '0.72rem',
                  padding: '4px 10px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'rgba(56, 189, 248, 0.08)',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                  color: 'var(--blue, #38bdf8)',
                }}
              >
                Faster: <strong>{compareResult.comparison.faster_model || 'n/a'}</strong>
              </span>
              <span style={{ fontSize: '0.72rem', padding: '4px 10px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-code)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                Δcost ${compareResult.comparison.cost_delta_usd.toFixed(6)}
              </span>
              <span style={{ fontSize: '0.72rem', padding: '4px 10px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-code)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                Δlatency {compareResult.comparison.latency_delta_ms} ms
              </span>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Provider</th>
                    <th>Mode</th>
                    <th>Latency</th>
                    <th>Prompt Tokens</th>
                    <th>Completion Tokens</th>
                    <th>Total Tokens</th>
                    <th>Cost</th>
                    <th>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {compareResult.results.map((row) => {
                    const decision = DECISION_STYLES[row.policy_decision] || FALLBACK_DECISION
                    return (
                      <tr key={row.model} data-testid={`compare-row-${row.model}`}>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{row.model}</td>
                        <td style={{ color: 'var(--text-secondary)' }}>{row.provider}</td>
                        <td>
                          <ModeBadge mode={row.execution_mode} />
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{row.latency_ms} ms</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{row.prompt_tokens}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{row.completion_tokens}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{row.total_tokens}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>${row.cost_usd.toFixed(6)}</td>
                        <td>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, color: decision.color }}>
                            {decision.label}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Model responses */}
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(compareResult.results.length, 1)}, 1fr)`, gap: '0.75rem', marginTop: '0.85rem' }}>
              {compareResult.results.map((row) => (
                <SafePayloadViewer key={`resp-${row.model}`} payload={row.response} label={`${row.model} response`} maxChars={300} />
              ))}
            </div>
          </div>
        ) : (
          !compareError && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '140px',
                color: 'var(--text-muted)',
                fontSize: '0.8rem',
              }}
              data-testid="compare-empty"
            >
              <GitCompareArrows size={30} style={{ marginBottom: '0.6rem', opacity: 0.3 }} />
              <span>Run a comparison to see latency, tokens, and cost per model.</span>
            </div>
          )
        )}
      </div>
    </div>
  )
}
