import React, { useState, useEffect } from 'react'
import { ReplayRecord, ReplayListItem } from '../types'
import { fetchReplays, fetchReplayDetail, triggerReplay } from '../services/api'
import { SafePayloadViewer } from './SafePayloadViewer'

interface ReplayViewProps {
  initialRunId?: string | null
}

export const ReplayView: React.FC<ReplayViewProps> = ({ initialRunId }) => {
  const [replays, setReplays] = useState<ReplayListItem[]>([])
  const [selectedReplayId, setSelectedReplayId] = useState<string | null>(null)
  const [selectedReplay, setSelectedReplay] = useState<ReplayRecord | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [isExecuting, setIsExecuting] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // Form state for triggering a new replay
  const [showForm, setShowForm] = useState<boolean>(false)
  const [originalRunId, setOriginalRunId] = useState<string>(initialRunId || '')
  const [targetModel, setTargetModel] = useState<string>('')
  const [targetPrompt, setTargetPrompt] = useState<string>('')
  const [candidatePolicyYaml, setCandidatePolicyYaml] = useState<string>('')
  const [matchingThreshold, setMatchingThreshold] = useState<number>(0.85)
  const [numSamples, setNumSamples] = useState<number>(3)

  // Load replay history
  const loadReplays = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchReplays()
      setReplays(data)
      if (data.length > 0 && !selectedReplayId) {
        setSelectedReplayId(data[0].id)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch replays')
    } finally {
      setIsLoading(false)
    }
  }

  // Load specific replay record
  const loadReplayDetail = async (id: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchReplayDetail(id)
      setSelectedReplay(data)
      setSelectedReplayId(id)
    } catch (err: any) {
      setError(err.message || 'Failed to load replay details')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadReplays()
  }, [])

  useEffect(() => {
    if (selectedReplayId) {
      loadReplayDetail(selectedReplayId)
    }
  }, [selectedReplayId])

  useEffect(() => {
    if (initialRunId) {
      setOriginalRunId(initialRunId)
      setShowForm(true)
    }
  }, [initialRunId])

  // Handle triggering a new replay
  const handleTriggerReplay = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!originalRunId.trim()) {
      setError('Original Run ID is required.')
      return
    }

    setIsExecuting(true)
    setError(null)
    try {
      const result = await triggerReplay({
        original_run_id: originalRunId.trim(),
        target_model: targetModel.trim() || undefined,
        target_prompt: targetPrompt.trim() || undefined,
        candidate_policy_yaml: candidatePolicyYaml.trim() || undefined,
        matching_threshold: matchingThreshold,
        num_samples: numSamples,
        compute_sensitivity: true,
      })
      setSelectedReplay(result)
      setSelectedReplayId(result.replay_id)
      setShowForm(false)
      // Refresh list
      loadReplays()
    } catch (err: any) {
      setError(err.message || 'Failed to execute incident replay')
    } finally {
      setIsExecuting(false)
    }
  }

  return (
    <div className="replay-view-container" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      {/* Title & Action Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#f8fafc', margin: 0 }}>
            Incident Replay Engine (RQ2)
          </h2>
          <p style={{ color: '#94a3b8', fontSize: '14px', marginTop: '4px' }}>
            Deterministic offline counterfactual evaluation with frozen tool outputs, zero live tool calls, fuzzy argument matching, and multi-sample regression detection.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              padding: '8px 16px',
              backgroundColor: showForm ? '#475569' : '#2563eb',
              color: '#ffffff',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {showForm ? 'Cancel Form' : '+ New Replay'}
          </button>
          <button
            onClick={loadReplays}
            disabled={isLoading}
            style={{
              padding: '8px 16px',
              backgroundColor: '#1e293b',
              color: '#94a3b8',
              borderRadius: '6px',
              border: '1px solid #334155',
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', backgroundColor: '#451a1a', border: '1px solid #7f1d1d', borderRadius: '6px', color: '#fca5a5', marginBottom: '20px' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Trigger Replay Form Drawer */}
      {showForm && (
        <div style={{ backgroundColor: '#1e293b', padding: '20px', borderRadius: '8px', border: '1px solid #334155', marginBottom: '24px' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '18px', color: '#f8fafc' }}>Configure Incident Replay</h3>
          <form onSubmit={handleTriggerReplay}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                  Original Run ID (Recorded Trace) *
                </label>
                <input
                  type="text"
                  value={originalRunId}
                  onChange={(e) => setOriginalRunId(e.target.value)}
                  placeholder="e.g. demo-injection-block-be058233"
                  required
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                  Target Model (Optional Counterfactual)
                </label>
                <input
                  type="text"
                  value={targetModel}
                  onChange={(e) => setTargetModel(e.target.value)}
                  placeholder="e.g. claude-3-5-sonnet, gpt-4o, mock-shift"
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                  Fuzzy Argument Matching Threshold ({matchingThreshold})
                </label>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  {[0.75, 0.85, 0.95].map((th) => (
                    <button
                      key={th}
                      type="button"
                      onClick={() => setMatchingThreshold(th)}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: matchingThreshold === th ? '#2563eb' : '#0f172a',
                        color: matchingThreshold === th ? '#ffffff' : '#94a3b8',
                        border: '1px solid #334155',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '13px',
                      }}
                    >
                      {th} {th === 0.85 ? '(Default)' : ''}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                  Number of Samples (N={numSamples})
                </label>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  {[1, 3, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setNumSamples(n)}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: numSamples === n ? '#2563eb' : '#0f172a',
                        color: numSamples === n ? '#ffffff' : '#94a3b8',
                        border: '1px solid #334155',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '13px',
                      }}
                    >
                      N={n} {n === 3 ? '(Default)' : ''}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                Target Prompt Variant (Optional)
              </label>
              <textarea
                value={targetPrompt}
                onChange={(e) => setTargetPrompt(e.target.value)}
                placeholder="Optional counterfactual system prompt or altered instruction..."
                rows={2}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontFamily: 'monospace' }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px' }}>
                Candidate Policy YAML (Optional)
              </label>
              <textarea
                value={candidatePolicyYaml}
                onChange={(e) => setCandidatePolicyYaml(e.target.value)}
                placeholder="version: '1'&#10;rules:&#10;  - id: candidate_rule&#10;    tool: '*'"
                rows={3}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontFamily: 'monospace' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                style={{ padding: '8px 16px', backgroundColor: '#334155', color: '#f8fafc', borderRadius: '6px', border: 'none', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isExecuting}
                style={{ padding: '8px 24px', backgroundColor: '#16a34a', color: '#ffffff', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}
              >
                {isExecuting ? 'Replaying Trajectory...' : 'Execute Replay'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main Layout: Left Past Replays List, Right Detail & Diff */}
      <div style={{ display: 'grid', gridTemplateColumns: '300px minmax(0, 1fr)', gap: '20px', width: '100%' }}>
        {/* Past Replays Sidebar */}
        <div style={{ backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '16px', height: 'fit-content' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', color: '#f8fafc', borderBottom: '1px solid #334155', paddingBottom: '8px' }}>
            Replay History ({replays.length})
          </h3>
          {replays.length === 0 ? (
            <p style={{ color: '#94a3b8', fontSize: '13px' }}>No replays recorded yet. Click &quot;+ New Replay&quot; to test a trace.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '600px', overflowY: 'auto' }}>
              {replays.map((r) => (
                <div
                  key={r.id}
                  onClick={() => setSelectedReplayId(r.id)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '6px',
                    backgroundColor: selectedReplayId === r.id ? '#334155' : '#0f172a',
                    border: selectedReplayId === r.id ? '1px solid #38bdf8' : '1px solid #1e293b',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontSize: '12px', color: '#38bdf8', fontWeight: 600 }}>{r.id.slice(0, 14)}...</span>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: r.outcome === 'success' ? '#14532d' : '#7f1d1d',
                        color: r.outcome === 'success' ? '#86efac' : '#fca5a5',
                      }}
                    >
                      {r.outcome}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    Orig: <span style={{ color: '#cbd5e1' }}>{r.original_run_id.slice(0, 18)}...</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginTop: '6px' }}>
                    <span style={{ color: '#94a3b8' }}>Fidelity: <strong style={{ color: '#f8fafc' }}>{(r.fidelity_score * 100).toFixed(1)}%</strong></span>
                    <span style={{ color: '#94a3b8' }}>Miss: <strong style={{ color: '#f8fafc' }}>{(r.cache_miss_rate * 100).toFixed(0)}%</strong></span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Replay Details & Trajectory Diff */}
        <div>
          {isLoading && !selectedReplay ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>Loading replay execution details...</div>
          ) : !selectedReplay ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', backgroundColor: '#1e293b', borderRadius: '8px' }}>
              Select a replay from the left or trigger a new incident replay.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Executive Metrics Bar */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
                {/* Fidelity Score */}
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase' }}>Fidelity Score</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', color: selectedReplay.fidelity_score >= 0.85 ? '#4ade80' : selectedReplay.fidelity_score >= 0.65 ? '#facc15' : '#f87171', marginTop: '4px' }}>
                    {(selectedReplay.fidelity_score * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                    0.4 S_tool + 0.3 S_args + 0.3 S_outcome
                  </div>
                </div>

                {/* Cache Miss Rate */}
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase' }}>Cache Miss Rate</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', color: selectedReplay.cache_miss_rate === 0 ? '#4ade80' : '#facc15', marginTop: '4px' }}>
                    {(selectedReplay.cache_miss_rate * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                    Zero live tool calls guaranteed
                  </div>
                </div>

                {/* Multi-sample Spread */}
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase' }}>Iteration Spread (N={selectedReplay.iteration_results?.length || 1})</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#38bdf8', marginTop: '4px' }}>
                    {selectedReplay.fidelity_spread.toFixed(4)}
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                    Consistency across runs
                  </div>
                </div>

                {/* Regression Detected */}
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: selectedReplay.regression_detected ? '1px solid #7f1d1d' : '1px solid #14532d' }}>
                  <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase' }}>Regression Status</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: selectedReplay.regression_detected ? '#f87171' : '#4ade80', marginTop: '8px' }}>
                    {selectedReplay.regression_detected ? 'REGRESSION DETECTED' : 'CLEAN / REPRODUCED'}
                  </div>
                  {selectedReplay.regression_reasons && selectedReplay.regression_reasons.length > 0 && (
                    <div style={{ fontSize: '11px', color: '#fca5a5', marginTop: '6px' }}>
                      {selectedReplay.regression_reasons.map((r, i) => (
                        <div key={i}>• {r}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Sample Breakdown Cards */}
              {selectedReplay.iteration_results && selectedReplay.iteration_results.length > 0 && (
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#f8fafc' }}>
                    Multi-Iteration Breakdown ({selectedReplay.iteration_results.length} Iterations Evaluated)
                  </h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                    {selectedReplay.iteration_results.map((s) => (
                      <div key={s.iteration_index} style={{ backgroundColor: '#0f172a', padding: '12px', borderRadius: '6px', border: '1px solid #334155' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#38bdf8' }}>Iteration #{s.iteration_index}</span>
                          <span style={{ fontSize: '11px', color: s.replayed_outcome === 'success' ? '#86efac' : '#fca5a5' }}>{s.replayed_outcome}</span>
                        </div>
                        <div style={{ fontSize: '12px', color: '#cbd5e1' }}>
                          Fidelity: <strong>{(s.fidelity_score * 100).toFixed(1)}%</strong>
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                          S_tool: {s.s_tool.toFixed(2)} | S_args: {s.s_args.toFixed(2)} | S_outcome: {s.s_outcome.toFixed(2)}
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                          Tools: {s.replayed_tools?.join(' → ') || 'none'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Sensitivity Analysis Table */}
              {selectedReplay.sensitivity_table && selectedReplay.sensitivity_table.length > 0 && (
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#f8fafc' }}>
                    Fuzzy Matching Sensitivity Analysis (Thresholds 0.75, 0.85, 0.95)
                  </h4>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', color: '#e2e8f0' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #334155', color: '#94a3b8', textAlign: 'left' }}>
                        <th style={{ padding: '8px' }}>Threshold</th>
                        <th style={{ padding: '8px' }}>Fidelity Score</th>
                        <th style={{ padding: '8px' }}>Cache Misses</th>
                        <th style={{ padding: '8px' }}>Total Calls</th>
                        <th style={{ padding: '8px' }}>Cache Miss Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedReplay.sensitivity_table.map((pt) => (
                        <tr key={pt.threshold} style={{ borderBottom: '1px solid #263347' }}>
                          <td style={{ padding: '8px', fontWeight: 600, color: pt.threshold === 0.85 ? '#38bdf8' : '#e2e8f0' }}>
                            {pt.threshold.toFixed(2)} {pt.threshold === 0.85 ? '(Default)' : ''}
                          </td>
                          <td style={{ padding: '8px' }}>{(pt.fidelity_score * 100).toFixed(1)}%</td>
                          <td style={{ padding: '8px' }}>{pt.cache_misses}</td>
                          <td style={{ padding: '8px' }}>{pt.total_calls}</td>
                          <td style={{ padding: '8px', color: pt.cache_miss_rate > 0 ? '#facc15' : '#4ade80' }}>
                            {(pt.cache_miss_rate * 100).toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Side-by-Side Trajectory Diff (Only rendered when recorded/replayed step strings exist) */}
              {selectedReplay.trajectory_diff && selectedReplay.trajectory_diff.length > 0 && (
                <div style={{ backgroundColor: '#1e293b', padding: '16px', borderRadius: '8px', border: '1px solid #334155' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h4 style={{ margin: 0, fontSize: '16px', color: '#f8fafc' }}>
                      Trajectory Step Diff (Recorded vs. Replayed)
                    </h4>
                    <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                      {selectedReplay.trajectory_diff.length} Step(s) | Plain Text Only
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {selectedReplay.trajectory_diff.map((step) => (
                      <div
                        key={step.step_number}
                        style={{
                          backgroundColor: '#0f172a',
                          borderRadius: '8px',
                          border: step.is_cache_miss ? '1px solid #b45309' : !step.tool_match ? '1px solid #991b1b' : '1px solid #334155',
                          overflow: 'hidden',
                        }}
                      >
                        {/* Step Header */}
                        <div
                          style={{
                            padding: '8px 16px',
                            backgroundColor: '#1e293b',
                            borderBottom: '1px solid #334155',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}
                        >
                          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                            <span style={{ fontWeight: 'bold', color: '#f8fafc', fontSize: '13px' }}>
                              Step #{step.step_number}
                            </span>
                            <span
                              style={{
                                fontSize: '11px',
                                padding: '2px 8px',
                                borderRadius: '4px',
                                backgroundColor: step.tool_match ? '#14532d' : '#7f1d1d',
                                color: step.tool_match ? '#86efac' : '#fca5a5',
                                fontWeight: 600,
                              }}
                            >
                              {step.tool_match ? 'TOOL MATCH' : 'TOOL DIVERGENCE'}
                            </span>
                            {step.is_cache_miss && (
                              <span
                                style={{
                                  fontSize: '11px',
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  backgroundColor: '#78350f',
                                  color: '#fde047',
                                  fontWeight: 600,
                                }}
                              >
                                CACHE MISS (SYNTHETIC RESPONSE)
                              </span>
                            )}
                          </div>
                          <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                            Argument Similarity: <strong style={{ color: '#38bdf8' }}>{(step.arg_similarity * 100).toFixed(1)}%</strong>
                          </span>
                        </div>

                        {/* Step Body: 2 Columns */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '1px', backgroundColor: '#334155' }}>
                          {/* Left Column: Recorded Trace */}
                          <div style={{ backgroundColor: '#0f172a', padding: '14px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                              <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#94a3b8', textTransform: 'uppercase' }}>
                                Recorded Original
                              </span>
                              <span
                                style={{
                                  fontSize: '11px',
                                  padding: '1px 6px',
                                  borderRadius: '4px',
                                  backgroundColor: step.policy_decision_recorded === 'allow' ? '#14532d' : '#7f1d1d',
                                  color: step.policy_decision_recorded === 'allow' ? '#86efac' : '#fca5a5',
                                }}
                              >
                                Policy: {step.policy_decision_recorded || 'n/a'}
                              </span>
                            </div>
                            <div style={{ fontSize: '13px', color: '#38bdf8', fontWeight: 600, marginBottom: '8px' }}>
                              {step.tool_name_recorded || '(None)'}
                            </div>
                            <div style={{ marginBottom: '10px' }}>
                              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Input Arguments:</div>
                              <SafePayloadViewer payload={step.args_recorded} maxChars={200} />
                            </div>
                            <div>
                              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Frozen Output:</div>
                              <SafePayloadViewer payload={step.output_recorded} maxChars={200} />
                            </div>
                          </div>

                          {/* Right Column: Replayed Execution */}
                          <div style={{ backgroundColor: '#0f172a', padding: '14px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                              <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#94a3b8', textTransform: 'uppercase' }}>
                                Replayed Candidate
                              </span>
                              <span
                                style={{
                                  fontSize: '11px',
                                  padding: '1px 6px',
                                  borderRadius: '4px',
                                  backgroundColor: step.policy_decision_replayed === 'allow' ? '#14532d' : '#7f1d1d',
                                  color: step.policy_decision_replayed === 'allow' ? '#86efac' : '#fca5a5',
                                }}
                              >
                                Policy: {step.policy_decision_replayed || 'n/a'}
                              </span>
                            </div>
                            <div style={{ fontSize: '13px', color: step.tool_match ? '#38bdf8' : '#f87171', fontWeight: 600, marginBottom: '8px' }}>
                              {step.tool_name_replayed || '(None)'}
                            </div>
                            <div style={{ marginBottom: '10px' }}>
                              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Replayed Arguments:</div>
                              <SafePayloadViewer payload={step.args_replayed} maxChars={200} />
                            </div>
                            <div>
                              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Replayed Output:</div>
                              <SafePayloadViewer payload={step.output_replayed} maxChars={200} />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
