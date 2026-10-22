import React, { useState, useEffect, useCallback } from 'react'
import { ShieldAlert } from 'lucide-react'
import { ApprovalItem } from '../types'
import { fetchApprovals, decideApproval, hasAdminToken } from '../services/api'
import { SafePayloadViewer } from './SafePayloadViewer'

interface ApprovalsQueueProps {
  onOpenTokenModal: () => void
  tokenConfigured: boolean
}

export const ApprovalsQueue: React.FC<ApprovalsQueueProps> = ({
  onOpenTokenModal,
  tokenConfigured,
}) => {
  const [approvals, setApprovals] = useState<ApprovalItem[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({})
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [decidingId, setDecidingId] = useState<string | null>(null)

  const loadApprovals = useCallback(async (isBackground = false) => {
    if (!isBackground) {
      setIsLoading(true)
    }
    setActionError(null)
    try {
      const data = await fetchApprovals(statusFilter === 'all' ? undefined : statusFilter)
      setApprovals(data || [])
    } catch (err: any) {
      console.error('Failed to load approvals:', err)
      if (!isBackground) {
        setActionError(err.message || 'Failed to load approvals')
        setApprovals([])
      }
    } finally {
      if (!isBackground) {
        setIsLoading(false)
      }
    }
  }, [statusFilter])

  useEffect(() => {
    loadApprovals(false)
    // Poll for pending approvals every 3 seconds while on pending filter
    const interval = setInterval(() => {
      loadApprovals(true)
    }, 3000)
    return () => clearInterval(interval)
  }, [loadApprovals])

  // Local second-by-second countdown ticker for pending items
  useEffect(() => {
    const timer = setInterval(() => {
      setApprovals((prev) =>
        prev.map((app) => {
          if (app.status === 'pending' && app.remaining_seconds > 0) {
            const nextRemaining = Math.max(0, app.remaining_seconds - 1)
            return {
              ...app,
              remaining_seconds: nextRemaining,
              status: nextRemaining === 0 ? 'timed_out' : app.status,
            }
          }
          return app
        })
      )
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const handleDecision = async (approvalId: string, decision: 'approve' | 'reject') => {
    if (!tokenConfigured) {
      onOpenTokenModal()
      return
    }

    setDecidingId(approvalId)
    setActionError(null)
    setActionSuccess(null)
    const reason = rejectionReasons[approvalId] || (decision === 'approve' ? 'Approved by operator' : 'Rejected by operator')

    try {
      await decideApproval(approvalId, decision, reason, 'dashboard_admin')
      setActionSuccess(`Successfully ${decision === 'approve' ? 'approved' : 'rejected'} tool call.`)
      setApprovals((prev) =>
        prev.map((app) =>
          app.id === approvalId
            ? { ...app, status: decision === 'approve' ? 'approved' : 'rejected' }
            : app
        )
      )
    } catch (err: any) {
      console.error('Decision failed:', err)
      setActionError(err.message || `Failed to ${decision} approval.`)
    } finally {
      setDecidingId(null)
    }
  }

  const handleReasonChange = (approvalId: string, value: string) => {
    setRejectionReasons((prev) => ({ ...prev, [approvalId]: value }))
  }

  return (
    <div className="approvals-queue-container" data-testid="approvals-queue">
      {/* Queue Header & Filters */}
      <div className="queue-header">
        <div>
          <h2 className="section-title">Human-in-the-Loop Approvals Queue</h2>
          <p className="section-subtitle">
            Review and decide tool invocations requiring human confirmation before execution.
          </p>
        </div>

        <div className="queue-actions">
          <div className="filter-chips">
            {['pending', 'approved', 'rejected', 'timed_out', 'all'].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`filter-chip ${statusFilter === st ? 'filter-chip-active' : ''}`}
                data-testid={`filter-${st}`}
              >
                {st.replace('_', ' ').toUpperCase()}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => loadApprovals(false)}
            className="btn btn-secondary"
            disabled={isLoading}
            data-testid="btn-refresh-approvals"
          >
            {isLoading ? 'Refreshing...' : '🔄 Refresh'}
          </button>
        </div>
      </div>

      {/* Admin Token Banner if not set */}
      {!tokenConfigured && (
        <div className="alert-banner alert-warning" data-testid="token-missing-banner">
          <div className="alert-icon">⚠️</div>
          <div className="alert-content">
            <strong>Admin Token Required:</strong> An in-memory administrative token is required to
            record approval decisions.
          </div>
          <button
            type="button"
            onClick={onOpenTokenModal}
            className="btn btn-primary btn-sm"
            data-testid="btn-set-token-banner"
          >
            Set Admin Token
          </button>
        </div>
      )}

      {/* Action Notifications */}
      {actionError && (
        <div className="alert-banner alert-danger" data-testid="action-error-banner">
          <div className="alert-icon">❌</div>
          <div className="alert-content">{actionError}</div>
          <button type="button" onClick={() => setActionError(null)} className="alert-close">
            ×
          </button>
        </div>
      )}

      {actionSuccess && (
        <div className="alert-banner alert-success" data-testid="action-success-banner">
          <div className="alert-icon">✅</div>
          <div className="alert-content">{actionSuccess}</div>
          <button type="button" onClick={() => setActionSuccess(null)} className="alert-close">
            ×
          </button>
        </div>
      )}

      {/* Approvals List */}
      <div className="approvals-list" data-testid="approvals-list">
        {approvals.length === 0 ? (
          <div className="empty-state" data-testid="empty-approvals-message">
            <div className="empty-icon">✓</div>
            <h3>No {statusFilter === 'all' ? '' : statusFilter} approvals found</h3>
            <p>Any agent tool calls matched with 'require_approval' policy rules will appear here.</p>
          </div>
        ) : (
          approvals.map((app) => (
            <div
              key={app.id}
              className={`approval-card approval-card-${app.status}`}
              data-testid={`approval-card-${app.id}`}
            >
              {/* Card Header */}
              <div className="approval-card-header">
                <div className="approval-title-group">
                  <span className="tool-icon">🔧</span>
                  <div>
                    <h3 className="approval-tool-name">{app.tool_name}</h3>
                    <div className="approval-meta-row">
                      <span className="meta-item">
                        <strong>Run ID:</strong>{' '}
                        <code className="code-snippet">{app.run_id}</code>
                      </span>
                      <span className="meta-item">
                        <strong>Requested:</strong>{' '}
                        {(() => {
                          const ts = app.requested_at || app.created_at
                          if (!ts) return 'just now'
                          const d = new Date(ts)
                          return isNaN(d.getTime()) ? 'just now' : d.toLocaleTimeString()
                        })()}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="approval-badges-group">
                  <span
                    className={`status-badge badge-${app.status}`}
                    data-testid={`status-badge-${app.id}`}
                  >
                    {app.status.toUpperCase()}
                  </span>

                  {app.status === 'pending' && (
                    <div
                      className={`countdown-chip ${app.remaining_seconds < 10 ? 'countdown-urgent' : ''}`}
                      data-testid={`countdown-${app.id}`}
                    >
                      ⏱️ {Math.ceil(app.remaining_seconds)}s remaining
                    </div>
                  )}
                </div>
              </div>

              {/* Call Hash & Single-Use Notice */}
              <div className="call-hash-banner">
                <span className="hash-label">Call Signature Hash (Single-Use Binding):</span>
                <code className="call-hash-code">{app.call_hash}</code>
              </div>

              {/* Arguments Payload - Rendered strictly as Plain Text */}
              <div className="approval-arguments-section">
                <SafePayloadViewer
                  label="Tool Arguments (Verified Redacted)"
                  payload={app.tool_args || app.arguments}
                  maxChars={600}
                />
              </div>

              {/* Decision Section */}
              {app.status === 'pending' ? (
                <div className="approval-action-bar">
                  <div className="reason-input-wrapper">
                    <input
                      type="text"
                      placeholder="Optional decision reason or security notes..."
                      value={rejectionReasons[app.id] || ''}
                      onChange={(e) => handleReasonChange(app.id, e.target.value)}
                      className="input-reason"
                      data-testid={`input-reason-${app.id}`}
                    />
                  </div>

                  <div className="action-buttons-group">
                    <button
                      type="button"
                      onClick={() => handleDecision(app.id, 'reject')}
                      disabled={decidingId === app.id}
                      className="btn btn-danger"
                      data-testid={`btn-reject-${app.id}`}
                    >
                      {decidingId === app.id ? 'Processing...' : '✕ Reject Call'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDecision(app.id, 'approve')}
                      disabled={decidingId === app.id}
                      className="btn btn-success"
                      data-testid={`btn-approve-${app.id}`}
                    >
                      {decidingId === app.id ? 'Processing...' : '✓ Approve Call'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="approval-decision-details">
                  <div className="decision-meta-item">
                    <strong>Decided:</strong>{' '}
                    {app.decided_at ? new Date(app.decided_at).toLocaleTimeString() : 'N/A'}
                  </div>
                  <div className="decision-meta-item">
                    <strong>Decided By:</strong>{' '}
                    <span className="unverified-note">
                      {app.decided_by || 'system'} (self-reported)
                    </span>
                  </div>
                  {app.decision_reason && (
                    <div className="decision-meta-item">
                      <strong>Reason:</strong> {app.decision_reason}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
