import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Check,
  X,
  AlertTriangle,
  ShieldCheck,
  Clock,
  ShieldAlert,
  Database,
  Terminal,
  Zap,
  Activity,
  ArrowUpRight,
  Play,
  RotateCw,
  Search,
  Bell,
  ChevronDown,
  Download,
  Share2,
  Network,
  Shield,
  Layers,
} from 'lucide-react'
import { ApprovalItem, AnalyticsSummary, AnomalyItem, AnalyticsBreakdown, Run, RunFilters } from '../types'
import {
  ActivePolicyInfo,
  decideApproval,
  fetchActivePolicy,
  fetchApprovals,
  fetchAnalyticsSummary,
  fetchAnomalies,
  fetchAnalyticsBreakdown,
  fetchGatewayHealth,
  GatewayHealth,
  fetchRuns,
  triggerLiveDemoScenario,
  DemoScenarioType,
} from '../services/api'
import { Sparkline } from './Sparkline'

interface CommandCenterProps {
  onSelectRun: (runId: string) => void
  onNavigateToApprovals?: () => void
  onNavigateToRuns?: (filters?: Partial<RunFilters>) => void
  onNavigateToAnalytics?: () => void
  onNavigateToPlayground?: () => void
}

type TimeRangeId = '1h' | '24h' | '7d' | 'all'

const TIME_RANGES: { id: TimeRangeId; label: string; ms: number | null }[] = [
  { id: '1h', label: 'Last hour', ms: 60 * 60 * 1000 },
  { id: '24h', label: 'Last 24 hours', ms: 24 * 60 * 60 * 1000 },
  { id: '7d', label: 'Last 7 days', ms: 7 * 24 * 60 * 60 * 1000 },
  { id: 'all', label: 'All time', ms: null },
]

type TopoNodeKey = 'agents' | 'gateway' | 'guard' | 'allowed' | 'pending' | 'blocked'

interface PollHistory {
  toolCalls: number[]
  denied: number[]
  approvals: number[]
  p50: number[]
}

const EMPTY_HISTORY: PollHistory = { toolCalls: [], denied: [], approvals: [], p50: [] }

