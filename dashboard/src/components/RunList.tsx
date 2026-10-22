import React, { useState } from 'react'
import { ShieldAlert, Copy, Check } from 'lucide-react'
import { Run, RunFilters } from '../types'

interface RunListProps {
  runs: Run[]
  total: number
  filters: RunFilters
  onFilterChange: (newFilters: Partial<RunFilters>) => void
  onSelectRun: (runId: string) => void
  selectedRunId: string | null
  isLoading: boolean
}

export const RunList: React.FC<RunListProps> = ({
  runs,
  total,
  filters,
  onFilterChange,
  onSelectRun,
  selectedRunId,
  isLoading,
}) => {
  const currentPage = Math.floor(filters.offset / filters.limit) + 1
  const totalPages = Math.max(1, Math.ceil(total / filters.limit))
  const [copiedRunId, setCopiedRunId] = useState<string | null>(null)

  const handleCopyRunId = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    navigator.clipboard.writeText(id)
    setCopiedRunId(id)
    setTimeout(() => setCopiedRunId(null), 1500)
  }

  return (
    <div className="run-list-container">
      {/* Quick Filter Pill Chips */}
      <div className="quick-filter-chips" data-testid="quick-filter-chips">
        <span className="quick-filter-label">Filter presets:</span>
        <button
          type="button"
          className={`quick-chip-btn ${!filters.outcome ? 'active' : ''}`}
          onClick={() => onFilterChange({ outcome: '', offset: 0 })}
          data-testid="chip-filter-all"
        >
          All Runs
        </button>
        <button
          type="button"
          className={`quick-chip-btn chip-blocked ${filters.outcome === 'blocked' ? 'active' : ''}`}
          onClick={() => onFilterChange({ outcome: 'blocked', offset: 0 })}
          data-testid="chip-filter-blocked"
        >
          Policy Blocks Only
        </button>
        <button
          type="button"
          className={`quick-chip-btn chip-success ${filters.outcome === 'success' ? 'active' : ''}`}
          onClick={() => onFilterChange({ outcome: 'success', offset: 0 })}
          data-testid="chip-filter-success"
        >
          Success
        </button>
        <button
          type="button"
          className={`quick-chip-btn chip-in-progress ${filters.outcome === 'in_progress' ? 'active' : ''}`}
          onClick={() => onFilterChange({ outcome: 'in_progress', offset: 0 })}
          data-testid="chip-filter-in-progress"
        >
          In Progress
        </button>
      </div>

      {/* Filters Bar */}
      <div className="filters-bar" data-testid="run-filters-bar">
        <div className="filter-group">
          <label htmlFor="filter-search">Search Keyword</label>
          <input
            id="filter-search"
            type="text"
            placeholder="Search prompts, tool args..."
            value={filters.search || ''}
            onChange={(e) => onFilterChange({ search: e.target.value, offset: 0 })}
            className="input-field"
            data-testid="input-search"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="filter-outcome">Outcome</label>
          <select
            id="filter-outcome"
            value={filters.outcome || ''}
            onChange={(e) => onFilterChange({ outcome: e.target.value, offset: 0 })}
            className="select-field"
            data-testid="select-outcome"
          >
            <option value="">All Outcomes</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="blocked">Blocked</option>
            <option value="timed_out">Timed Out</option>
            <option value="in_progress">In Progress</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="filter-model">Model</label>
          <input
            id="filter-model"
            type="text"
            placeholder="Filter model..."
            value={filters.model || ''}
            onChange={(e) => onFilterChange({ model: e.target.value, offset: 0 })}
            className="input-field"
            data-testid="input-model"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="filter-session">Session ID</label>
          <input
            id="filter-session"
            type="text"
            placeholder="Session ID..."
            value={filters.session_id || ''}
            onChange={(e) => onFilterChange({ session_id: e.target.value, offset: 0 })}
            className="input-field"
            data-testid="input-session"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="filter-start-date">From Date</label>
          <input
            id="filter-start-date"
            type="date"
            value={filters.start_date || ''}
            onChange={(e) => onFilterChange({ start_date: e.target.value, offset: 0 })}
            className="input-field"
            data-testid="input-start-date"
          />
        </div>

        <div className="filter-group">
          <label htmlFor="filter-end-date">To Date</label>
          <input
            id="filter-end-date"
            type="date"
            value={filters.end_date || ''}
            onChange={(e) => onFilterChange({ end_date: e.target.value, offset: 0 })}
            className="input-field"
            data-testid="input-end-date"
          />
        </div>

        <div className="filter-group flex-end">
          <button
            type="button"
            onClick={() =>
              onFilterChange({
                outcome: '',
                model: '',
                session_id: '',
                search: '',
                start_date: '',
                end_date: '',
                offset: 0,
              })
            }
            className="btn-secondary"
            data-testid="btn-reset-filters"
          >
            Reset
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="table-responsive">
        <table className="data-table" data-testid="runs-table">
          <thead>
            <tr>
              <th>Task / Run ID</th>
              <th>Session</th>
              <th>Model</th>
              <th>Outcome</th>
              <th>Cost</th>
              <th>Tokens</th>
              <th>Steps</th>
              <th>Latency</th>
              <th>Started</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && runs.length === 0 ? (
              <tr>
                <td colSpan={10} className="text-center py-8 text-slate-400">
                  Loading agent execution runs...
                </td>
              </tr>
            ) : runs.length === 0 ? (
              <tr>
                <td colSpan={10} className="text-center py-8 text-slate-400" data-testid="no-runs-message">
                  No runs found matching current filter criteria.
                </td>
              </tr>
            ) : (
              runs.map((r) => {
                const outcomeClass =
                  r.outcome === 'success'
                    ? 'badge-success'
                    : r.outcome === 'blocked'
                    ? 'badge-blocked'
                    : r.outcome === 'failure'
                    ? 'badge-failure'
                    : 'badge-neutral'

                const isSelected = r.id === selectedRunId

                return (
                  <tr
                    key={r.id}
                    className={`table-row ${isSelected ? 'row-active' : ''}`}
                    onClick={() => onSelectRun(r.id)}
                    data-testid={`run-row-${r.id}`}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="font-medium text-slate-100">{r.task_id || 'Untitled Task'}</span>
                        {(r.id?.startsWith('demo-') || r.session_id?.includes('demo')) && (
                          <span
                            data-testid={`demo-chip-${r.id}`}
                            style={{
                              fontSize: '10px',
                              padding: '1px 6px',
                              borderRadius: '4px',
                              background: 'rgba(56, 189, 248, 0.15)',
                              color: '#38bdf8',
                              border: '1px solid rgba(56, 189, 248, 0.3)',
                              fontWeight: 600,
                            }}
                          >
                            DEMO
                          </span>
                        )}
                      </div>
                      <div className="run-id-row" style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                        <span className="font-mono text-xs text-slate-400 truncate max-w-xs">{r.id}</span>
                        <button
                          type="button"
                          className="btn-copy-id-small"
                          title="Copy Run ID"
                          onClick={(e) => handleCopyRunId(e, r.id)}
                          data-testid={`btn-copy-id-${r.id}`}
                        >
                          {copiedRunId === r.id ? (
                            <span style={{ color: 'var(--mint)', display: 'inline-flex', alignItems: 'center', gap: '2px', fontSize: '10px' }}>
                              <Check size={10} /> Copied!
                            </span>
                          ) : (
                            <Copy size={10} />
                          )}
                        </button>
                      </div>
                      {/* Micro-toolchain flow indicator */}
                      <div className="micro-toolchain-tag" style={{ marginTop: '4px' }}>
                        <span className="toolchain-step model-step">{r.model ? r.model.replace(/^models\//, '').slice(0, 14) : 'agent'}</span>
                        <span className="toolchain-arrow">➔</span>
                        <span className="toolchain-step guard-step">AST Guard</span>
                        <span className="toolchain-arrow">➔</span>
                        <span className={`toolchain-step outcome-step ${r.outcome}`}>
                          {r.outcome === 'blocked' ? 'Blocked' : r.outcome === 'success' ? 'Allow' : r.outcome}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="font-mono text-xs text-slate-300">
                        {r.external_session_id || r.session_id || '—'}
                      </div>
                    </td>
                    <td>
                      <span className="font-mono text-xs text-slate-200">{r.model || 'unknown'}</span>
                    </td>
                    <td>
                      <span className={`badge-outcome ${outcomeClass}`} data-testid={`outcome-${r.id}`}>
                        {r.outcome}
                      </span>
                    </td>
                    <td className="font-mono text-xs">
                      {r.total_cost !== null && r.total_cost !== undefined ? `$${r.total_cost.toFixed(4)}` : 'Unknown'}
                    </td>
                    <td className="font-mono text-xs">{r.total_tokens.toLocaleString()}</td>
                    <td className="font-mono text-xs">{r.step_count}</td>
                    <td className="font-mono text-xs">{r.latency_ms}ms</td>
                    <td className="text-xs text-slate-400">
                      {(() => {
                        const ts = r.started_at || r.created_at
                        if (!ts) return '—'
                        const d = new Date(ts)
                        return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      })()}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            onSelectRun(r.id)
                          }}
                          className={`btn-table-action ${isSelected ? 'btn-active' : ''}`}
                          data-testid={`btn-view-${r.id}`}
                        >
                          {isSelected ? 'Active' : 'View Trace'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="pagination-bar">
        <div className="pagination-info text-xs text-slate-400">
          Showing {total === 0 ? 0 : filters.offset + 1} to {Math.min(filters.offset + filters.limit, total)} of {total} runs
        </div>
        <div className="pagination-controls">
          <button
            type="button"
            disabled={filters.offset === 0}
            onClick={() => onFilterChange({ offset: Math.max(0, filters.offset - filters.limit) })}
            className="btn-pagination"
            data-testid="btn-prev-page"
          >
            Previous
          </button>
          <span className="page-indicator text-xs font-mono">
            Page {currentPage} of {totalPages}
          </span>
          <button
            type="button"
            disabled={filters.offset + filters.limit >= total}
            onClick={() => onFilterChange({ offset: filters.offset + filters.limit })}
            className="btn-pagination"
            data-testid="btn-next-page"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
