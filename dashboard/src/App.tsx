import React, { useState, useEffect, useCallback } from 'react'
import { Square, Search, Database } from 'lucide-react'
import { Run, RunDetail, RunFilters, SessionItem } from './types'
import { fetchRuns, fetchRunDetail, fetchSessions, fetchApprovals, hasAdminToken } from './services/api'

import { Sidebar, NavTabId } from './components/Sidebar'
import { CommandCenter } from './components/CommandCenter'
import { RunTraceAuditView } from './components/RunTraceAuditView'
import { StudyOverview } from './components/StudyOverview'
import { PolicyPlayground } from './components/PolicyPlayground'
import { HeldOutExplorer } from './components/HeldOutExplorer'
import { ClaimsViewer } from './components/ClaimsViewer'
import { RunList } from './components/RunList'
import { ApprovalsQueue } from './components/ApprovalsQueue'
import { AnalyticsDashboard } from './components/AnalyticsDashboard'
import { ReplayView } from './components/ReplayView'
import { LiveAgentLab } from './components/LiveAgentLab'
import { CyberArcTopology } from './components/CyberArcTopology'
import { AdminTokenModal } from './components/AdminTokenModal'
import { CommandPalette } from './components/CommandPalette'

import './index.css'

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTabId>('command_center')

  const [runs, setRuns] = useState<Run[]>([])
  const [totalRuns, setTotalRuns] = useState<number>(0)
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState<number>(0)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [selectedRunDetail, setSelectedRunDetail] = useState<RunDetail | null>(null)
  const [playgroundInitialPayload, setPlaygroundInitialPayload] = useState<any>(null)

  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [isLoadingRuns, setIsLoadingRuns] = useState<boolean>(false)
  const [isLoadingSessions, setIsLoadingSessions] = useState<boolean>(false)
  const [isTokenModalOpen, setIsTokenModalOpen] = useState<boolean>(false)
  const [tokenConfigured, setTokenConfigured] = useState<boolean>(hasAdminToken())

  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState<boolean>(false)

  const [filters, setFilters] = useState<RunFilters>({
    outcome: '',
    model: '',
    session_id: '',
    search: '',
    start_date: '',
    end_date: '',
    limit: 25,
    offset: 0,
  })

  // Keyboard shortcut listener for Ctrl+K / Cmd+K
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        setIsCommandPaletteOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [])

  // Load runs from API
  const loadRuns = useCallback(async (isBackground = false) => {
    if (!isBackground) {
      setIsLoadingRuns(true)
    }
    try {
      const data = await fetchRuns(filters)
      setRuns(data.runs || [])
      setTotalRuns(data.total || 0)
    } catch (err) {
      console.warn('Backend runs fetch failed, defaulting to empty list:', err)
      if (!isBackground) {
        setRuns([])
        setTotalRuns(0)
      }
    } finally {
      if (!isBackground) {
        setIsLoadingRuns(false)
      }
    }
  }, [filters])

  // Load sessions from API
  const loadSessions = useCallback(async (isBackground = false) => {
    if (!isBackground) {
      setIsLoadingSessions(true)
    }
    try {
      const data = await fetchSessions()
      setSessions(data.sessions || [])
    } catch (err) {
      console.warn('Failed to load sessions:', err)
      if (!isBackground) {
        setSessions([])
      }
    } finally {
      if (!isBackground) {
        setIsLoadingSessions(false)
      }
    }
  }, [])

  // Auto-poll runs every 3 seconds in background: updates state quietly without blanking UI
  useEffect(() => {
    loadRuns(false)
    const interval = setInterval(() => {
      loadRuns(true)
    }, 3000)
    return () => clearInterval(interval)
  }, [loadRuns])

  // Poll pending approvals count for live sidebar badge
  const refreshApprovalsCount = useCallback(async () => {
    try {
      const pending = await fetchApprovals('pending')
      setPendingApprovalsCount(Array.isArray(pending) ? pending.length : 0)
    } catch {
      // Quiet background failure
    }
  }, [])

  useEffect(() => {
    refreshApprovalsCount()
    const interval = setInterval(refreshApprovalsCount, 3000)
    return () => clearInterval(interval)
  }, [refreshApprovalsCount])

  useEffect(() => {
    if (activeTab === 'runs') {
      loadSessions(false)
      const interval = setInterval(() => {
        loadSessions(true)
      }, 5000)
      return () => clearInterval(interval)
    }
  }, [activeTab, loadSessions])

  // Select a run to view waterfall timeline
  const handleSelectRun = async (runId: string) => {
    setSelectedRunId(runId)
    try {
      const detail = await fetchRunDetail(runId)
      setSelectedRunDetail(detail)
      setActiveTab('runs')
    } catch (err) {
      console.warn('Failed to load run detail:', err)
      setSelectedRunDetail(null)
      setActiveTab('runs')
    }
  }

  // Navigate to playground with pre-filled payload
  const handleNavigateToPlayground = (initialPayload: any) => {
    setPlaygroundInitialPayload(initialPayload)
    setSelectedRunDetail(null)
    setActiveTab('playground')
  }

  const handleFilterChange = (newFilters: Partial<RunFilters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }))
  }

  const getWindowTitle = () => {
    if (activeTab === 'command_center') return '1 · Operate: runs and approvals'
    if (activeTab === 'runs' && selectedRunDetail) return '2 · Operate: trace and policy audit'
    if (activeTab === 'study_overview') return '3 · Evaluate: study overview and replay lab'
    if (activeTab === 'playground') return 'Operate: live policy gateway playground'
    if (activeTab === 'live_lab') return 'Operate: live agent lab and real-world API calls'
    if (activeTab === 'cyber_arc') return 'Operate: CyberArc 3D WebGL security universe and tool topology'
    if (activeTab === 'held_out') return 'Evaluate: held-out active attacks benchmark'
    if (activeTab === 'claims') return 'Evaluate: claims and limit boundaries'
    return 'AgentShield SOC Operations Center'
  }

  return (
    <div className="window-frame">
      {/* Outer ambient canvas branding from sample image */}
      <div className="sample-outer-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: 800, fontSize: '1.05rem', color: '#f0fdfa', letterSpacing: '-0.02em' }}>
            Juice <span style={{ color: '#2dd4bf', fontWeight: 600 }}>Lab</span>
          </span>
          <span style={{ fontSize: '0.7rem', color: '#628a99', background: 'rgba(45, 212, 191, 0.08)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(45, 212, 191, 0.18)' }}>
            AgentShield
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '1.05rem', color: '#ccfbf1', letterSpacing: '0.04em' }}>
            Analytics <strong style={{ color: '#ffffff', fontWeight: 700 }}>Dashboard</strong>
          </span>
        </div>
      </div>

      {/* Top Window Titlebar */}
      <div className="window-titlebar">
        <div className="window-title-left">
          <span style={{ display: 'flex', gap: '6px', marginRight: '8px' }}>
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#ef4444', display: 'inline-block' }}></span>
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#f59e0b', display: 'inline-block' }}></span>
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }}></span>
          </span>
          <span className="font-semibold text-slate-200">{getWindowTitle()}</span>
        </div>

        <div className="window-title-right">
          {/* Quick Command Palette Button */}
          <button
            type="button"
            className="window-btn btn-cmd-k"
            onClick={() => setIsCommandPaletteOpen(true)}
            title="Open Command Palette (Ctrl+K)"
            data-testid="btn-open-palette"
          >
            <Search size={12} style={{ marginRight: '4px' }} />
            <span>Ctrl+K</span>
          </button>

          <span
            className="window-badge"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              backgroundColor: 'rgba(45, 212, 191, 0.1)',
              color: 'var(--teal)',
              fontSize: '0.72rem',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '4px',
              border: '1px solid rgba(45, 212, 191, 0.3)',
            }}
          >
            <Database size={11} />
            <span>GATEWAY DB</span>
          </span>

          <button
            type="button"
            className="window-btn"
            onClick={() => window.location.reload()}
            title="Reload window"
          >
            <Square size={11} />
          </button>
        </div>
      </div>

      {/* Main Body: Sidebar + Active Workspace Viewport */}
      <div className="app-layout">
        <Sidebar
          activeTab={activeTab}
          onSelectTab={(tab) => {
            if (tab !== 'runs') {
              setSelectedRunDetail(null)
            }
            setActiveTab(tab)
          }}
          pendingApprovalsCount={pendingApprovalsCount}
          runsCount={totalRuns}
          onOpenTokenModal={() => setIsTokenModalOpen(true)}
          tokenConfigured={tokenConfigured}
        />

        {/* Workspace Viewport based on active tab */}
        {activeTab === 'command_center' ? (
          <CommandCenter
            onSelectRun={handleSelectRun}
            onNavigateToApprovals={() => setActiveTab('approvals')}
            onNavigateToRuns={(filters) => {
              if (filters) handleFilterChange({ ...filters, offset: 0 })
              setSelectedRunDetail(null)
              setActiveTab('runs')
            }}
            onNavigateToAnalytics={() => setActiveTab('analytics')}
            onNavigateToPlayground={() => setActiveTab('playground')}
          />
        ) : activeTab === 'runs' ? (
          selectedRunDetail ? (
            <RunTraceAuditView
              run={selectedRunDetail}
              onBack={() => {
                setSelectedRunDetail(null)
                setSelectedRunId(null)
              }}
              onNavigateToPlayground={handleNavigateToPlayground}
            />
          ) : (
            <div className="workspace-viewport">
              <div className="view-header">
                <div className="view-title-wrap">
                  <h2 className="view-title">All Runs & Sessions</h2>
                  <span className="view-meta-subtitle">
                    {totalRuns} RUNS REGISTERED
                  </span>
                </div>
              </div>
              <RunList
                runs={runs}
                total={totalRuns}
                filters={filters}
                onFilterChange={handleFilterChange}
                onSelectRun={handleSelectRun}
                selectedRunId={selectedRunId}
                isLoading={isLoadingRuns}
              />
            </div>
          )
        ) : activeTab === 'study_overview' ? (
          <StudyOverview />
        ) : activeTab === 'held_out' ? (
          <HeldOutExplorer />
        ) : activeTab === 'playground' ? (
          <PolicyPlayground initialPayload={playgroundInitialPayload} />
        ) : activeTab === 'claims' ? (
          <ClaimsViewer />
        ) : activeTab === 'approvals' ? (
          <div className="workspace-viewport">
            <ApprovalsQueue
              onOpenTokenModal={() => setIsTokenModalOpen(true)}
              tokenConfigured={tokenConfigured}
            />
          </div>
        ) : activeTab === 'analytics' ? (
          <div className="workspace-viewport">
            <AnalyticsDashboard onSelectRun={handleSelectRun} />
          </div>
        ) : activeTab === 'live_lab' ? (
          <LiveAgentLab onNavigateToApprovals={() => setActiveTab('approvals')} />
        ) : activeTab === 'cyber_arc' ? (
          <CyberArcTopology
            onNavigateToRuns={(filters) => {
              if (filters) handleFilterChange({ ...filters, offset: 0 })
              setSelectedRunDetail(null)
              setActiveTab('runs')
            }}
            onNavigateToLiveLab={() => setActiveTab('live_lab')}
            onSelectRun={handleSelectRun}
          />
        ) : (
          <div className="workspace-viewport">
            <ReplayView initialRunId={selectedRunId} />
          </div>
        )}
      </div>

      {/* Global Command Palette */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onSelectTab={(tab) => {
          setSelectedRunDetail(null)
          setActiveTab(tab)
        }}
        onSelectRun={handleSelectRun}
      />

      {/* Admin Token Modal */}
      <AdminTokenModal
        isOpen={isTokenModalOpen}
        onClose={() => setIsTokenModalOpen(false)}
        onTokenUpdated={() => setTokenConfigured(hasAdminToken())}
      />

      {/* Persistent Operational Status HUD Footer */}
      <footer className="window-status-footer" data-testid="window-status-footer">
        <div className="status-footer-left">
          <span className="status-indicator-dot online" />
          <span className="status-text font-mono">GATEWAY: ONLINE (PORT 8000)</span>
          <span className="status-divider">|</span>
          <span className="status-metric font-mono">AST: SQLGlot DETERMINISTIC</span>
          <span className="status-divider">|</span>
          <span className="status-metric font-mono">LATENCY OVERHEAD: &lt; 2.5ms</span>
        </div>
        <div className="status-footer-right">
          <span className="status-hotkey"><kbd>Ctrl+K</kbd> Palette</span>
          <span className="status-divider">|</span>
          <span className="status-hotkey"><kbd>j</kbd>/<kbd>k</kbd> Trace Spans</span>
          <span className="status-divider">|</span>
          <span className="status-hotkey"><kbd>Esc</kbd> Close</span>
          <span className="status-divider">|</span>
          <span className="status-version font-mono">AgentShield v1.0.4-soc</span>
        </div>
      </footer>
    </div>
  )
}

export default App
