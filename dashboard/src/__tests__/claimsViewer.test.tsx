import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ClaimsViewer } from '../components/ClaimsViewer'
import * as api from '../services/api'

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api')
  return {
    ...actual,
    fetchEvalFile: vi.fn().mockImplementation((filename: string) => {
      if (filename === 'CLAIMS.md') {
        return Promise.resolve({
          filename: 'CLAIMS.md',
          content: `# Audited Claims\n<script>alert('xss-attempt')</script>\n<img src=x onerror=alert('img-xss') />\n<div id="malicious-injected-element">Injected payload</div>\nNormal text.`,
          size_bytes: 140,
        })
      }
      return Promise.resolve({
        filename: 'KNOWN_LIMITATIONS.md',
        content: `# Limitations\n<img src=x onerror=alert('xss') />\n1. AST recursion limit.`,
        size_bytes: 100,
      })
    }),
  }
})

describe('ClaimsViewer Component HTML Escaping & Safe Preformatted Rendering', () => {
  it('renders markdown content strictly as preformatted plain text and prevents HTML element injection', async () => {
    const { container } = render(<ClaimsViewer />)

    // Wait for the preformatted block to be rendered
    const preElement = await screen.findByTestId('claims-preformatted-content')
    expect(preElement).toBeInTheDocument()

    // Verify that literal script, img, and div tags appear as plain text inside the pre element
    expect(preElement.textContent).toContain("<script>alert('xss-attempt')</script>")
    expect(preElement.textContent).toContain("<img src=x onerror=alert('img-xss') />")
    expect(preElement.textContent).toContain('<div id="malicious-injected-element">Injected payload</div>')

    // CRITICAL SECURITY ASSERTION: Confirm that the HTML was NOT parsed into DOM nodes
    // No script or img element exists in the DOM
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()

    // No div with id "malicious-injected-element" was created as a DOM element
    expect(container.querySelector('#malicious-injected-element')).toBeNull()
    expect(document.getElementById('malicious-injected-element')).toBeNull()
  })
})
