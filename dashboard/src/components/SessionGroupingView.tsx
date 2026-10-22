import React from 'react'
import { SessionItem } from '../types'

interface SessionGroupingViewProps {
  sessions: SessionItem[]
  onSelectSession: (sessionId: string) => void
  selectedSessionId: string | null
  isLoading: boolean
}

export const SessionGroupingView: React.FC<SessionGroupingViewProps> = ({
  sessions,
  onSelectSession,
  selectedSessionId,
  isLoading,
}) => {
  if (isLoading) {
    return <div className="p-8 text-center text-slate-400">Loading session groups...</div>
  }

  if (sessions.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400" data-testid="no-sessions-message">
        No sessions recorded. Run an agent with <code>session_id</code> specified to group execution runs.
      </div>
    )
  }

  return (
    <div className="session-grid" data-testid="session-grouping-grid">
      {sessions.map((sess) => {
        const isSelected = sess.session_id === selectedSessionId || sess.id === selectedSessionId
        return (
          <div
            key={sess.id}
            className={`session-card ${isSelected ? 'session-card-active' : ''}`}
            onClick={() => onSelectSession(sess.session_id)}
            data-testid={`session-card-${sess.session_id}`}
          >
            <div className="session-card-header">
              <span className="badge-type badge-model">SESSION</span>
              <span className="session-run-count font-mono text-xs">
                {sess.run_count} {sess.run_count === 1 ? 'run' : 'runs'}
              </span>
            </div>

            <h4 className="session-title font-medium text-slate-100 mt-2 truncate">
              {sess.name || `Session ${sess.session_id}`}
            </h4>
            <div className="session-id font-mono text-xs text-slate-400 mt-1 truncate">
              ID: {sess.session_id}
            </div>

            <div className="session-footer mt-4 pt-2 border-t border-slate-700/50 flex justify-between items-center text-xs text-slate-400">
              <span>{new Date(sess.created_at).toLocaleDateString()}</span>
              <button
                type="button"
                className="btn-link"
                onClick={(e) => {
                  e.stopPropagation()
                  onSelectSession(sess.session_id)
                }}
              >
                Filter Runs →
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
