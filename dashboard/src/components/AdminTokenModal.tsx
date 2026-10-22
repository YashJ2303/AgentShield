import React, { useState } from 'react'
import { getAdminToken, setAdminToken, hasAdminToken } from '../services/api'

interface AdminTokenModalProps {
  isOpen: boolean
  onClose: () => void
  onTokenUpdated: () => void
}

export const AdminTokenModal: React.FC<AdminTokenModalProps> = ({
  isOpen,
  onClose,
  onTokenUpdated,
}) => {
  const [tokenInput, setTokenInput] = useState(getAdminToken())

  if (!isOpen) return null

  const handleSave = () => {
    setAdminToken(tokenInput)
    onTokenUpdated()
    onClose()
  }

  const handleClear = () => {
    setAdminToken('')
    setTokenInput('')
    onTokenUpdated()
    onClose()
  }

  return (
    <div className="modal-backdrop" data-testid="admin-token-modal">
      <div className="modal-dialog">
        <div className="modal-header">
          <h3 className="modal-title">Admin Authentication Token</h3>
          <button onClick={onClose} className="btn-close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <p className="text-xs text-slate-300 mb-3">
            The administrator token is required exclusively for <strong>mutating actions</strong> (such as policy updates, version rollback, and approval decisions).
          </p>
          <div className="security-notice mb-4">
            <span className="font-semibold text-amber-300">🔒 Security Boundary:</span>
            <span className="text-xs text-slate-300 ml-1">
              This token is retained strictly in volatile browser runtime memory. It is <strong>never written</strong> to localStorage, sessionStorage, or cookies.
            </span>
          </div>

          <label htmlFor="admin-token-input" className="filter-label">
            X-Admin-Token Secret:
          </label>
          <input
            id="admin-token-input"
            type="password"
            placeholder="Enter administrative token..."
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            className="input-field w-full font-mono mt-1"
            data-testid="input-admin-token"
          />
        </div>

        <div className="modal-footer">
          {hasAdminToken() && (
            <button type="button" onClick={handleClear} className="btn-danger-outline mr-auto" data-testid="btn-clear-token">
              Clear Token
            </button>
          )}
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button type="button" onClick={handleSave} className="btn-primary ml-2" data-testid="btn-save-token">
            Save in Memory
          </button>
        </div>
      </div>
    </div>
  )
}
