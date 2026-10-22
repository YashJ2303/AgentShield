import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CommandPalette } from '../components/CommandPalette'

describe('Enterprise SOC Navigation & Command Palette', () => {
  describe('Command Palette (Ctrl+K)', () => {
    it('renders search input and allows navigating tabs', () => {
      const mockSelectTab = vi.fn()
      const mockClose = vi.fn()

      render(
        <CommandPalette
          isOpen={true}
          onClose={mockClose}
          onSelectTab={mockSelectTab}
        />
      )

      expect(screen.getByTestId('command-palette-modal')).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/Type a command/i)).toBeInTheDocument()

      const cmdCenterItem = screen.getByTestId('palette-item-nav-command-center')
      fireEvent.click(cmdCenterItem)
      expect(mockSelectTab).toHaveBeenCalledWith('command_center')
      expect(mockClose).toHaveBeenCalled()
    })

    it('filters commands on search input', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={vi.fn()}
          onSelectTab={vi.fn()}
        />
      )

      const input = screen.getByTestId('palette-search-input')
      fireEvent.change(input, { target: { value: 'Playground' } })

      expect(screen.getByText('Policy Playground')).toBeInTheDocument()
      expect(screen.queryByText('Approvals Queue')).not.toBeInTheDocument()
    })
  })
})
