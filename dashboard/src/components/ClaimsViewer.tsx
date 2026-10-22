import React, { useState, useEffect } from 'react'
import { FileText, Shield, AlertTriangle, RefreshCw, AlertCircle } from 'lucide-react'
import { fetchEvalFile } from '../services/api'

export const ClaimsViewer: React.FC = () => {
  const [activeDoc, setActiveDoc] = useState<'CLAIMS' | 'KNOWN_LIMITATIONS'>('CLAIMS')
  const [claimsContent, setClaimsContent] = useState<string>('')
  const [limitationsContent, setLimitationsContent] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    const load = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const [claimsRes, limitsRes] = await Promise.all([
          fetchEvalFile('CLAIMS.md'),
          fetchEvalFile('KNOWN_LIMITATIONS.md'),
        ])
        if (isMounted) {
          setClaimsContent(claimsRes.content || '')
          setLimitationsContent(limitsRes.content || '')
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Failed to load claims documents')
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }
    load()
    return () => {
      isMounted = false
    }
  }, [])

  const currentContent = activeDoc === 'CLAIMS' ? claimsContent : limitationsContent
  const currentFilename = activeDoc === 'CLAIMS' ? 'CLAIMS.md' : 'KNOWN_LIMITATIONS.md'

  return (
    <div className="workspace-viewport" data-testid="claims-viewer-view">
      <div className="view-header">
        <div className="view-title-wrap">
          <div>
            <div className="evaluate-header-title">Evaluate: Formal Verification & Audit Trail</div>
            <h2 className="view-title" style={{ marginTop: '0.2rem' }}>
              Claims & Known Limitations
            </h2>
          </div>
        </div>

        <div className="header-badges-wrap">
          <div className="badge-scripted-agents">
            Directly rendered from audited repository documentation
          </div>
        </div>
      </div>

      {/* Document Tab Selector */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
        <button
          type="button"
          onClick={() => setActiveDoc('CLAIMS')}
          className={`btn ${activeDoc === 'CLAIMS' ? 'btn-primary' : 'btn-secondary'}`}
          data-testid="tab-claims-md"
        >
          <FileText size={14} className="inline mr-1" />
          CLAIMS.md
        </button>
        <button
          type="button"
          onClick={() => setActiveDoc('KNOWN_LIMITATIONS')}
          className={`btn ${activeDoc === 'KNOWN_LIMITATIONS' ? 'btn-primary' : 'btn-secondary'}`}
          data-testid="tab-limitations-md"
        >
          <AlertTriangle size={14} className="inline mr-1" />
          KNOWN_LIMITATIONS.md
        </button>
      </div>

      {isLoading ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <RefreshCw size={24} className="animate-spin text-mint" style={{ margin: '0 auto 1rem' }} />
          <div>Loading {currentFilename} from read-only evaluation API...</div>
        </div>
      ) : error ? (
        <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--coral)', borderRadius: 'var(--radius-md)', color: 'var(--coral-light)' }}>
          <AlertCircle size={16} className="inline mr-2" />
          {error}
        </div>
      ) : (
        <div className="panel-card" style={{ padding: '1.5rem' }}>
          <div className="panel-header" style={{ marginBottom: '1rem' }}>
            <h3 className="panel-title font-mono text-mint" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileText size={16} />
              {currentFilename}
            </h3>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {currentContent.length.toLocaleString()} characters
            </span>
          </div>

          <pre
            data-testid="claims-preformatted-content"
            style={{
              margin: 0,
              padding: '1rem',
              backgroundColor: '#090d16',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              fontSize: '0.8rem',
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: '650px',
              overflowY: 'auto',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {currentContent}
          </pre>
        </div>
      )}
    </div>
  )
}
