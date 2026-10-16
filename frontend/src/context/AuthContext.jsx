/**
 * src/context/AuthContext.jsx
 *
 * Provides authentication state across the application.
 * Manages the JWT, user profile, and exposes login/register/logout helpers.
 *
 * On mount, validates any stored token against GET /auth/me so stale
 * or expired tokens are cleared before the first render.
 */

import { createContext, useContext, useState, useCallback, useEffect } from 'react'

const AuthContext = createContext(null)

const STORAGE_KEY = 'recalce_token'
const USER_KEY    = 'recalce_user'

const BASE = (() => {
  const raw = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
  return raw.endsWith('/api/v1') ? raw : `${raw.replace(/\/+$/, '')}/api/v1`
})()

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY))
  const [user, setUser]   = useState(() => {
    try {
      const raw = localStorage.getItem(USER_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })
  // Start loading=true so we can validate the stored token before rendering routes
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const persist = useCallback((tok, usr) => {
    setToken(tok)
    setUser(usr)
    if (tok) {
      localStorage.setItem(STORAGE_KEY, tok)
      localStorage.setItem(USER_KEY, JSON.stringify(usr))
    } else {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem(USER_KEY)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // On mount: validate any stored token by calling /auth/me.
  // If the token is expired or revoked the backend returns 401 → clear session.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const storedToken = localStorage.getItem(STORAGE_KEY)
    if (!storedToken) {
      setLoading(false)
      return
    }

    fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${storedToken}` },
    })
      .then(async (res) => {
        if (res.ok) {
          const freshUser = await res.json()
          // Refresh the stored user profile in case it changed server-side
          persist(storedToken, freshUser)
        } else {
          // Token is invalid / expired — clear session
          persist(null, null)
        }
      })
      .catch(() => {
        // Network error (backend down) — keep stored session so UX isn't
        // destroyed by a transient outage, but don't block rendering.
        // The first real API call will fail with a meaningful error.
      })
      .finally(() => {
        setLoading(false)
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])   // run once on mount only

  // ---------------------------------------------------------------------------
  // Login
  // ---------------------------------------------------------------------------
  const login = useCallback(async (email, password) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${BASE}/auth/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Invalid email or password.')
      }
      const data = await res.json()
      persist(data.access_token, data.user)
      return data.user
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [persist])

  // ---------------------------------------------------------------------------
  // Register Org (creates Org + first Admin, then auto-logs in)
  // ---------------------------------------------------------------------------
  const registerOrg = useCallback(async ({ orgName, adminName, adminEmail, password }) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${BASE}/auth/register-org`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          org_name:    orgName,
          admin_name:  adminName,
          admin_email: adminEmail,
          password,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Organization registration failed.')
      }
      const data = await res.json()
      persist(data.access_token, data.user)
      return data.user
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [persist])

  // loginAsDemo is an alias for login — both use the same credential flow.
  const loginAsDemo = useCallback(async (email, password) => {
    return login(email, password)
  }, [login])

  const logout = useCallback(() => {
    persist(null, null)
  }, [persist])

  const clearError = useCallback(() => setError(null), [])

  const value = {
    token,
    user,
    loading,
    error,
    isAuthenticated: Boolean(token && user),
    role: user?.role ?? null,
    login,
    registerOrg,
    loginAsDemo,
    logout,
    clearError,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
