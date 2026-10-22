import { describe, it, expect, beforeEach } from 'vitest'
import { setAdminToken, getAdminToken, hasAdminToken } from '../services/api'

describe('Admin Token In-Memory Isolation', () => {
  beforeEach(() => {
    setAdminToken('')
  })

  it('keeps the admin token strictly in-memory and never writes to browser storage', () => {
    expect(hasAdminToken()).toBe(false)
    expect(getAdminToken()).toBe('')

    const secret = 'super-secret-admin-token-12345'
    setAdminToken(secret)

    expect(hasAdminToken()).toBe(true)
    expect(getAdminToken()).toBe(secret)

    // Verify localStorage and sessionStorage were NEVER touched
    expect(window.localStorage.getItem('admin_token')).toBeNull()
    expect(window.sessionStorage.getItem('admin_token')).toBeNull()
  })

  it('clears token cleanly on reset', () => {
    setAdminToken('temp-token')
    expect(hasAdminToken()).toBe(true)

    setAdminToken('')
    expect(hasAdminToken()).toBe(false)
    expect(getAdminToken()).toBe('')
  })
})