export const CommandCenter: React.FC<CommandCenterProps> = ({
  onSelectRun,
  onNavigateToApprovals,
  onNavigateToRuns,
  onNavigateToAnalytics,
  onNavigateToPlayground,
}) => {
  // Live State
  const [liveSummary, setLiveSummary] = useState<AnalyticsSummary | null>(null)
  const [liveApprovals, setLiveApprovals] = useState<ApprovalItem[]>([])
  const [liveAnomalies, setLiveAnomalies] = useState<AnomalyItem[]>([])
  const [liveBreakdown, setLiveBreakdown] = useState<AnalyticsBreakdown | null>(null)
  const [recentRuns, setRecentRuns] = useState<Run[]>([])
  const [isLoadingLive, setIsLoadingLive] = useState<boolean>(false)

  // Live gateway state (policy version + health) and interactive controls
  const [activePolicy, setActivePolicy] = useState<ActivePolicyInfo | null>(null)
  const [gatewayHealth, setGatewayHealth] = useState<GatewayHealth | null>(null)
  const [timeRange, setTimeRange] = useState<TimeRangeId>('24h')
  const [isRangeMenuOpen, setIsRangeMenuOpen] = useState<boolean>(false)
  const [pollHistory, setPollHistory] = useState<PollHistory>(EMPTY_HISTORY)
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [searchResults, setSearchResults] = useState<Run[]>([])
  const [isSearchOpen, setIsSearchOpen] = useState<boolean>(false)
  const [isNotifOpen, setIsNotifOpen] = useState<boolean>(false)
  const [hoveredNode, setHoveredNode] = useState<TopoNodeKey | null>(null)
  const [selectedNode, setSelectedNode] = useState<TopoNodeKey | null>(null)
  const [showScoreBreakdown, setShowScoreBreakdown] = useState<boolean>(false)
  const [headerNotice, setHeaderNotice] = useState<{ message: string; tone: 'info' | 'success' | 'error' } | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)

  // Live Demo Controller State
  const [demoToast, setDemoToast] = useState<{ message: string; type: 'success' | 'blocked' | 'pending' | 'info' } | null>(null)
  const [isExecutingDemo, setIsExecutingDemo] = useState<boolean>(false)

  // Current approval item for quick action
  const [approval, setApproval] = useState<ApprovalItem | null>(null)
  const [remainingSec, setRemainingSec] = useState<number>(45)
  const [approvalFeedback, setApprovalFeedback] = useState<string | null>(null)

  // Window start derived from the selected time range (undefined = all time)
  const rangeStart = useMemo(() => {
    const cfg = TIME_RANGES.find((r) => r.id === timeRange)
    return cfg?.ms ? new Date(Date.now() - cfg.ms).toISOString() : undefined
  }, [timeRange])

  const notify = useCallback((message: string, tone: 'info' | 'success' | 'error' = 'info') => {
    setHeaderNotice({ message, tone })
    window.setTimeout(() => setHeaderNotice(null), 4000)
  }, [])

  // Fetch live telemetry from gateway database
  const fetchLiveTelemetry = useCallback(async (isBackground = false) => {
    if (!isBackground) {
      setIsLoadingLive(true)
    }
    try {
      const [sum, apps, anoms, breakdown, runsData, policy, health] = await Promise.all([
        fetchAnalyticsSummary(rangeStart ? { start_date: rangeStart } : undefined).catch(() => null),
        fetchApprovals('pending').catch(() => []),
        fetchAnomalies(undefined, undefined, rangeStart).catch(() => []),
        fetchAnalyticsBreakdown(rangeStart).catch(() => null),
        fetchRuns({ limit: 12, offset: 0, start_date: rangeStart }).catch(() => ({ total: 0, runs: [] as Run[] })),
        fetchActivePolicy(),
        fetchGatewayHealth(),
      ])

      setLiveSummary(sum)
      setLiveApprovals(apps || [])
      setLiveAnomalies(anoms || [])
      setLiveBreakdown(breakdown)
      setRecentRuns(runsData?.runs || [])
      setActivePolicy(policy)
      setGatewayHealth(health)

      if (sum) {
        // Rolling history of the values actually observed by the dashboard poll.
        setPollHistory((prev) => {
          const push = (arr: number[], v: number) => [...arr, v].slice(-24)
          return {
            toolCalls: push(prev.toolCalls, sum.total_tool_calls ?? 0),
            denied: push(prev.denied, sum.blocked_runs ?? 0),
            approvals: push(prev.approvals, (apps || []).length),
            p50: push(prev.p50, Math.round(sum.p50_latency_ms ?? 0)),
          }
        })
      }

      if (apps && apps.length > 0) {
        setApproval(apps[0])
        setRemainingSec(Math.max(1, Math.round(apps[0].remaining_seconds || 45)))
      } else {
        setApproval(null)
      }
    } catch (err) {
      console.warn('Failed to fetch live telemetry:', err)
    } finally {
      if (!isBackground) {
        setIsLoadingLive(false)
      }
    }
  }, [rangeStart])

  // Auto-poll live telemetry every 3 seconds quietly in background
  useEffect(() => {
    fetchLiveTelemetry(false)
    const interval = setInterval(() => {
      fetchLiveTelemetry(true)
    }, 3000)
    return () => clearInterval(interval)
  }, [fetchLiveTelemetry])

  // Sparkline history belongs to one window only: reset when the range changes.
  useEffect(() => {
    setPollHistory(EMPTY_HISTORY)
  }, [timeRange])

  // Debounced run search against the gateway's full-text run search
  useEffect(() => {
    const q = searchQuery.trim()
    if (q.length < 2) {
      setSearchResults([])
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      fetchRuns({ search: q, limit: 6, offset: 0 })
        .then((data) => {
          if (!cancelled) setSearchResults(data.runs || [])
        })
        .catch(() => {
          if (!cancelled) setSearchResults([])
        })
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [searchQuery])

  const handleRunDemoScenario = async (scenario: DemoScenarioType) => {
    setIsExecutingDemo(true)
    setDemoToast({ message: `Triggering ${scenario} through live Gateway endpoints...`, type: 'info' })
    try {
      const res = await triggerLiveDemoScenario(scenario)
      setDemoToast({
        message: res.message,
        type: scenario === 'sql_attack' || scenario === 'path_traversal' ? 'blocked' : scenario === 'hitl_approval' ? 'pending' : 'success',
      })
      await fetchLiveTelemetry(true)
    } catch (err: any) {
      setDemoToast({ message: `API Error: ${err.message}`, type: 'blocked' })
    } finally {
      setIsExecutingDemo(false)
    }
  }

  // Countdown timer effect
  useEffect(() => {
    if (!approval) return
    const timer = setInterval(() => {
      setRemainingSec((prev) => (prev > 1 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [approval])

  // Format seconds to mm:ss
  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60)
    const secs = sec % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }

  // Handle Approve / Reject
  const handleDecision = useCallback(
    async (decision: 'approved' | 'rejected') => {
      if (!approval) return

      try {
        await decideApproval(
          approval.id,
          decision === 'approved' ? 'approve' : 'reject',
          `Command center hotkey: ${decision}`
        )
        setApprovalFeedback(
          decision === 'approved'
            ? '✓ Invocation approved and token dispatched.'
            : '✕ Invocation rejected and execution halted.'
        )

        setTimeout(() => {
          setApproval(null)
          fetchLiveTelemetry(true)
        }, 1000)
      } catch (err: any) {
        console.error('Failed to submit approval:', err)
        setApprovalFeedback(`Decision error: ${err.message || 'Failed'}`)
      }
    },
    [approval, fetchLiveTelemetry]
  )

  // Keyboard hotkeys: 'a' approve, 'r' reject, '/' focus the run search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const inField = ['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)
      if (inField) return

      if (e.key === '/') {
        e.preventDefault()
        searchInputRef.current?.focus()
      } else if (e.key === 'a' || e.key === 'A') {
        e.preventDefault()
        handleDecision('approved')
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        handleDecision('rejected')
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleDecision])

  // ---------------------------------------------------------------------
  // Derived metrics — every number below comes from the gateway payload.
  // When the gateway has no rows we surface "no telemetry" instead of a
  // fabricated score, so the dashboard can never look healthier than it is.
  // ---------------------------------------------------------------------
  const toolCallsCount = liveSummary?.total_tool_calls ?? 0
  const deniedCount = liveSummary?.blocked_runs ?? 0
  const totalRuns = liveSummary?.total_runs ?? 0
  const allowedRuns = Math.max(0, totalRuns - deniedCount)
  const deniedPct = totalRuns > 0
    ? ((deniedCount / totalRuns) * 100).toFixed(1)
    : '0.0'
  const allowPct = totalRuns > 0
    ? ((allowedRuns / totalRuns) * 100).toFixed(1)
    : '100.0'
  const pendingApprovalsCount = liveApprovals.length
  const hasData = totalRuns > 0
  const isDemoPopulated = hasData
  const rangeLabel = TIME_RANGES.find((r) => r.id === timeRange)?.label ?? 'Last 24 hours'

  const p50Latency = Math.round(liveSummary?.p50_latency_ms ?? 0)
  const p95Latency = Math.round(liveSummary?.p95_latency_ms ?? 0)
  const avgLatency = Math.round(liveSummary?.avg_latency_ms ?? 0)
  // Sub-millisecond policy checks are real: keep one decimal so "0ms" never
  // reads as missing telemetry.
  const rawP50 = liveSummary?.p50_latency_ms ?? 0
  const p50Display = rawP50 > 0 && rawP50 < 10 ? rawP50.toFixed(1) : String(p50Latency)
  const toolErrorRate = liveSummary?.tool_error_rate ?? 0

  const tools = liveBreakdown?.tools || []
  const deniedTools = tools
    .filter((t) => (t.policy_block_count || 0) > 0)
    .sort((a, b) => (b.policy_block_count || 0) - (a.policy_block_count || 0))
  const deniedToolCalls = deniedTools.reduce((acc, t) => acc + (t.policy_block_count || 0), 0)
  const allowedToolCalls = Math.max(0, toolCallsCount - deniedToolCalls)
  const distinctAgents = new Set(
    recentRuns.map((r) => r.agent_label || r.model || 'unlabeled agent')
  ).size
  const policyLabel = activePolicy ? `v${activePolicy.version_number}` : 'unavailable'
  const ruleCount = activePolicy?.rule_count ?? 0
  const topDenyingTool = deniedTools[0] || null

  // Transparent health score: allow-rate 60 + anomaly penalty 15 + HITL queue 10 + tool reliability 15
  const allowPoints = hasData ? Math.round((allowedRuns / totalRuns) * 60) : 0
  const anomalyPoints = hasData ? Math.max(0, 15 - liveAnomalies.length * 3) : 0
  const hitlPoints = hasData ? (pendingApprovalsCount === 0 ? 10 : Math.max(0, 10 - pendingApprovalsCount * 2)) : 0
  const reliabilityPoints = hasData ? Math.round(Math.max(0, Math.min(1, 1 - toolErrorRate)) * 15) : 0

  const scoreParts = [
    { label: 'Allow rate (weight 60)', detail: `${allowedRuns}/${totalRuns} runs allowed`, points: allowPoints, max: 60 },
    { label: 'Anomaly penalty (weight 15)', detail: `${liveAnomalies.length} anomalies in window (-3 each)`, points: anomalyPoints, max: 15 },
    { label: 'HITL queue (weight 10)', detail: `${pendingApprovalsCount} pending approvals (-2 each)`, points: hitlPoints, max: 10 },
    { label: 'Tool reliability (weight 15)', detail: `${(Math.max(0, Math.min(1, 1 - toolErrorRate)) * 100).toFixed(1)}% clean tool calls`, points: reliabilityPoints, max: 15 },
  ]

  const healthScore: number | null = hasData
    ? Math.max(0, Math.min(100, allowPoints + anomalyPoints + hitlPoints + reliabilityPoints))
    : null

  const healthLabel = healthScore === null
    ? 'No telemetry'
    : healthScore >= 85 ? 'Excellent' : healthScore >= 70 ? 'Operational' : 'Attention Required'
  const healthColor = healthScore === null
    ? '#94a3b8'
    : healthScore >= 85 ? '#2dd4bf' : healthScore >= 70 ? '#fbbf24' : '#f87171'
  const gatewayStatus = gatewayHealth?.status || 'unreachable'
  const gatewayBadgeColor = gatewayHealth?.status === 'healthy' ? '#34d399' : '#f87171'

  const arcRadius = 66
  const arcCircumference = Math.PI * arcRadius
  const arcOffset = arcCircumference - (arcCircumference * ((healthScore ?? 0) / 100))

  // Real threat attribution: share of tool calls that were denied, per tool.
  const THREAT_COLORS = ['#ef4444', '#f97316', '#a855f7']
  const threatSegments = useMemo(() => {
    if (toolCallsCount === 0) return [] as { key: string; label: string; count: number; color: string }[]
    const segments = deniedTools.slice(0, 3).map((t, i) => ({
      key: t.tool_name,
      label: t.tool_name,
      count: t.policy_block_count || 0,
      color: THREAT_COLORS[i % THREAT_COLORS.length],
    }))
    const rest = deniedTools.slice(3).reduce((acc, t) => acc + (t.policy_block_count || 0), 0)
    if (rest > 0) {
      segments.push({ key: 'other-denied', label: 'other tools', count: rest, color: '#64748b' })
    }
    if (allowedToolCalls > 0) {
      segments.push({ key: 'allowed', label: 'allowed', count: allowedToolCalls, color: '#10b981' })
    }
    return segments
  }, [liveBreakdown, toolCallsCount, deniedToolCalls, allowedToolCalls])

  // ---------------------------------------------------------------------
  // Navigation + control handlers
  // ---------------------------------------------------------------------
  const goToRuns = useCallback(
    (filters?: Partial<RunFilters>) => {
      onNavigateToRuns?.(filters)
    },
    [onNavigateToRuns]
  )
  const goToAnalytics = useCallback(() => onNavigateToAnalytics?.(), [onNavigateToAnalytics])
  const goToPlayground = useCallback(() => onNavigateToPlayground?.(), [onNavigateToPlayground])

  const handleExport = () => {
    const snapshot = {
      exported_at: new Date().toISOString(),
      time_range: rangeLabel,
      range_start: rangeStart ?? null,
      summary: liveSummary,
      active_policy: activePolicy,
      gateway_health: gatewayHealth,
      pending_approvals: liveApprovals,
      anomalies: liveAnomalies,
      tool_breakdown: tools,
      time_series: liveBreakdown?.time_series ?? [],
      recent_runs: recentRuns,
    }
    try {
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `agentshield-command-center-${Date.now()}.json`
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      URL.revokeObjectURL(url)
      notify('Telemetry snapshot exported as JSON', 'success')
    } catch (err: any) {
      notify(`Export failed: ${err?.message || err}`, 'error')
    }
  }

  const handleCopySummary = async () => {
    const summaryText = [
      `AgentShield command center — ${rangeLabel}`,
      `${totalRuns} runs · ${toolCallsCount} tool calls · ${deniedCount} blocked runs (${deniedPct}%)`,
      `${pendingApprovalsCount} pending approvals · ${liveAnomalies.length} anomalies`,
      `p50 ${p50Display}ms · p95 ${p95Latency}ms · avg ${avgLatency}ms`,
      activePolicy ? `policy v${activePolicy.version_number} (${activePolicy.rule_count} rules)` : 'policy unavailable',
    ].join('\n')
    try {
      if (!navigator?.clipboard?.writeText) {
        notify('Clipboard API unavailable in this browser', 'error')
        return
      }
      await navigator.clipboard.writeText(summaryText)
      notify('Summary copied to clipboard', 'success')
    } catch {
      notify('Clipboard write was blocked by the browser', 'error')
    }
  }

  // Topology detail bar content, derived from live counts
  const topoDetail: Record<TopoNodeKey, { title: string; detail: string; actionLabel: string; action: () => void }> = {
    agents: {
      title: 'Host Agents',
      detail: `${totalRuns} runs observed · ${distinctAgents} distinct agent/model label${distinctAgents === 1 ? '' : 's'} in the ${recentRuns.length} most recent runs`,
      actionLabel: 'Open runs',
      action: () => goToRuns(),
    },
    gateway: {
      title: 'Gateway /check',
      detail: `${toolCallsCount} tool calls evaluated · p50 ${p50Display}ms / p95 ${p95Latency}ms`,
      actionLabel: 'Compare models',
      action: () => goToPlayground(),
    },
    guard: {
      title: 'AST Guard',
      detail: activePolicy
        ? `Active policy ${policyLabel} with ${ruleCount} rules · ${deniedCount} runs blocked`
        : 'No active policy version reported by the gateway',
      actionLabel: 'Open analytics',
      action: () => goToAnalytics(),
    },
    allowed: {
      title: 'Allowed tool executions',
      detail: `${allowedToolCalls} of ${toolCallsCount} tool calls allowed (${toolCallsCount > 0 ? ((allowedToolCalls / toolCallsCount) * 100).toFixed(1) : '0.0'}%)`,
      actionLabel: 'View allowed runs',
      action: () => goToRuns({ outcome: 'success' }),
    },
    pending: {
      title: 'Human-in-the-loop queue',
      detail: `${pendingApprovalsCount} approval${pendingApprovalsCount === 1 ? '' : 's'} awaiting a decision`,
      actionLabel: 'Open approvals',
      action: () => onNavigateToApprovals?.(),
    },
    blocked: {
      title: 'Blocked tool executions',
      detail: `${deniedToolCalls} denied tool span${deniedToolCalls === 1 ? '' : 's'} across ${deniedTools.length} tool${deniedTools.length === 1 ? '' : 's'}`,
      actionLabel: 'View blocked runs',
      action: () => goToRuns({ outcome: 'blocked' }),
    },
  }

  const topoNode = (
    key: TopoNodeKey,
    cx: number,
    cy: number,
    radius: number,
    label: string,
    value: string,
    color: string,
    labelBelow = true,
  ) => {
    const interactive = true
    const isActive = hoveredNode === key || selectedNode === key
    return (
      <g
        key={key}
        transform={`translate(${cx}, ${cy})`}
        className={`topo-node${isActive ? ' topo-node-active' : ''}`}
        data-testid={`topo-node-${key}`}
        role="button"
        tabIndex={0}
        aria-label={`${label}: ${value}`}
        onClick={() => setSelectedNode(key)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setSelectedNode(key)
          }
        }}
        onMouseEnter={() => setHoveredNode(key)}
        onMouseLeave={() => setHoveredNode(null)}
        style={{ cursor: interactive ? 'pointer' : 'default' }}
      >
        <title>{`${label} — ${value}. Click for details.`}</title>
        {isActive && (
          <circle r={radius + 5} fill="none" stroke={color} strokeWidth="1" strokeDasharray="3 3" opacity="0.85" />
        )}
        <circle r={radius} fill={`${color}22`} stroke={`${color}80`} strokeWidth="1.5" />
        <circle r={Math.max(5, radius - 6)} fill="#061f28" stroke={color} strokeWidth="2" />
        {labelBelow ? (
          <>
            <text y={radius + 14} fill={color} fontSize="10" fontWeight="700" textAnchor="middle">
              {label}
            </text>
            <text
              y={radius + 26}
              fill="#99b6c4"
              fontSize="9.5"
              fontWeight="600"
              textAnchor="middle"
              fontFamily="var(--font-mono)"
            >
              {value}
            </text>
          </>
        ) : (
          <text
            x={radius + 10}
            y={3.5}
            fill="#cbe7f0"
            fontSize="10"
            fontWeight="700"
            textAnchor="start"
          >
            {label} · <tspan fill={color} fontFamily="var(--font-mono)">{value}</tspan>
          </text>
        )}
      </g>
    )
  }

  // Recent invocations narrowed by the live search box (server-side fallback below)
  const recentSearch = searchQuery.trim().toLowerCase()
  const filteredRecentRuns = recentSearch
    ? recentRuns.filter((r) =>
        `${r.id} ${r.task_id || ''} ${r.agent_label || ''} ${r.model || ''} ${r.outcome}`
          .toLowerCase()
          .includes(recentSearch)
      )
    : recentRuns

  const pipelineSteps = [
    {
      key: 'detect',
      label: '1. Detection',
      status: liveAnomalies.length > 0 ? `${liveAnomalies.length} flagged` : hasData ? 'Clear' : 'Idle',
      color: liveAnomalies.length > 0 ? '#fbbf24' : '#2dd4bf',
      action: goToAnalytics,
      title: 'Open anomaly analytics',
    },
    {
      key: 'inspect',
      label: '2. AST Inspection',
      status: hasData ? `${toolCallsCount} checks` : 'Idle',
      color: '#38bdf8',
      action: goToAnalytics,
      title: 'Inspect tool breakdown',
    },
    {
      key: 'confirm',
      label: '3. Denial Recorded',
      status: deniedCount > 0 ? `${deniedCount} runs blocked` : 'None',
      color: deniedCount > 0 ? '#f87171' : '#2dd4bf',
      action: () => goToRuns({ outcome: 'blocked' }),
      title: 'View blocked runs',
    },
    {
      key: 'resolve',
      label: '4. Safe Resolution',
      status: hasData ? `${allowedRuns} allowed` : 'Idle',
      color: '#34d399',
      action: () => goToRuns({ outcome: 'success' }),
      title: 'View successful runs',
    },
  ]

  // Sparkline series should only draw real observations
  const sparkSeries = (series: number[]) =>
    series.length >= 2 ? series : series.length === 1 ? [series[0], series[0]] : []

  return (
    <div className="workspace-viewport" data-testid="command-center-view">
      {/* Top SOC Navigation Ribbon (Inspired by reference image) */}
      <div className="soc-top-ribbon" data-testid="soc-top-ribbon">
        <div className="soc-ribbon-left">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '6px' }}>
            <div style={{ width: '16px', height: '16px', display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '2px' }}>
              <div style={{ background: '#2dd4bf', borderRadius: '1px' }} />
              <div style={{ background: '#14b8a6', borderRadius: '1px' }} />
              <div style={{ background: '#0d9488', borderRadius: '1px' }} />
              <div style={{ background: '#2dd4bf', borderRadius: '1px' }} />
            </div>
          </div>

          <button
            type="button"
            className="soc-filter-pill"
            onClick={() => goToRuns()}
            title={`Distinct agent/model labels across the ${recentRuns.length} most recent runs — open the run ledger`}
            data-testid="ribbon-fleet-pill"
          >
            <span>Fleet: <strong style={{ color: '#f0fdfa' }}>{distinctAgents} agent{distinctAgents === 1 ? '' : 's'}</strong></span>
            <ArrowUpRight size={12} />
          </button>

          <button
            type="button"
            className="soc-filter-pill"
            onClick={() => fetchLiveTelemetry(false)}
            title="Re-poll gateway health"
            data-testid="ribbon-gateway-pill"
          >
            <span>Gateway: <strong style={{ color: gatewayBadgeColor }}>{gatewayStatus}</strong></span>
            <RotateCw size={12} className={isLoadingLive ? 'animate-spin' : ''} />
          </button>

          <div style={{ position: 'relative' }}>
            <button
              type="button"
              className="soc-filter-pill"
              onClick={() => setIsRangeMenuOpen((v) => !v)}
              aria-haspopup="listbox"
              aria-expanded={isRangeMenuOpen}
              data-testid="time-range-pill"
            >
              <span>Time Range: <strong style={{ color: '#f0fdfa' }}>{rangeLabel}</strong></span>
              <ChevronDown size={12} />
            </button>

            {isRangeMenuOpen && (
              <div className="soc-dropdown" role="listbox" aria-label="Time range" data-testid="time-range-menu">
                {TIME_RANGES.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    role="option"
                    aria-selected={r.id === timeRange}
                    className={`soc-dropdown-item${r.id === timeRange ? ' active' : ''}`}
                    data-testid={`time-range-option-${r.id}`}
                    onClick={() => {
                      setTimeRange(r.id)
                      setIsRangeMenuOpen(false)
                    }}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            className="soc-filter-pill"
            onClick={goToPlayground}
            title="Open the policy playground"
          >
            <span>
              Defense: <strong style={{ color: activePolicy ? '#2dd4bf' : '#fbbf24' }}>
                AST Guard {policyLabel}
              </strong>
            </span>
            <ArrowUpRight size={12} />
          </button>
        </div>

        <div className="soc-ribbon-right">
          <div className="soc-search-wrap">
            <Search size={13} className="soc-search-icon" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
                setIsSearchOpen(true)
              }}
              onFocus={() => setIsSearchOpen(true)}
              onBlur={() => window.setTimeout(() => setIsSearchOpen(false), 140)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  const q = searchQuery.trim()
                  if (!q) return
                  if (searchResults.length === 1) {
                    onSelectRun(searchResults[0].id)
                  } else {
                    goToRuns({ search: q })
                  }
                  setIsSearchOpen(false)
                } else if (e.key === 'Escape') {
                  setIsSearchOpen(false)
                }
              }}
              placeholder="Search runs by ID, task or tool  ( / )"
              className="soc-search-input"
              aria-label="Search runs"
              data-testid="cc-search-input"
            />

            {isSearchOpen && recentSearch.length >= 2 && (
              <div className="soc-search-results" data-testid="cc-search-results">
                {searchResults.length === 0 ? (
                  <div className="soc-search-empty">
                    No indexed run matches “{searchQuery.trim()}”. Press Enter to search the full gateway.
                  </div>
                ) : (
                  searchResults.map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      className="soc-search-result"
                      data-testid={`cc-search-result-${r.id}`}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        onSelectRun(r.id)
                        setIsSearchOpen(false)
                      }}
                    >
                      <span className="soc-search-result-id">{r.id.slice(0, 10)}</span>
                      <span className="soc-search-result-task">{r.task_id || 'untitled task'}</span>
                      <span className={`soc-search-outcome outcome-${r.outcome}`}>{r.outcome}</span>
                    </button>
                  ))
                )}
                <button
                  type="button"
                  className="soc-search-all"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    goToRuns({ search: searchQuery.trim() })
                    setIsSearchOpen(false)
                  }}
                >
                  Open all runs matching “{searchQuery.trim()}”
                </button>
              </div>
            )}
          </div>

          <div style={{ position: 'relative' }}>
            <button
              type="button"
              className="soc-icon-btn"
              title="Pending notifications"
              aria-expanded={isNotifOpen}
              data-testid="cc-notifications-btn"
              onClick={() => setIsNotifOpen((v) => !v)}
            >
              <Bell size={14} />
              {(pendingApprovalsCount > 0 || liveAnomalies.length > 0) && (
                <span className="soc-notif-dot" />
              )}
            </button>

            {isNotifOpen && (
              <div className="soc-notif-panel" data-testid="cc-notifications-panel">
                <button
                  type="button"
                  className="soc-notif-item"
                  onClick={() => {
                    setIsNotifOpen(false)
                    onNavigateToApprovals?.()
                  }}
                >
                  <Clock size={13} style={{ color: '#fbbf24' }} />
                  <span>{pendingApprovalsCount} pending approval{pendingApprovalsCount === 1 ? '' : 's'}</span>
                  <ArrowUpRight size={12} />
                </button>
                <button
                  type="button"
                  className="soc-notif-item"
                  onClick={() => {
                    setIsNotifOpen(false)
                    goToAnalytics()
                  }}
                >
                  <AlertTriangle size={13} style={{ color: liveAnomalies.length > 0 ? '#f87171' : '#2dd4bf' }} />
                  <span>{liveAnomalies.length} anomalies in {rangeLabel.toLowerCase()}</span>
                  <ArrowUpRight size={12} />
                </button>
                <button
                  type="button"
                  className="soc-notif-item"
                  onClick={() => {
                    setIsNotifOpen(false)
                    goToRuns({ outcome: 'blocked' })
                  }}
                >
                  <ShieldAlert size={13} style={{ color: '#f87171' }} />
                  <span>{deniedCount} runs blocked</span>
                  <ArrowUpRight size={12} />
                </button>
              </div>
            )}
          </div>

          <div className="soc-user-avatar">
            <div className="soc-avatar-img">SOC</div>
            <span>SecOps Lead</span>
          </div>
        </div>
      </div>

      {headerNotice && (
        <div className={`header-notice header-notice-${headerNotice.tone}`} data-testid="cc-header-notice" role="status">
          {headerNotice.message}
        </div>
      )}

      {/* Main View Title & Header */}
      <div className="view-header" style={{ marginBottom: '1.25rem', flexWrap: 'wrap', gap: '10px' }}>
        <div className="view-title-wrap">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <h2 className="view-title" style={{ whiteSpace: 'nowrap' }}>Incidents Management</h2>
              <span
                style={{
                  fontSize: '0.72rem',
                  fontFamily: 'var(--font-mono)',
                  color: activePolicy ? '#34d399' : '#fbbf24',
                  background: activePolicy ? 'rgba(16, 185, 129, 0.1)' : 'rgba(251, 191, 36, 0.1)',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  border: activePolicy ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid rgba(251, 191, 36, 0.25)',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                }}
                data-testid="active-policy-badge"
              >
                {activePolicy ? `v${activePolicy.version_number} Policy Active` : 'No Active Policy'}
              </span>
              <span
                style={{
                  fontSize: '0.72rem',
                  color: '#628292',
                  fontFamily: 'var(--font-mono)',
                  whiteSpace: 'nowrap',
                }}
              >
                {ruleCount} rules
              </span>
            </div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              Monitor, investigate, prioritize, and enforce deterministic runtime policies.
            </p>
          </div>
        </div>

        <div className="header-badges-wrap">
          <div
            className="badge-status-online"
            data-testid="gateway-health-badge"
            title={gatewayHealth ? `Gateway status: ${gatewayStatus}` : 'Gateway unreachable'}
          >
            <span
              className="status-dot-green"
              style={{ background: gatewayBadgeColor, boxShadow: `0 0 8px ${gatewayBadgeColor}` }}
            ></span>
            {gatewayStatus}
          </div>

          <span className="view-meta-subtitle" style={{ display: 'none' }}>
            HOST-LOCAL-GATEWAY · ACTIVE
          </span>

          <div
            className="data-source-chip"
            data-testid="data-source-chip"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              borderRadius: '9999px',
              fontSize: '0.72rem',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              backgroundColor: isDemoPopulated ? 'rgba(56, 189, 248, 0.12)' : 'rgba(255, 255, 255, 0.05)',
              border: isDemoPopulated ? '1px solid rgba(56, 189, 248, 0.35)' : '1px solid #30363d',
              color: isDemoPopulated ? '#38bdf8' : '#8b949e',
            }}
          >
            <Database size={12} />
            <span>{isDemoPopulated ? 'DEMO DATA (LIVE GATEWAY)' : 'LIVE GATEWAY TELEMETRY'}</span>
          </div>

          <button
            type="button"
            className="btn-pill-glow"
            onClick={() => fetchLiveTelemetry(false)}
            title="Fetch latest gateway data"
          >
            <RotateCw size={13} className={isLoadingLive ? 'animate-spin' : ''} />
            <span>Refresh Data</span>
          </button>

          <button
            type="button"
            className="btn-pill-icon"
            title="Export incident telemetry as JSON"
            aria-label="Export incident telemetry"
            data-testid="cc-export-btn"
            onClick={handleExport}
          >
            <Download size={14} />
          </button>
          <button
            type="button"
            className="btn-pill-icon"
            title="Copy the current incident summary"
            aria-label="Copy incident summary"
            data-testid="cc-share-btn"
            onClick={handleCopySummary}
          >
            <Share2 size={14} />
          </button>
        </div>
      </div>

      {/* SecOps Hero Grid: Incident Health Score Gauge + Agent Toolchain Topology */}
      <div className="secops-hero-grid">
        {/* Left Hero Card: Incident Health Score Gauge */}
        <div className="health-score-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
              <Activity size={15} style={{ color: '#2dd4bf' }} />
              <span style={{ fontWeight: 700, fontSize: '0.92rem', color: '#f0fdfa' }}>
                Incident Health Score
              </span>
            </div>
            <span style={{ fontSize: '0.68rem', color: '#2dd4bf', background: 'rgba(45, 212, 191, 0.12)', padding: '2px 7px', borderRadius: '4px', border: '1px solid rgba(45, 212, 191, 0.25)', fontFamily: 'var(--font-mono)' }}>
              ● LIVE
            </span>
          </div>

          <div className="health-gauge-center">
            <button
              type="button"
              className="health-gauge-btn"
              onClick={() => setShowScoreBreakdown((v) => !v)}
              aria-expanded={showScoreBreakdown}
              title="Show how the score is composed"
              data-testid="health-gauge"
            >
              <svg width="180" height="106" viewBox="0 0 180 106">
                <defs>
                  <linearGradient id="secopsGaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#ef4444" />
                    <stop offset="35%" stopColor="#f59e0b" />
                    <stop offset="70%" stopColor="#14b8a6" />
                    <stop offset="100%" stopColor="#2dd4bf" />
                  </linearGradient>
                  <filter id="gaugeTealGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>

                {/* Gauge Background Track */}
                <path
                  d="M 24 90 A 66 66 0 0 1 156 90"
                  fill="none"
                  stroke="rgba(255, 255, 255, 0.08)"
                  strokeWidth="11"
                  strokeLinecap="round"
                />

                {/* Dynamic Filled Arc */}
                <path
                  d="M 24 90 A 66 66 0 0 1 156 90"
                  fill="none"
                  stroke="url(#secopsGaugeGrad)"
                  strokeWidth="11"
                  strokeLinecap="round"
                  strokeDasharray={arcCircumference}
                  strokeDashoffset={arcOffset}
                  filter="url(#gaugeTealGlow)"
                  style={{ transition: 'stroke-dashoffset 0.8s cubic-bezier(0.16, 1, 0.3, 1)' }}
                />

                {/* Center Numbers — '—' when the gateway has no rows in the window */}
                <text x="90" y="68" textAnchor="middle" fill="#f0fdfa" fontSize="28" fontWeight="800" fontFamily="var(--font-sans)">
                  {healthScore === null ? '—' : healthScore}
                  <tspan fontSize="13" fill="#628292" fontWeight="500">/100</tspan>
                </text>
                <text x="90" y="86" textAnchor="middle" fill={healthColor} fontSize="11" fontWeight="700" letterSpacing="0.04em">
                  {healthLabel}
                </text>
              </svg>
            </button>
          </div>

          <div className="health-metrics-list">
            <button
              type="button"
              className="health-metric-row health-metric-row-btn"
              onClick={goToAnalytics}
              title="Open tool-call analytics"
              data-testid="health-row-tool-calls"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Shield size={12} style={{ color: '#2dd4bf' }} />
                <span>Tool calls evaluated</span>
              </div>
              <span className="val">{hasData ? toolCallsCount : '—'}</span>
            </button>

            <button
              type="button"
              className="health-metric-row health-metric-row-btn"
              onClick={() => goToRuns({ outcome: 'blocked' })}
              title="Open blocked runs"
              data-testid="health-row-denied"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <AlertTriangle size={12} style={{ color: '#ef4444' }} />
                <span>Denied runs</span>
              </div>
              <span className="val" style={{ color: deniedCount > 0 ? '#f87171' : '#f0fdfa' }}>
                {hasData ? deniedCount : '—'}
              </span>
            </button>

            <button
              type="button"
              className="health-metric-row health-metric-row-btn"
              onClick={() => onNavigateToApprovals?.()}
              title="Open the human-in-the-loop approval queue"
              data-testid="health-row-pending"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Clock size={12} style={{ color: '#f59e0b' }} />
                <span>Approval queue</span>
              </div>
              <span className="val" style={{ color: pendingApprovalsCount > 0 ? '#fbbf24' : '#f0fdfa' }}>
                {pendingApprovalsCount}
              </span>
            </button>

            <button
              type="button"
              className="health-metric-row health-metric-row-btn"
              onClick={() => goToAnalytics()}
              title={`p50 latency · average ${avgLatency}ms over ${totalRuns} runs`}
              data-testid="health-row-latency"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ShieldCheck size={12} style={{ color: '#10b981' }} />
                <span>Check latency (p50)</span>
              </div>
              <span className="val" style={{ fontFamily: 'var(--font-mono)' }}>
                {hasData ? `${p50Display}ms` : '—'}
              </span>
            </button>
          </div>

          {showScoreBreakdown && (
            <div className="health-score-breakdown" data-testid="health-score-breakdown">
              <div className="health-breakdown-title">
                Score composition {hasData ? `· ${healthScore}/100` : '· no telemetry in window'}
              </div>
              {scoreParts.map((part) => (
                <div className="health-breakdown-row" key={part.label} title={part.detail}>
                  <span className="health-breakdown-label">
                    {part.label}
                    <span className="health-breakdown-detail">{part.detail}</span>
                  </span>
                  <span className="health-breakdown-points">{part.points}/{part.max}</span>
                </div>
              ))}
              <div className="health-breakdown-note">
                Deterministic weights — no model is involved in this score.
              </div>
            </div>
          )}

          <div className="health-status-footer">
            <span>Status</span>
            <span style={{ color: healthColor, fontWeight: 600, display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span
                className="status-dot-green"
                style={{ background: healthColor, boxShadow: `0 0 8px ${healthColor}` }}
              ></span>
              {healthLabel}
            </span>
          </div>
        </div>

        {/* Center/Right Hero Card: Network & Agent Toolchain Topology */}
        <div className="topology-hero-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Network size={16} style={{ color: '#2dd4bf' }} />
                <span style={{ fontWeight: 700, fontSize: '0.94rem', color: '#f0fdfa' }}>
                  Runtime Request Topology
                </span>
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                Live request flow: host agents → gateway → AST guard → execution sinks · {rangeLabel.toLowerCase()}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: '0.74rem', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px', color: '#f87171' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ef4444', boxShadow: '0 0 6px #ef4444' }}></span>
                <span>{deniedToolCalls} blocked spans</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px', color: '#2dd4bf' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2dd4bf', boxShadow: '0 0 6px #2dd4bf' }}></span>
                <span>{allowedToolCalls} allowed tool calls</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px', color: '#fbbf24' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#fbbf24', boxShadow: '0 0 6px #fbbf24' }}></span>
                <span>{pendingApprovalsCount} in HITL queue</span>
              </div>
            </div>
          </div>

          {/* SVG Topology Flow Visualizer */}
          <div className="topology-svg-wrap">
            <svg width="100%" height="100%" viewBox="0 0 740 160" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Live runtime request topology">
              <defs>
                <filter id="topoTealGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <filter id="topoRedGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Ambient Grid Lines in Topology */}
              <line x1="0" y1="74" x2="740" y2="74" stroke="rgba(45, 212, 191, 0.06)" strokeDasharray="4 4" />
              <line x1="0" y1="122" x2="740" y2="122" stroke="rgba(239, 68, 68, 0.06)" strokeDasharray="4 4" />

              {/* Agent -> Gateway -> Guard chain */}
              <path d="M 68 74 C 110 74, 140 74, 180 74" fill="none" stroke="#14b8a6" strokeWidth="2" filter="url(#topoTealGlow)" />
              <path d="M 212 74 C 255 74, 285 74, 320 74" fill="none" stroke="#14b8a6" strokeWidth="2" filter="url(#topoTealGlow)" />

              {/* Guard -> Allowed */}
              <path
                d="M 360 68 C 430 44, 480 32, 534 30"
                fill="none"
                stroke={allowedToolCalls > 0 ? '#10b981' : '#334155'}
                strokeWidth="2.2"
                filter="url(#topoTealGlow)"
              />
              {/* Guard -> HITL queue */}
              <path
                d="M 360 74 C 430 74, 480 76, 534 76"
                fill="none"
                stroke={pendingApprovalsCount > 0 ? '#f59e0b' : '#334155'}
                strokeWidth="2"
                strokeDasharray={pendingApprovalsCount > 0 ? undefined : '5 4'}
              />
              {/* Guard -> Blocked */}
              <path
                d="M 360 80 C 430 108, 480 120, 534 122"
                fill="none"
                stroke={deniedToolCalls > 0 ? '#ef4444' : '#334155'}
                strokeWidth="2.2"
                strokeDasharray={deniedToolCalls > 0 ? '6 4' : '5 4'}
                filter={deniedToolCalls > 0 ? 'url(#topoRedGlow)' : undefined}
              />

              {/* Edge counts — the numbers actually flowing */}
              {allowedToolCalls > 0 && (
                <text x="440" y="40" fill="#34d399" fontSize="10" fontWeight="700" textAnchor="middle" fontFamily="var(--font-mono)">
                  {allowedToolCalls}
                </text>
              )}
              {pendingApprovalsCount > 0 && (
                <text x="440" y="68" fill="#fbbf24" fontSize="10" fontWeight="700" textAnchor="middle" fontFamily="var(--font-mono)">
                  {pendingApprovalsCount}
                </text>
              )}
              {deniedToolCalls > 0 && (
                <text x="440" y="116" fill="#f87171" fontSize="10" fontWeight="700" textAnchor="middle" fontFamily="var(--font-mono)">
                  {deniedToolCalls}
                </text>
              )}

              {topoNode('agents', 52, 74, 16, 'Host Agents', `${totalRuns} runs`, '#2dd4bf')}
              {topoNode('gateway', 196, 74, 16, 'Gateway', `${toolCallsCount} calls`, '#38bdf8')}
              {topoNode('guard', 340, 74, 20, 'AST Guard', `${policyLabel} · ${ruleCount} rules`, '#2dd4bf')}

              {topoNode('allowed', 548, 30, 14, 'Allowed', `${allowedToolCalls}`, '#10b981', false)}
              {topoNode('pending', 548, 76, 14, 'HITL', `${pendingApprovalsCount}`, '#fbbf24', false)}
              {topoNode('blocked', 548, 122, 14, 'Blocked', `${deniedToolCalls}`, '#ef4444', false)}
            </svg>
          </div>

          <div className="topo-detail-bar" data-testid="topo-detail-bar">
            {selectedNode ? (
              <>
                <div className="topo-detail-text">
                  <strong>{topoDetail[selectedNode].title}</strong>
                  <span>{topoDetail[selectedNode].detail}</span>
                </div>
                <button
                  type="button"
                  className="topo-detail-action"
                  onClick={topoDetail[selectedNode].action}
                  data-testid="topo-detail-action"
                >
                  {topoDetail[selectedNode].actionLabel}
                  <ArrowUpRight size={12} />
                </button>
              </>
            ) : (
              <span className="topo-detail-hint">
                Click any node to inspect its live counters and drill into the matching view.
              </span>
            )}
          </div>

          {/* The 4 Core SecOps Metrics directly embedded in Topology Hero */}
          <div className="topology-metrics-row">
            <button
              type="button"
              className="metric-card cc-metric-card cc-metric-btn"
              style={{ padding: '0.75rem 1rem', margin: 0 }}
              onClick={goToAnalytics}
              title="Open tool-call analytics"
              data-testid="metric-card-tool-calls"
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Terminal size={14} style={{ color: '#2dd4bf' }} />
                  <span className="metric-label">Tool calls</span>
                </div>
                <span className="cc-metric-spark" title={`Observed poll samples: ${pollHistory.toolCalls.length}`}>
                  <Sparkline data={sparkSeries(pollHistory.toolCalls)} color="#2dd4bf" />
                </span>
              </div>
              <div className="metric-value-wrap">
                <span className="metric-value-large">{hasData ? toolCallsCount : '—'}</span>
              </div>
              <span className="cc-metric-subtitle">
                {hasData ? `${totalRuns} runs · ${tools.length} tools in window` : 'No telemetry in window'}
              </span>
            </button>

            <button
              type="button"
              className="metric-card cc-metric-card cc-metric-btn"
              style={{ padding: '0.75rem 1rem', margin: 0 }}
              onClick={() => goToRuns({ outcome: 'blocked' })}
              title="Open blocked runs"
              data-testid="metric-card-denied"
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ShieldAlert size={14} style={{ color: '#ef4444' }} />
                  <span className="metric-label">Denied</span>
                </div>
                <span className="cc-metric-spark" title={`Observed poll samples: ${pollHistory.denied.length}`}>
                  <Sparkline data={sparkSeries(pollHistory.denied)} color="#ef4444" />
                </span>
              </div>
              <div className="metric-value-wrap">
                <span className="metric-value-large metric-value-coral">
                  {hasData ? deniedCount : '—'}
                </span>
                <span className="metric-unit">{deniedPct}%</span>
              </div>
              <span className="cc-metric-subtitle">
                {hasData ? `${deniedToolCalls} denied tool spans · server-side enforcement` : 'No telemetry in window'}
              </span>
            </button>

            <button
              type="button"
              className="metric-card cc-metric-card cc-metric-btn"
              style={{ padding: '0.75rem 1rem', margin: 0 }}
              onClick={() => onNavigateToApprovals?.()}
              title="Open the approval queue"
              data-testid="metric-card-pending"
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Clock size={14} style={{ color: '#f59e0b' }} />
                  <span className="metric-label">Pending approvals</span>
                </div>
                <span className="cc-metric-spark" title={`Observed poll samples: ${pollHistory.approvals.length}`}>
                  <Sparkline data={sparkSeries(pollHistory.approvals)} color="#f59e0b" />
                </span>
              </div>
              <div className="metric-value-wrap">
                <span className="metric-value-large metric-value-amber">
                  {pendingApprovalsCount}
                </span>
              </div>
              <span className="cc-metric-subtitle">
                {pendingApprovalsCount === 0 ? 'Approval queue is clear' : 'Awaiting human decision'}
              </span>
            </button>

            <button
              type="button"
              className="metric-card cc-metric-card cc-metric-btn"
              style={{ padding: '0.75rem 1rem', margin: 0 }}
              onClick={() => goToAnalytics()}
              title={`p50 ${p50Display}ms · p95 ${p95Latency}ms · avg ${avgLatency}ms`}
              data-testid="metric-card-latency"
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Zap size={14} style={{ color: '#10b981' }} />
                  <span className="metric-label">Check latency p50</span>
                </div>
                <span className="cc-metric-spark" title={`Observed poll samples: ${pollHistory.p50.length}`}>
                  <Sparkline data={sparkSeries(pollHistory.p50)} color="#10b981" />
                </span>
              </div>
              <div className="metric-value-wrap">
                <span className="metric-value-large">{hasData ? p50Display : '—'}</span>
                <span className="metric-unit">ms</span>
              </div>
              <span className="cc-metric-subtitle">
                {hasData ? `p95 ${p95Latency}ms · avg ${avgLatency}ms · n=${totalRuns}` : 'No telemetry in window'}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Live Demonstration Controller Banner */}
      <div
        className="panel-card"
        data-testid="live-demo-controls-banner"
        style={{
          marginBottom: '1.25rem',
          background: '#030a0e',
          border: '1px solid rgba(45, 212, 191, 0.14)',
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
          position: 'relative',
          overflow: 'hidden',
          borderRadius: '14px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ display: 'inline-block', width: '9px', height: '9px', borderRadius: '50%', backgroundColor: '#10b981', boxShadow: '0 0 10px #10b981' }}></span>
            <span style={{ fontWeight: 700, fontSize: '0.92rem', color: '#f8fafc', letterSpacing: '0.01em' }}>
              Live API Demonstration Controller
            </span>
            <span style={{ fontSize: '0.72rem', color: '#38bdf8', background: 'rgba(56, 189, 248, 0.12)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(56, 189, 248, 0.25)', fontFamily: 'var(--font-mono)' }}>
              Target: 127.0.0.1:8000
            </span>
          </div>
          <div style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
            Live Background Polling · Click buttons to execute real Gateway AST checks & spans
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
          <button
            type="button"
            disabled={isExecutingDemo}
            onClick={() => handleRunDemoScenario('sql_analyst')}
            style={{
              padding: '9px 12px',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '8px',
              background: '#040d12',
              border: '1px solid rgba(34, 197, 94, 0.35)',
              color: '#4ade80',
              cursor: isExecutingDemo ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '2px',
              transition: 'all 0.15s ease',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span>▶ 1. Benign Analyst</span>
            </div>
            <span style={{ fontSize: '0.68rem', color: '#86efac', opacity: 0.85, fontWeight: 400 }}>
              Allow + PII Redaction
            </span>
          </button>

          <button
            type="button"
            disabled={isExecutingDemo}
            onClick={() => handleRunDemoScenario('sql_attack')}
            style={{
              padding: '9px 12px',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '8px',
              background: '#040d12',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              color: '#f87171',
              cursor: isExecutingDemo ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '2px',
              transition: 'all 0.15s ease',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span>🛑 2. SQL Injection</span>
            </div>
            <span style={{ fontSize: '0.68rem', color: '#fca5a5', opacity: 0.85, fontWeight: 400 }}>
              AST DROP TABLE Blocked
            </span>
          </button>

          <button
            type="button"
            disabled={isExecutingDemo}
            onClick={() => handleRunDemoScenario('hitl_approval')}
            style={{
              padding: '9px 12px',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '8px',
              background: '#040d12',
              border: '1px solid rgba(245, 158, 11, 0.35)',
              color: '#fbbf24',
              cursor: isExecutingDemo ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '2px',
              transition: 'all 0.15s ease',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span>⏱ 3. Request Approval</span>
            </div>
            <span style={{ fontSize: '0.68rem', color: '#fde047', opacity: 0.85, fontWeight: 400 }}>
              $85k Wire Transfer HITL
            </span>
          </button>

          <button
            type="button"
            disabled={isExecutingDemo}
            onClick={() => handleRunDemoScenario('path_traversal')}
            style={{
              padding: '9px 12px',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '8px',
              background: '#040d12',
              border: '1px solid rgba(168, 85, 247, 0.35)',
              color: '#c084fc',
              cursor: isExecutingDemo ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '2px',
              transition: 'all 0.15s ease',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span>🚫 4. Path Traversal</span>
            </div>
            <span style={{ fontSize: '0.68rem', color: '#d8b4fe', opacity: 0.85, fontWeight: 400 }}>
              Sandbox Escape Blocked
            </span>
          </button>

          <button
            type="button"
            disabled={isExecutingDemo}
            onClick={() => handleRunDemoScenario('tool_loop')}
            style={{
              padding: '9px 12px',
              fontSize: '0.78rem',
              fontWeight: 600,
              borderRadius: '8px',
              background: '#040d12',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              color: '#38bdf8',
              cursor: isExecutingDemo ? 'wait' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '2px',
              transition: 'all 0.15s ease',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span>🔁 5. Tool Loop Anomaly</span>
            </div>
            <span style={{ fontSize: '0.68rem', color: '#bae6fd', opacity: 0.85, fontWeight: 400 }}>
              5x Rapid Recursive Calls
            </span>
          </button>
        </div>

        {demoToast && (
          <div
            style={{
              marginTop: '12px',
              padding: '9px 14px',
              borderRadius: '8px',
              fontSize: '0.82rem',
              fontWeight: 500,
              backgroundColor:
                demoToast.type === 'blocked'
                  ? 'rgba(239, 68, 68, 0.18)'
                  : demoToast.type === 'pending'
                  ? 'rgba(245, 158, 11, 0.18)'
                  : demoToast.type === 'info'
                  ? 'rgba(56, 189, 248, 0.18)'
                  : 'rgba(34, 197, 94, 0.18)',
              color:
                demoToast.type === 'blocked'
                  ? '#fca5a5'
                  : demoToast.type === 'pending'
                  ? '#fde047'
                  : demoToast.type === 'info'
                  ? '#7dd3fc'
                  : '#86efac',
              border: '1px solid currentColor',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>{demoToast.message}</span>
            <button
              type="button"
              onClick={() => setDemoToast(null)}
              style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '0.85rem' }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* Middle Grid: AI Investigation & Decision stream + Approval needed */}
      <div className="middle-grid">
        {/* AI Investigation & Decision Stream Visualizer */}
        <div className="panel-card">
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Activity size={16} style={{ color: '#38bdf8' }} />
              <h3 className="panel-title">Decision stream</h3>
            </div>
            <div className="decision-stream-legend">
              <span className="legend-item">
                <span className="legend-square-allow"></span>
                allow
              </span>
              <span className="legend-item">
                <span className="legend-square-deny"></span>
                deny
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%' }}>
            {/* Policy verdict summary (deterministic — no model inference) */}
            <div className="ai-investigation-box">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span className="ai-investigation-badge">DETERMINISTIC POLICY SUMMARY</span>
                <span style={{ fontSize: '0.68rem', color: '#99b6c4', fontFamily: 'var(--font-mono)' }}>
                  {activePolicy ? `policy ${policyLabel}` : 'policy unavailable'}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: '0.76rem', color: '#ccfbf1' }}>
                {topDenyingTool
                  ? `${topDenyingTool.tool_name} was denied ${topDenyingTool.policy_block_count} time${topDenyingTool.policy_block_count === 1 ? '' : 's'} by rule "${topDenyingTool.top_block_rule || 'unknown'}" — the most frequent rule in this window. ${deniedCount} of ${totalRuns} runs blocked, ${liveAnomalies.length} anomalies flagged.`
                  : hasData
                  ? `No tool denials recorded in ${rangeLabel.toLowerCase()}. ${toolCallsCount} tool calls inspected across ${totalRuns} runs; ${liveAnomalies.length} anomalies flagged.`
                  : `No telemetry in ${rangeLabel.toLowerCase()}. Run a Live API scenario above to populate real gateway spans.`}
              </p>
            </div>

            {liveSummary && liveSummary.total_runs > 0 ? (
              <div>
                {/* Threat Attribution breakdown — derived from per-tool denial counts */}
                <div style={{ marginBottom: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#99b6c4' }}>
                    <span>Denial attribution by tool</span>
                    <span style={{ fontWeight: 700, color: '#f0fdfa' }}>{toolCallsCount} total calls</span>
                  </div>
                  <div className="threat-attribution-bar">
                    {threatSegments.map((seg) => (
                      <div
                        key={seg.key}
                        style={{
                          width: `${(seg.count / Math.max(1, toolCallsCount)) * 100}%`,
                          background: seg.color,
                        }}
                        title={`${seg.label}: ${seg.count} of ${toolCallsCount} tool calls (${((seg.count / Math.max(1, toolCallsCount)) * 100).toFixed(1)}%)`}
                      />
                    ))}
                  </div>
                  <div className="threat-legend">
                    {threatSegments.map((seg) => (
                      <span key={seg.key} className="threat-legend-item">
                        <span className="threat-legend-swatch" style={{ background: seg.color }} />
                        {seg.label}: {seg.count} ({((seg.count / Math.max(1, toolCallsCount)) * 100).toFixed(1)}%)
                      </span>
                    ))}
                  </div>
                </div>

                {/* Proportional Ratio Bar */}
                <div className="cc-decision-ratio-container" style={{ marginTop: '0.5rem' }}>
                  <div className="cc-ratio-bar-track">
                    <div
                      className="cc-ratio-fill-allow"
                      style={{ width: `${Math.max(4, parseFloat(allowPct))}%` }}
                      title={`Allowed: ${allowPct}%`}
                    />
                    <div
                      className="cc-ratio-fill-deny"
                      style={{ width: `${Math.max(deniedCount > 0 ? 4 : 0, parseFloat(deniedPct))}%` }}
                      title={`Denied: ${deniedPct}%`}
                    />
                  </div>
                  <div className="cc-ratio-stats-row">
                    <span style={{ color: '#10b981', fontWeight: 600 }}>
                      ● {allowedRuns} Allow ({allowPct}%)
                    </span>
                    <span style={{ color: '#ef4444', fontWeight: 600 }}>
                      ● {deniedCount} Deny ({deniedPct}%)
                    </span>
                  </div>
                </div>

                {/* Recent Invocations Mini Stream */}
                {(filteredRecentRuns.length > 0 || recentSearch.length > 0) && (
                  <div className="cc-recent-invocations-list" style={{ marginTop: '0.85rem' }}>
                    <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: '#64748b', fontWeight: 700, letterSpacing: '0.05em' }}>
                      Recent Invocations{recentSearch ? ` · matching “${searchQuery.trim()}”` : ''}
                    </div>
                    {filteredRecentRuns.length === 0 ? (
                      <div style={{ fontSize: '0.74rem', color: '#64748b', padding: '6px 0' }}>
                        No run in the last {recentRuns.length} matches this query. Press Enter in the search box to query the full gateway.
                      </div>
                    ) : (
                      filteredRecentRuns.slice(0, 3).map((r) => {
                      const isBlocked = r.outcome === 'blocked' || r.failure_category === 'policy_block'
                      return (
                        <div
                          key={r.id}
                          className="cc-invocation-item"
                          onClick={() => onSelectRun(r.id)}
                          title="Click to view waterfall trace"
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {isBlocked ? (
                              <ShieldAlert size={13} style={{ color: '#ef4444' }} />
                            ) : (
                              <Check size={13} style={{ color: '#10b981' }} />
                            )}
                            <span style={{ fontWeight: 600, color: '#e2e8f0' }}>
                              {r.task_id || r.id}
                            </span>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span
                              style={{
                                fontSize: '0.68rem',
                                padding: '1px 5px',
                                borderRadius: '3px',
                                fontWeight: 700,
                                background: isBlocked ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                                color: isBlocked ? '#f87171' : '#34d399',
                                border: isBlocked ? '1px solid rgba(239, 68, 68, 0.3)' : '1px solid rgba(16, 185, 129, 0.3)',
                              }}
                            >
                              {isBlocked ? 'DENIED' : 'ALLOWED'}
                            </span>
                            <span style={{ fontSize: '0.7rem', color: '#64748b', fontFamily: 'var(--font-mono)' }}>
                              {r.latency_ms ? `${Math.round(r.latency_ms)}ms` : '0ms'}
                            </span>
                            <ArrowUpRight size={12} style={{ color: '#94a3b8' }} />
                          </div>
                        </div>
                      )
                      })
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ height: '140px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                <span>No decision history available.</span>
              </div>
            )}
          </div>
        </div>

        {/* Approval Needed Card */}
        <div className="panel-card panel-approval-needed">
          <div className="approval-card-top-row">
            <span className="approval-card-title">Approval needed</span>
            {approval && remainingSec > 0 && (
              <span className="approval-timer-badge">
                <Clock size={12} className="inline mr-1" />
                auto-reject in {formatTimer(remainingSec)}
              </span>
            )}
          </div>

          {approval ? (
            <div>
              <div className="approval-call-header">
                <div>
                  <span className="approval-tool-name">{approval.tool_name}</span>
                  <span className="approval-session-ref">
                    {approval.session_id ? `session: ${approval.session_id}` : `call: ${approval.call_hash?.slice(0, 10)}`}
                  </span>
                </div>
              </div>

              <div className="approval-params-box">
                <div className="approval-params-label">Call Arguments:</div>
                <pre className="approval-params-code">
                  {JSON.stringify(approval.tool_args || approval.arguments, null, 2)}
                </pre>
              </div>

              {approvalFeedback && (
                <div className="approval-feedback-banner">
                  {approvalFeedback}
                </div>
              )}

              <div className="approval-action-row">
                <button
                  type="button"
                  className="btn-reject-hotkey"
                  onClick={() => handleDecision('rejected')}
                  data-testid="btn-cc-reject"
                >
                  <X size={14} className="inline mr-1" />
                  Reject <kbd className="hotkey-kbd">R</kbd>
                </button>

                <button
                  type="button"
                  className="btn-approve-hotkey"
                  onClick={() => handleDecision('approved')}
                  data-testid="btn-cc-approve"
                >
                  <Check size={14} className="inline mr-1" />
                  Approve <kbd className="hotkey-kbd">A</kbd>
                </button>
              </div>
            </div>
          ) : (
            <div className="approval-empty-state">
              <ShieldCheck size={28} className="text-mint" style={{ marginBottom: '8px' }} />
              <div>All authorizations cleared.</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                No pending Human-in-the-Loop review requests in queue.
              </div>

              {/* Live pipeline stepper — counts come from the gateway */}
              <div style={{ marginTop: '1.25rem', width: '100%', textAlign: 'left', borderTop: '1px solid rgba(45, 212, 191, 0.12)', paddingTop: '0.85rem' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#f0fdfa', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Incident Execution Pipeline
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {pipelineSteps.map((step) => (
                    <button
                      key={step.key}
                      type="button"
                      className="pipeline-step"
                      onClick={step.action}
                      title={step.title}
                      data-testid={`pipeline-step-${step.key}`}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: step.color }} />
                        <span style={{ color: '#cbd5e1' }}>{step.label}</span>
                      </div>
                      <span
                        style={{
                          fontSize: '0.68rem',
                          color: step.color,
                          background: `${step.color}1f`,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {step.status}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Grid: Top denying rules + Anomaly list */}
      <div className="bottom-grid">
        {/* Top Denying Rules Table */}
        <div className="panel-card">
          <div className="panel-header">
            <h3 className="panel-title">Top denying rules · {rangeLabel.toLowerCase()}</h3>
            <span style={{ fontSize: '0.7rem', color: '#628292', fontFamily: 'var(--font-mono)' }}>
              {deniedTools.length} tool{deniedTools.length === 1 ? '' : 's'} denied
            </span>
          </div>

          <table className="rules-table">
            <thead>
              <tr>
                <th>Rule ID</th>
                <th>Tool</th>
                <th style={{ textAlign: 'right' }}>Hits</th>
                <th style={{ textAlign: 'right' }}>% of den.</th>
              </tr>
            </thead>
            <tbody>
              {deniedTools.length > 0 ? (
                deniedTools.map((t) => {
                  const ruleName = t.top_block_rule || 'unattributed'
                  const hits = t.policy_block_count || 0
                  const pct = Math.min(100, Math.round((hits / Math.max(1, deniedToolCalls)) * 100))
                  return (
                    <tr
                      key={t.tool_name}
                      className="clickable-row"
                      onClick={() => goToRuns({ search: t.tool_name })}
                      title={`Open runs that called ${t.tool_name}`}
                      data-testid={`rules-row-${t.tool_name}`}
                    >
                      <td>
                        <span className="rule-code-badge">{ruleName}</span>
                      </td>
                      <td>
                        <span className="tool-code-badge">{t.tool_name}</span>
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 600, color: '#f87171' }}>
                        {hits}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
                          <div style={{ width: '45px', height: '4px', backgroundColor: '#334155', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${pct}%`, height: '100%', backgroundColor: '#ef4444' }} />
                          </div>
                          <span style={{ fontSize: '0.72rem', color: '#94a3b8', minWidth: '28px' }}>
                            {pct}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '1rem' }}>
                    {liveSummary && liveSummary.blocked_runs > 0
                      ? `${liveSummary.blocked_runs} blocked runs recorded, but no per-tool denial attribution is available for this window.`
                      : `No policy denials recorded in ${rangeLabel.toLowerCase()}.`}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Anomaly / Alert Banner Stack */}
        <div className="panel-card">
          <div className="panel-header">
            <h3 className="panel-title">Recent anomalies & alerts</h3>
          </div>

          <div className="anomaly-stack">
            {liveAnomalies.slice(0, 3).map((item: any, idx) => {
              const runId = item.run_id || item.runId
              return (
                <div
                  key={idx}
                  className={`anomaly-card${runId ? ' anomaly-card-clickable' : ''}`}
                  role={runId ? 'button' : undefined}
                  tabIndex={runId ? 0 : undefined}
                  onClick={() => (runId ? onSelectRun(runId) : goToAnalytics())}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      runId ? onSelectRun(runId) : goToAnalytics()
                    }
                  }}
                  title={runId ? 'Open the run trace for this anomaly' : 'Open anomaly analytics'}
                  data-testid={`anomaly-card-${idx}`}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <AlertTriangle
                      size={15}
                      className={
                        item.severity === 'high' || item.severity === 'critical' || item.level === 'high'
                          ? 'text-coral'
                          : 'text-amber'
                      }
                    />
                    <span className="anomaly-title">{item.type || item.title}</span>
                    {item.severity && (
                      <span
                        style={{
                          fontSize: '0.65rem',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          padding: '1px 5px',
                          borderRadius: '3px',
                          background: item.severity === 'critical' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: item.severity === 'critical' ? '#f87171' : '#fbbf24',
                          border: '1px solid currentColor',
                        }}
                      >
                        {item.severity}
                      </span>
                    )}
                    <ArrowUpRight size={12} style={{ marginLeft: 'auto', color: '#64748b' }} />
                  </div>
                  <div className="anomaly-desc">{item.message || item.description || item.reason}</div>
                </div>
              )
            })}

            {liveAnomalies.length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '1.5rem', fontSize: '0.85rem' }}>
                No active anomalies in {rangeLabel.toLowerCase()}.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
