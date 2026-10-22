import { describe, it, expect } from 'vitest'
import { sortSpansDeterministically, calculateTimelineBounds } from '../components/TraceWaterfall'
import { formatPayloadToString } from '../components/SafePayloadViewer'
import { Span } from '../types'

describe('Data Transformations & Timeline Sorting', () => {
  it('sorts spans deterministically by sequence number and timestamp', () => {
    const rawSpans: Span[] = [
      {
        id: 'span-3',
        run_id: 'r1',
        sequence_number: 3,
        parent_span_id: null,
        policy_version_id: 'v1',
        span_type: 'tool',
        name: 'write_db',
        input_payload: {},
        output_payload: {},
        started_at: '2026-10-17T10:00:05.000Z',
        ended_at: '2026-10-17T10:00:05.100Z',
        latency_ms: 100,
        token_counts: {},
        error: null,
        redaction_count: 0,
        policy_decision: 'allow',
        policy_rule_id: 'allow_db',
      },
      {
        id: 'span-1',
        run_id: 'r1',
        sequence_number: 1,
        parent_span_id: null,
        policy_version_id: 'v1',
        span_type: 'model',
        name: 'gpt-4o',
        input_payload: {},
        output_payload: {},
        started_at: '2026-10-17T10:00:00.000Z',
        ended_at: '2026-10-17T10:00:02.000Z',
        latency_ms: 2000,
        token_counts: {},
        error: null,
        redaction_count: 0,
        policy_decision: 'bypassed',
        policy_rule_id: null,
      },
      {
        id: 'span-2',
        run_id: 'r1',
        sequence_number: 2,
        parent_span_id: null,
        policy_version_id: 'v1',
        span_type: 'tool',
        name: 'fetch_data',
        input_payload: {},
        output_payload: {},
        started_at: '2026-10-17T10:00:02.500Z',
        ended_at: '2026-10-17T10:00:03.000Z',
        latency_ms: 500,
        token_counts: {},
        error: null,
        redaction_count: 0,
        policy_decision: 'allow',
        policy_rule_id: 'allow_fetch',
      },
    ]

    const sorted = sortSpansDeterministically(rawSpans)
    expect(sorted.map((s) => s.id)).toEqual(['span-1', 'span-2', 'span-3'])
    expect(sorted.map((s) => s.sequence_number)).toEqual([1, 2, 3])
  })

  it('calculates timeline bounds and duration correctly', () => {
    const spans: Span[] = [
      {
        id: 's1',
        run_id: 'r1',
        sequence_number: 1,
        parent_span_id: null,
        policy_version_id: 'v1',
        span_type: 'model',
        name: 'model_call',
        input_payload: {},
        output_payload: {},
        started_at: '2026-10-17T12:00:00.000Z',
        ended_at: '2026-10-17T12:00:01.000Z',
        latency_ms: 1000,
        token_counts: {},
        error: null,
        redaction_count: 0,
        policy_decision: 'allow',
        policy_rule_id: null,
      },
      {
        id: 's2',
        run_id: 'r1',
        sequence_number: 2,
        parent_span_id: null,
        policy_version_id: 'v1',
        span_type: 'tool',
        name: 'tool_call',
        input_payload: {},
        output_payload: {},
        started_at: '2026-10-17T12:00:02.000Z',
        ended_at: '2026-10-17T12:00:03.500Z',
        latency_ms: 1500,
        token_counts: {},
        error: null,
        redaction_count: 0,
        policy_decision: 'allow',
        policy_rule_id: null,
      },
    ]

    const bounds = calculateTimelineBounds(spans)
    expect(bounds.minStartTime).toBe(new Date('2026-10-17T12:00:00.000Z').getTime())
    expect(bounds.maxEndTime).toBe(new Date('2026-10-17T12:00:03.500Z').getTime())
    expect(bounds.totalDurationMs).toBe(3500)
  })

  it('formats various payload types into clean string representations', () => {
    expect(formatPayloadToString(null)).toBe('null')
    expect(formatPayloadToString(undefined)).toBe('null')
    expect(formatPayloadToString('raw plain string')).toBe('raw plain string')
    expect(formatPayloadToString({ a: 1, b: 'two' })).toBe('{\n  "a": 1,\n  "b": "two"\n}')
    expect(formatPayloadToString([1, 2, 3])).toBe('[\n  1,\n  2,\n  3\n]')
  })
})
