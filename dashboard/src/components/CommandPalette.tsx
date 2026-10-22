import React, { useState, useEffect, useRef, useMemo } from 'react'
import {
  Search,
  Activity,
  Layers,
  CheckSquare,
  Sliders,
  BarChart3,
  FlaskConical,
  Compass,
  RotateCcw,
  FileCheck,
  Database,
  TestTube,
  Network,
} from 'lucide-react'
import { NavTabId } from './Sidebar'

export interface PaletteItem {
  id: string
  title: string
  subtitle?: string
  category: 'Navigation' | 'System'
  icon: React.ReactNode
  action: () => void
}

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  onSelectTab: (tab: NavTabId) => void
  onSelectRun?: (runId: string) => void
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onSelectTab,
}) => {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Focus input whenever opened
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Build commands catalog
  const items: PaletteItem[] = useMemo(() => {
    return [
      // Navigation
      {
        id: 'nav-command-center',
        title: 'Command Center',
        subtitle: 'Real-time telemetry, threat stream, and urgent approvals',
        category: 'Navigation',
        icon: <Activity size={15} className="text-mint" />,
        action: () => onSelectTab('command_center'),
      },
      {
        id: 'nav-runs',
        title: 'Runs and Sessions',
        subtitle: 'Execution trace audit, waterfall timeline, and step parameters',
        category: 'Navigation',
        icon: <Layers size={15} className="text-mint" />,
        action: () => onSelectTab('runs'),
      },
      {
        id: 'nav-approvals',
        title: 'Approvals Queue',
        subtitle: 'Human-in-the-loop authorization and countdown timers',
        category: 'Navigation',
        icon: <CheckSquare size={15} className="text-amber" />,
        action: () => onSelectTab('approvals'),
      },
      {
        id: 'nav-playground',
        title: 'Policy Playground',
        subtitle: 'Live gateway AST validation and parameter checks',
        category: 'Navigation',
        icon: <Sliders size={15} className="text-teal" />,
        action: () => onSelectTab('playground'),
      },
      {
        id: 'nav-analytics',
        title: 'Analytics Dashboard',
        subtitle: 'Token usage, tool frequency, and anomaly distribution',
        category: 'Navigation',
        icon: <BarChart3 size={15} className="text-mint" />,
        action: () => onSelectTab('analytics'),
      },
      {
        id: 'nav-live-lab',
        title: 'Live Agent Lab',
        subtitle: 'Real-world API calls with live guardrail enforcement',
        category: 'Navigation',
        icon: <TestTube size={15} className="text-mint" />,
        action: () => onSelectTab('live_lab'),
      },
      {
        id: 'nav-cyber-arc',
        title: 'CyberArc 3D Topology',
        subtitle: 'Cinematic 3D WebGL agent security universe and live topology',
        category: 'Navigation',
        icon: <Network size={15} className="text-mint" />,
        action: () => onSelectTab('cyber_arc'),
      },
      {
        id: 'nav-study-overview',
        title: 'Study Overview & Replay Lab',
        subtitle: 'Wilson score 95% CIs and evaluation results',
        category: 'Navigation',
        icon: <FlaskConical size={15} className="text-mint" />,
        action: () => onSelectTab('study_overview'),
      },
      {
        id: 'nav-held-out',
        title: 'Held-Out Attacks Benchmark',
        subtitle: 'Evaluation against active injection attack scenarios',
        category: 'Navigation',
        icon: <Compass size={15} className="text-mint" />,
        action: () => onSelectTab('held_out'),
      },
      {
        id: 'nav-replay',
        title: 'Side-by-Side Replay Lab',
        subtitle: 'Baseline vs AgentShield Protected execution comparisons',
        category: 'Navigation',
        icon: <RotateCcw size={15} className="text-mint" />,
        action: () => onSelectTab('replay'),
      },
      {
        id: 'nav-claims',
        title: 'Claims & Safety Boundaries',
        subtitle: 'Audited CLAIMS.md and KNOWN_LIMITATIONS.md documents',
        category: 'Navigation',
        icon: <FileCheck size={15} className="text-mint" />,
        action: () => onSelectTab('claims'),
      },
    ]
  }, [onSelectTab])

  // Filter items by search query
  const filteredItems = useMemo(() => {
    if (!query.trim()) return items
    const lower = query.toLowerCase()
    return items.filter(
      (item) =>
        item.title.toLowerCase().includes(lower) ||
        (item.subtitle && item.subtitle.toLowerCase().includes(lower)) ||
        item.category.toLowerCase().includes(lower)
    )
  }, [items, query])

  // Reset index when search query changes
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // Key navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev < filteredItems.length - 1 ? prev + 1 : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : filteredItems.length - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filteredItems[selectedIndex]) {
        filteredItems[selectedIndex].action()
        onClose()
      }
    }
  }

  if (!isOpen) return null

  return (
    <div className="palette-backdrop" onClick={onClose} data-testid="command-palette-backdrop">
      <div
        className="palette-modal"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
        data-testid="command-palette-modal"
      >
        {/* Search Bar */}
        <div className="palette-search-bar">
          <Search size={16} className="text-mint" style={{ marginRight: '10px' }} />
          <input
            ref={inputRef}
            type="text"
            className="palette-input"
            placeholder="Type a command or navigate to a view..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="palette-search-input"
          />
          <span className="palette-badge">ESC to close</span>
        </div>

        {/* Results List */}
        <div className="palette-results" ref={listRef}>
          {filteredItems.length === 0 ? (
            <div className="palette-empty">No matching commands found.</div>
          ) : (
            filteredItems.map((item, index) => {
              const isSelected = index === selectedIndex
              return (
                <div
                  key={item.id}
                  className={`palette-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => {
                    item.action()
                    onClose()
                  }}
                  onMouseEnter={() => setSelectedIndex(index)}
                  data-testid={`palette-item-${item.id}`}
                >
                  <div className="palette-item-icon">{item.icon}</div>
                  <div className="palette-item-text">
                    <div className="palette-item-title">{item.title}</div>
                    {item.subtitle && (
                      <div className="palette-item-sub">{item.subtitle}</div>
                    )}
                  </div>
                  <span className="palette-category-badge">{item.category}</span>
                </div>
              )
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="palette-footer">
          <span>
            <kbd>↑</kbd> <kbd>↓</kbd> to navigate
          </span>
          <span>
            <kbd>ENTER</kbd> to select
          </span>
          <span>
            <kbd>ESC</kbd> to dismiss
          </span>
        </div>
      </div>
    </div>
  )
}
