import React, { useState } from 'react'

interface SafePayloadViewerProps {
  payload: any
  maxChars?: number
  label?: string
}

export function formatPayloadToString(payload: any): string {
  if (payload === null || payload === undefined) {
    return 'null'
  }
  if (typeof payload === 'string') {
    return payload
  }
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
}

export const SafePayloadViewer: React.FC<SafePayloadViewerProps> = ({
  payload,
  maxChars = 300,
  label,
}) => {
  const [expanded, setExpanded] = useState(false)
  const formattedText = formatPayloadToString(payload)
  const isTruncated = formattedText.length > maxChars
  const displayText = !expanded && isTruncated ? formattedText.slice(0, maxChars) + '...' : formattedText

  return (
    <div className="safe-payload-viewer">
      {label && <div className="payload-label">{label}</div>}
      {/* 
        CRITICAL SECURITY REQUIREMENT:
        Always render payloads as plain text via React text nodes.
        NEVER use dangerouslySetInnerHTML or parse HTML/Markdown.
        This guarantees malicious strings like <script> or <img onerror> are safely escaped.
      */}
      <pre data-testid="safe-payload-content" className="payload-code">
        {displayText}
      </pre>
      {isTruncated && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="expand-toggle-btn"
          data-testid="expand-toggle-btn"
        >
          {expanded ? 'Show less' : `Show more (${formattedText.length - maxChars} more characters)`}
        </button>
      )}
    </div>
  )
}
