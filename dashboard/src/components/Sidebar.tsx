import React from 'react'
import {
  Shield,
  Activity,
  Layers,
  CheckSquare,
  Sliders,
  BarChart3,
  FlaskConical,
  Compass,
  RotateCcw,
  FileCheck,
  KeyRound,
  ShieldAlert,
  Network,
  ShieldCheck,
  TestTube,
} from 'lucide-react'

export type NavTabId =
  | 'command_center'
  | 'runs'
  | 'approvals'
  | 'playground'
  | 'analytics'
  | 'live_lab'
  | 'cyber_arc'
  | 'study_overview'
  | 'held_out'
  | 'replay'
  | 'claims'

interface SidebarProps {
  activeTab: NavTabId
  onSelectTab: (tab: NavTabId) => void
  pendingApprovalsCount?: number
  runsCount?: number
  onOpenTokenModal: () => void
  tokenConfigured: boolean
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  pendingApprovalsCount = 0,
  runsCount,
  onOpenTokenModal,
  tokenConfigured,
}) => {
  return (
    <aside className="app-sidebar" data-testid="app-sidebar">
      <div className="sidebar-brand">
        <div style={{ width: '20px', height: '20px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '2px', marginRight: '4px' }}>
          <div style={{ background: '#2dd4bf', borderRadius: '1.5px', boxShadow: '0 0 6px #2dd4bf' }} />
          <div style={{ background: '#2dd4bf', borderRadius: '1.5px' }} />
          <div style={{ background: '#14b8a6', borderRadius: '1.5px' }} />
          <div style={{ background: '#2dd4bf', borderRadius: '1.5px' }} />
          <div style={{ background: '#14b8a6', borderRadius: '1.5px' }} />
          <div style={{ background: '#0d9488', borderRadius: '1.5px' }} />
          <div style={{ background: '#14b8a6', borderRadius: '1.5px' }} />
          <div style={{ background: '#0d9488', borderRadius: '1.5px' }} />
          <div style={{ background: '#2dd4bf', borderRadius: '1.5px' }} />
        </div>
        <span>AgentShield</span>
      </div>

      {/* Group: OPERATE */}
      <div className="sidebar-nav-group">
        <div className="sidebar-group-title">Operate</div>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'command_center' ? 'active' : ''}`}
          onClick={() => onSelectTab('command_center')}
          data-testid="nav-command-center"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={15} />
            Command center
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'runs' ? 'active' : ''}`}
          onClick={() => onSelectTab('runs')}
          data-testid="nav-runs"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Layers size={15} />
            Runs and sessions
          </span>
          {runsCount !== undefined && runsCount > 0 && (
            <span className="sidebar-badge-neutral" data-testid="sidebar-runs-count">{runsCount}</span>
          )}
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'approvals' ? 'active' : ''}`}
          onClick={() => onSelectTab('approvals')}
          data-testid="nav-approvals"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <CheckSquare size={15} />
            Approvals
          </span>
          {pendingApprovalsCount > 0 && (
            <span className="sidebar-badge" data-testid="sidebar-approvals-count">{pendingApprovalsCount}</span>
          )}
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'playground' ? 'active' : ''}`}
          onClick={() => onSelectTab('playground')}
          data-testid="nav-playground"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Sliders size={15} />
            Policy playground
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => onSelectTab('analytics')}
          data-testid="nav-analytics"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <BarChart3 size={15} />
            Analytics
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'live_lab' ? 'active' : ''}`}
          onClick={() => onSelectTab('live_lab')}
          data-testid="nav-live-lab"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <TestTube size={15} />
            Live Agent Lab
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'cyber_arc' ? 'active' : ''}`}
          onClick={() => onSelectTab('cyber_arc')}
          data-testid="nav-cyber-arc"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Network size={15} />
            CyberArc 3D
          </span>
          <span style={{ fontSize: '0.6rem', padding: '1px 5px', borderRadius: '4px', background: 'rgba(45, 212, 191, 0.15)', color: '#2dd4bf', border: '1px solid rgba(45, 212, 191, 0.3)', fontWeight: 700 }}>3D</span>
        </button>
      </div>

      {/* Group: EVALUATE */}
      <div className="sidebar-nav-group" style={{ marginTop: '0.75rem' }}>
        <div className="sidebar-group-title">Evaluate</div>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'study_overview' ? 'active' : ''}`}
          onClick={() => onSelectTab('study_overview')}
          data-testid="nav-study-overview"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FlaskConical size={15} />
            Study overview
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'held_out' ? 'active' : ''}`}
          onClick={() => onSelectTab('held_out')}
          data-testid="nav-held-out"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Compass size={15} />
            Held-out explorer
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'replay' ? 'active' : ''}`}
          onClick={() => onSelectTab('replay')}
          data-testid="nav-replay"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <RotateCcw size={15} />
            Replay lab
          </span>
        </button>

        <button
          type="button"
          className={`sidebar-nav-item ${activeTab === 'claims' ? 'active' : ''}`}
          onClick={() => onSelectTab('claims')}
          data-testid="nav-claims"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FileCheck size={15} />
            Claims and limits
          </span>
        </button>
      </div>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <button
          type="button"
          onClick={onOpenTokenModal}
          className="sidebar-nav-item"
          style={{
            fontSize: '0.75rem',
            color: tokenConfigured ? 'var(--mint)' : 'var(--amber)',
            borderColor: tokenConfigured ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)',
            backgroundColor: tokenConfigured ? 'rgba(16, 185, 129, 0.05)' : 'rgba(245, 158, 11, 0.05)',
            borderWidth: '1px',
            borderStyle: 'solid',
          }}
          data-testid="btn-admin-token-sidebar"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <KeyRound size={13} />
            {tokenConfigured ? 'Admin Token Active' : 'Set Admin Token'}
          </span>
        </button>
      </div>
    </aside>
  )
}
