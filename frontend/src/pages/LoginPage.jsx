/**
 * src/pages/LoginPage.jsx
 *
 * Clean authentication portal.
 * Quick persona switcher for development and evaluation.
 */

import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import styles from './AuthPage.module.css'

const DEMO_PERSONAS = [
  { label: 'Platform Admin',        email: 'superadmin@recalce.internal', password: 'Recalce@2026!', role: 'SUPER_ADMIN' },
  { label: 'Apex Capital (Admin 1)', email: 'admin1@apexcap.com',          password: 'Apex@2026!',    role: 'ADMIN' },
  { label: 'Apex Capital (Admin 2)', email: 'admin2@apexcap.com',          password: 'Apex@2026!',    role: 'ADMIN' },
  { label: 'Apex Analyst 1',         email: 'analyst1@apexcap.com',        password: 'Apex@2026!',    role: 'ANALYST' },
  { label: 'Meridian Admin',         email: 'admin@meridian.com',          password: 'Meridian@2026!', role: 'ADMIN' },
  { label: 'Meridian Analyst 4',     email: 'analyst4@meridian.com',       password: 'Meridian@2026!', role: 'ANALYST' },
]

const ROLE_REDIRECT = {
  SUPER_ADMIN: '/superadmin',
  ADMIN:       '/admin',
  ANALYST:     '/workspace',
}

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, loginAsDemo, loading, error, clearError, isAuthenticated, user } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [liveStats, setLiveStats] = useState({ match_rate: 79.0, processing_time_ms: 132000 })

  useEffect(() => {
    const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
    const apiBase = rawBase.endsWith('/api/v1') ? rawBase : `${rawBase.replace(/\/+$/, '')}/api/v1`

    fetch(`${apiBase}/public/platform-stats`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.match_rate > 0) {
          setLiveStats(data)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (isAuthenticated && user) {
      navigate(ROLE_REDIRECT[user.role] ?? '/workspace', { replace: true })
    }
  }, [isAuthenticated, user, navigate])

  async function handleSubmit(e) {
    e.preventDefault()
    clearError()
    try {
      const loggedUser = await login(email, password)
      navigate(ROLE_REDIRECT[loggedUser.role] ?? '/workspace', { replace: true })
    } catch {
      // error is already stored in AuthContext
    }
  }

  async function handleDemo(persona) {
    clearError()
    try {
      const loggedUser = await loginAsDemo(persona.email, persona.password)
      navigate(ROLE_REDIRECT[loggedUser.role] ?? '/workspace', { replace: true })
    } catch {
      // error is already stored in AuthContext
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <div className={styles.leftInner}>
          <Link to="/" className={styles.backBrand}>Recalce</Link>
          <div className={styles.leftQuote}>
            <blockquote className={styles.quote}>
              "Reconciliation is the final word in any financial close."
            </blockquote>
            <div className={styles.quoteStats}>
              <div className={styles.qStat}>
                <span className={styles.qVal}>{Math.round(liveStats.match_rate)}%</span>
                <span className={styles.qLabel}>Match accuracy</span>
              </div>
              <div className={styles.qDivider} />
              <div className={styles.qStat}>
                <span className={styles.qVal}>
                  {liveStats.processing_time_ms >= 1000
                    ? `${(liveStats.processing_time_ms / 1000).toFixed(0)}s`
                    : `${liveStats.processing_time_ms}ms`}
                </span>
                <span className={styles.qLabel}>Median batch runtime</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className={styles.right}>
        <motion.div
          className={styles.card}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        >
          <div className={styles.cardHead}>
            <h1 className={styles.cardTitle}>Sign in</h1>
            <p className={styles.cardSub}>
              Don't have an account?{' '}
              <Link to="/signup" className={styles.cardLink}>Register your organization</Link>
            </p>
          </div>

          <form className={styles.form} onSubmit={handleSubmit}>
            {error && (
              <div className={styles.errorAlert} role="alert">
                {error}
              </div>
            )}
            <div className={styles.field}>
              <label className={styles.label} htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                className={styles.input}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@organization.com"
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                className={styles.input}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
              />
            </div>
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <div className={styles.divider}>
            <span className={styles.dividerLabel}>Or continue as</span>
          </div>

          <div className={styles.personaGrid}>
            {DEMO_PERSONAS.map((p) => (
              <button
                key={p.email}
                className={styles.personaBtn}
                onClick={() => handleDemo(p)}
                disabled={loading}
              >
                <span className={styles.personaLabel}>{p.label}</span>
                <span className={styles.personaRole}>{p.role}</span>
              </button>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
