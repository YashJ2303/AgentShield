import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { ApprovalsQueue } from '../components/ApprovalsQueue'
import * as api from '../services/api'
import { ApprovalItem } from '../types'

describe('ApprovalsQueue Component', () => {
  const mockApprovals: ApprovalItem[] = [
    {
      id: 'app-1',
      run_id: 'run-12345',
      span_id: 'span-1',
      tool_name: 'wire_transfer',
      tool_args: {
        account: 'AC-1002',
        amount: 5000,
        notes: "<script>alert('xss_attack')</script><img src=x onerror=alert(1)>",
      },
      call_hash: 'a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890',
      status: 'pending',
      timeout_seconds: 60,
      remaining_seconds: 45,
      requested_at: new Date().toISOString(),
      decided_at: null,
      decision_reason: null,
      decided_by: null,
      is_consumed: false,
    },
    {
      id: 'app-2',
      run_id: 'run-67890',
      span_id: null,
      tool_name: 'delete_database',
      tool_args: { db_name: 'production_analytics' },
      call_hash: 'b2c3d4e5f6a17890abcdef1234567890abcdef1234567890abcdef1234567890',
      status: 'rejected',
      timeout_seconds: 30,
      remaining_seconds: 0,
      requested_at: new Date(Date.now() - 60000).toISOString(),
      decided_at: new Date(Date.now() - 30000).toISOString(),
      decision_reason: 'Destructive deletion denied by policy operator',
      decided_by: 'secops_lead',
      is_consumed: false,
    },
  ]

  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'fetchApprovals').mockResolvedValue(mockApprovals)
  })

  it('renders approval cards with tool names, countdown timers, and plain-text arguments', async () => {
    const onOpenTokenModal = vi.fn()
    const { container } = render(
      <ApprovalsQueue onOpenTokenModal={onOpenTokenModal} tokenConfigured={true} />
    )

    await waitFor(() => {
      expect(screen.getByText('wire_transfer')).toBeInTheDocument()
    })

    // Assert countdown timer displays
    expect(screen.getByTestId('countdown-app-1')).toHaveTextContent('45s remaining')

    // Assert call hash signature is displayed
    expect(screen.getByText(/a1b2c3d4e5f67890/)).toBeInTheDocument()

    // Assert plain-text rendering immunity: zero DOM script or img elements created
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    const payloadElements = screen.getAllByTestId('safe-payload-content')
    expect(payloadElements[0]).toHaveTextContent("<script>alert('xss_attack')</script>")
  })

  it('prompts to open token modal when admin token is not configured', async () => {
    const onOpenTokenModal = vi.fn()
    render(<ApprovalsQueue onOpenTokenModal={onOpenTokenModal} tokenConfigured={false} />)

    await waitFor(() => {
      expect(screen.getByTestId('token-missing-banner')).toBeInTheDocument()
    })

    const setTokenBtn = screen.getByTestId('btn-set-token-banner')
    fireEvent.click(setTokenBtn)
    expect(onOpenTokenModal).toHaveBeenCalledTimes(1)
  })

  it('calls decideApproval with approve action when approve button is clicked', async () => {
    const decideSpy = vi.spyOn(api, 'decideApproval').mockResolvedValue({ status: 'approved' })
    const onOpenTokenModal = vi.fn()

    render(<ApprovalsQueue onOpenTokenModal={onOpenTokenModal} tokenConfigured={true} />)

    await waitFor(() => {
      expect(screen.getByTestId('btn-approve-app-1')).toBeInTheDocument()
    })

    const approveBtn = screen.getByTestId('btn-approve-app-1')
    fireEvent.click(approveBtn)

    await waitFor(() => {
      expect(decideSpy).toHaveBeenCalledWith('app-1', 'approve', 'Approved by operator', 'dashboard_admin')
    })
  })

  it('calls decideApproval with reject action and custom reason', async () => {
    const decideSpy = vi.spyOn(api, 'decideApproval').mockResolvedValue({ status: 'rejected' })
    const onOpenTokenModal = vi.fn()

    render(<ApprovalsQueue onOpenTokenModal={onOpenTokenModal} tokenConfigured={true} />)

    await waitFor(() => {
      expect(screen.getByTestId('btn-reject-app-1')).toBeInTheDocument()
    })

    const reasonInput = screen.getByTestId('input-reason-app-1')
    fireEvent.change(reasonInput, { target: { value: 'Amount exceeds single-day limit' } })

    const rejectBtn = screen.getByTestId('btn-reject-app-1')
    fireEvent.click(rejectBtn)

    await waitFor(() => {
      expect(decideSpy).toHaveBeenCalledWith(
        'app-1',
        'reject',
        'Amount exceeds single-day limit',
        'dashboard_admin'
      )
    })
  })
})
