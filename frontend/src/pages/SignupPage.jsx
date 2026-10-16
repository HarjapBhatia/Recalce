/**
 * src/pages/SignupPage.jsx
 *
 * Organization registration page.
 * Creates Organization + Admin account and automatically signs in to /admin.
 */

import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import styles from './AuthPage.module.css'

export default function SignupPage() {
  const navigate = useNavigate()
  const { registerOrg, loading, error, clearError, isAuthenticated, user } = useAuth()
  const [localError, setLocalError] = useState(null)

  /* --- Org registration state --- */
  const [orgName, setOrgName] = useState('')
  const [adminName, setAdminName] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [orgPassword, setOrgPassword] = useState('')

  useEffect(() => {
    if (isAuthenticated && user) {
      if (user.role === 'SUPER_ADMIN') navigate('/superadmin', { replace: true })
      else if (user.role === 'ADMIN') navigate('/admin', { replace: true })
      else navigate('/workspace', { replace: true })
    }
  }, [isAuthenticated, user, navigate])

  async function handleOrgSubmit(e) {
    e.preventDefault()
    setLocalError(null)
    clearError()
    try {
      const loggedUser = await registerOrg({ orgName, adminName, adminEmail, password: orgPassword })
      if (loggedUser?.role === 'ADMIN') {
        navigate('/admin', { replace: true })
      } else {
        navigate('/workspace', { replace: true })
      }
    } catch (err) {
      setLocalError(err.message)
    }
  }

  const activeError = localError || error

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <div className={styles.leftInner}>
          <Link to="/" className={styles.backBrand}>Recalce</Link>
          <div className={styles.leftQuote}>
            <blockquote className={styles.quote}>
              "A reconciliation error is just a transaction waiting to be explained."
            </blockquote>
            <div className={styles.quoteStats}>
              <div className={styles.qStat}>
                <span className={styles.qVal}>3-tier</span>
                <span className={styles.qLabel}>Role hierarchy</span>
              </div>
              <div className={styles.qDivider} />
              <div className={styles.qStat}>
                <span className={styles.qVal}>Org-scoped</span>
                <span className={styles.qLabel}>Data isolation</span>
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
            <h1 className={styles.cardTitle}>Register Organization</h1>
            <p className={styles.cardSub}>
              Already have an account?{' '}
              <Link to="/login" className={styles.cardLink}>Sign in</Link>
            </p>
          </div>

          <form className={styles.form} onSubmit={handleOrgSubmit}>
            {activeError && (
              <div className={styles.errorAlert} role="alert">{activeError}</div>
            )}
            <div className={styles.field}>
              <label className={styles.label} htmlFor="orgName">Organization name</label>
              <input
                id="orgName"
                type="text"
                required
                className={styles.input}
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Apex Capital"
              />
            </div>
            <div className={styles.formRow}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="adminName">Your full name</label>
                <input
                  id="adminName"
                  type="text"
                  required
                  className={styles.input}
                  value={adminName}
                  onChange={(e) => setAdminName(e.target.value)}
                  placeholder="Sarah Chen"
                />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="adminEmail">Work email</label>
                <input
                  id="adminEmail"
                  type="email"
                  required
                  className={styles.input}
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  placeholder="admin@org.com"
                />
              </div>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="orgPassword">Password</label>
              <input
                id="orgPassword"
                type="password"
                required
                minLength={8}
                className={styles.input}
                value={orgPassword}
                onChange={(e) => setOrgPassword(e.target.value)}
                placeholder="Minimum 8 characters"
              />
            </div>
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? 'Creating organization...' : 'Create organization'}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  )
}
