import React, { useState, useEffect } from 'react'
import { Check, X, Shield, Filter, Search, RefreshCw, AlertCircle } from 'lucide-react'
import { fetchHeldOutScenarios } from '../services/api'

interface HeldOutRow {
  scenario_id: string
  agent_type: string
  attack_category: string
  prompt: string
  condition: string
  tool_name: string
  tool_args: string
  blocked_by_policy: string | boolean
  unsafe_effect_occurred: string | boolean
  real_effect_status: string
  effect_evidence: string
  rule_fired: string
  notes: string
}

export const HeldOutExplorer: React.FC = () => {
  const [scenarios, setScenarios] = useState<HeldOutRow[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [selectedCondition, setSelectedCondition] = useState<string>('gateway')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    const load = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const data = await fetchHeldOutScenarios()
        if (isMounted) {
          setScenarios(data || [])
          if (data && data.length > 0) {
            setActiveScenarioId(data[0].scenario_id)
          }
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Failed to load held-out scenarios')
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

  // Filter scenarios
  const filtered = scenarios.filter((sc) => {
    if (selectedCondition !== 'all' && sc.condition !== selectedCondition) {
      return false
    }
    if (selectedCategory !== 'all' && sc.attack_category !== selectedCategory && sc.agent_type !== selectedCategory) {
      return false
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return (
        sc.scenario_id.toLowerCase().includes(q) ||
        sc.prompt.toLowerCase().includes(q) ||
        sc.attack_category.toLowerCase().includes(q) ||
        sc.tool_name.toLowerCase().includes(q) ||
        (sc.rule_fired && sc.rule_fired.toLowerCase().includes(q))
      )
    }
    return true
  })

  // Unique categories
  const categories = Array.from(new Set(scenarios.map((s) => s.attack_category))).filter(Boolean)

  const selectedItem = scenarios.find(
    (s) => s.scenario_id === activeScenarioId && (selectedCondition === 'all' || s.condition === selectedCondition)
  ) || filtered[0]

  return (
    <div className="workspace-viewport" data-testid="held-out-explorer-view">
      {/* View Header */}
      <div className="view-header">
        <div className="view-title-wrap">
          <div>
            <div className="evaluate-header-title">Evaluate: Held-Out Active Attacks Benchmark</div>
            <h2 className="view-title" style={{ marginTop: '0.2rem' }}>
              Held-Out Attack Scenario Explorer
            </h2>
          </div>
        </div>

        <div className="header-badges-wrap">
          <div className="badge-scripted-agents">
            eval_results/held_out_unsafe_results.csv · {scenarios.length} evaluation rows
          </div>
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <RefreshCw size={24} className="animate-spin text-mint" style={{ margin: '0 auto 1rem' }} />
          <div>Loading held-out benchmark dataset from evaluation API...</div>
        </div>
      ) : error ? (
        <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--coral)', borderRadius: 'var(--radius-md)', color: 'var(--coral-light)' }}>
          <AlertCircle size={16} className="inline mr-2" />
          {error}
        </div>
      ) : (
        <>
          {/* Filter Bar */}
          <div className="panel-card" style={{ marginBottom: '1.25rem', padding: '0.75rem 1rem' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flex: 1, minWidth: '220px' }}>
                <Search size={14} className="text-secondary" />
                <input
                  type="text"
                  placeholder="Filter scenarios by ID, prompt, tool, or rule..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="input-field"
                  style={{ width: '100%', fontSize: '0.8rem' }}
                  data-testid="input-heldout-search"
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Condition:</span>
                <select
                  value={selectedCondition}
                  onChange={(e) => setSelectedCondition(e.target.value)}
                  className="select-field"
                  style={{ fontSize: '0.75rem', padding: '4px 8px' }}
                >
                  <option value="gateway">AgentShield Gateway</option>
                  <option value="naive_blocklist">Naive Keyword Blocklist</option>
                  <option value="no_policy">No Policy Baseline</option>
                  <option value="all">All Conditions</option>
                </select>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Category:</span>
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  className="select-field"
                  style={{ fontSize: '0.75rem', padding: '4px 8px' }}
                >
                  <option value="all">All Categories</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Grid Layout: Scenario List (Col 1) vs Scenario Detail Inspector (Col 2) */}
          <div className="middle-grid" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
            {/* Col 1: Scenarios List Table */}
            <div className="panel-card">
              <div className="panel-header">
                <h3 className="panel-title">Evaluation Runs ({filtered.length})</h3>
              </div>

              <div style={{ maxHeight: '520px', overflowY: 'auto' }}>
                <table className="rules-table" style={{ fontSize: '0.775rem' }}>
                  <thead>
                    <tr>
                      <th>Scenario</th>
                      <th>Category</th>
                      <th>Tool</th>
                      <th style={{ textAlign: 'center' }}>Blocked?</th>
                      <th style={{ textAlign: 'center' }}>Unsafe Effect</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((item, idx) => {
                      const isBlocked = String(item.blocked_by_policy).toLowerCase() === 'true'
                      const isUnsafe = String(item.unsafe_effect_occurred).toLowerCase() === 'true'
                      const isSelected = item.scenario_id === activeScenarioId && item.condition === selectedItem?.condition

                      return (
                        <tr
                          key={idx}
                          onClick={() => setActiveScenarioId(item.scenario_id)}
                          style={{
                            cursor: 'pointer',
                            backgroundColor: isSelected ? 'rgba(45, 212, 191, 0.08)' : undefined,
                          }}
                        >
                          <td className="font-mono text-mint" style={{ fontWeight: 600 }}>
                            {item.scenario_id}
                          </td>
                          <td>
                            <span className="tool-chip" style={{ fontSize: '0.68rem' }}>
                              {item.attack_category}
                            </span>
                          </td>
                          <td className="font-mono">{item.tool_name}</td>
                          <td style={{ textAlign: 'center' }}>
                            {isBlocked ? (
                              <span style={{ color: 'var(--mint)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                <Check size={13} /> Yes
                              </span>
                            ) : (
                              <span style={{ color: 'var(--coral)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                <X size={13} /> No
                              </span>
                            )}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {isUnsafe ? (
                              <span className="status-badge badge-high" style={{ fontSize: '0.65rem' }}>
                                Active
                              </span>
                            ) : (
                              <span className="status-badge badge-low" style={{ fontSize: '0.65rem' }}>
                                None
                              </span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Col 2: Scenario Detail Inspector */}
            <div className="panel-card">
              <div className="panel-header">
                <h3 className="panel-title">Inspection Dossier</h3>
                {selectedItem && (
                  <span className="font-mono text-mint" style={{ fontSize: '0.8rem' }}>
                    {selectedItem.scenario_id} ({selectedItem.condition})
                  </span>
                )}
              </div>

              {selectedItem ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.2rem' }}>
                      Attack Prompt
                    </div>
                    <div style={{ padding: '0.6rem 0.75rem', background: '#090d16', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.78rem', color: 'var(--text-primary)' }}>
                      {selectedItem.prompt}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.2rem' }}>
                      Tool Call & Arguments
                    </div>
                    <pre style={{ margin: 0, padding: '0.6rem 0.75rem', background: '#090d16', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.72rem', color: 'var(--mint-light)', overflowX: 'auto', fontFamily: 'var(--font-mono)' }}>
                      {selectedItem.tool_name}({selectedItem.tool_args})
                    </pre>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.2rem' }}>
                      Policy Decision & Rule Fired
                    </div>
                    <div style={{ padding: '0.6rem 0.75rem', background: '#090d16', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.78rem' }}>
                      <span style={{ fontWeight: 600, color: String(selectedItem.blocked_by_policy).toLowerCase() === 'true' ? 'var(--mint)' : 'var(--coral)' }}>
                        {String(selectedItem.blocked_by_policy).toLowerCase() === 'true' ? 'BLOCKED' : 'ALLOWED'}
                      </span>
                      {selectedItem.rule_fired && (
                        <span style={{ marginLeft: '0.5rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                          Rule: {selectedItem.rule_fired}
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.2rem' }}>
                      Effect Evidence & Execution Notes
                    </div>
                    <div style={{ padding: '0.6rem 0.75rem', background: '#090d16', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      <div><strong>Status:</strong> {selectedItem.real_effect_status}</div>
                      {selectedItem.effect_evidence && (
                        <div style={{ marginTop: '0.3rem' }}><strong>Evidence:</strong> {selectedItem.effect_evidence}</div>
                      )}
                      {selectedItem.notes && (
                        <div style={{ marginTop: '0.3rem' }}><strong>Notes:</strong> {selectedItem.notes}</div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  Select a scenario to view detailed evaluation evidence.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
