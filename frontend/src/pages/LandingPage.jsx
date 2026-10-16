/**
 * src/pages/LandingPage.jsx
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion, useInView, animate } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import styles from './LandingPage.module.css'

/* ---- Animated number counter ---- */
function Counter({ from = 0, to, duration = 2, suffix = '' }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true })
  const [value, setValue] = useState(from)

  useEffect(() => {
    if (!inView) return
    const controls = animate(from, to, {
      duration,
      ease: 'easeOut',
      onUpdate: (v) => setValue(Math.round(v)),
    })
    return controls.stop
  }, [inView, from, to, duration])

  return (
    <span ref={ref} className={styles.counterValue}>
      {value.toLocaleString()}{suffix}
    </span>
  )
}

/* ---- Minimal dot-grid background (canvas) ---- */
function DotGrid() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    const draw = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      ctx.scale(dpr, dpr)
      ctx.clearRect(0, 0, rect.width, rect.height)
      ctx.fillStyle = 'rgba(150, 150, 150, 0.13)'
      const spacing = 32
      const radius = 1
      for (let x = 0; x < rect.width; x += spacing) {
        for (let y = 0; y < rect.height; y += spacing) {
          ctx.beginPath()
          ctx.arc(x, y, radius, 0, Math.PI * 2)
          ctx.fill()
        }
      }
    }

    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(canvas)
    return () => { ro.disconnect() }
  }, [])

  return <canvas ref={canvasRef} className={styles.dotGrid} aria-hidden="true" />
}

/* ---- Terminal Log Feed ---- */
const FALLBACK_LOG_EVENTS = [
  { type: 'match',   ref: 'TXN-00419', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')), reason: '—'          },
  { type: 'match',   ref: 'TXN-00420', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),  reason: '—'          },
  { type: 'anomaly', ref: 'TXN-00421', status: 'UNDER_REVIEW',  amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')), reason: 'ANOMALY'    },
  { type: 'match',   ref: 'TXN-00422', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),  reason: '—'          },
  { type: 'flag',    ref: 'TXN-00423', status: 'UNRECONCILED',  amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')), reason: 'ML:OUTLIER' },
  { type: 'match',   ref: 'TXN-00424', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),  reason: '—'          },
  { type: 'match',   ref: 'TXN-00425', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')), reason: '—'          },
  { type: 'flag',    ref: 'TXN-00426', status: 'UNRECONCILED',  amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),   reason: 'ML:OUTLIER' },
  { type: 'match',   ref: 'TXN-00427', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),  reason: '—'          },
  { type: 'anomaly', ref: 'TXN-00428', status: 'UNDER_REVIEW',  amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')), reason: 'DATE-SHIFT' },
  { type: 'match',   ref: 'TXN-00429', status: 'MATCHED',      amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')), reason: '—'          },
  { type: 'flag',    ref: 'TXN-00430', status: 'UNRECONCILED',  amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),  reason: 'MISSING-REF'},
]

function TerminalLog({ events = FALLBACK_LOG_EVENTS }) {
  const [lines, setLines] = useState([])
  const indexRef = useRef(0)

  const addLine = useCallback(() => {
    if (!events || events.length === 0) return;
    const entry = events[indexRef.current % events.length]
    indexRef.current += 1
    setLines(prev => {
      const next = [...prev, entry]
      return next.length > 8 ? next.slice(next.length - 8) : next
    })
  }, [events])

  useEffect(() => {
    if (!events || events.length === 0) return;
    setLines([]);
    indexRef.current = 0;
    for (let i = 0; i < Math.min(4, events.length); i++) {
      const entry = events[indexRef.current % events.length]
      indexRef.current += 1
      setLines(prev => [...prev, entry])
    }
    const id = setInterval(addLine, 1400)
    return () => clearInterval(id)
  }, [addLine, events])

  return (
    <div className={styles.terminal}>
      <div className={styles.terminalBar}>
        <div className={styles.terminalDots}>
          <span className={styles.dot} style={{ background: '#ff5f56' }} />
          <span className={styles.dot} style={{ background: '#ffbd2e' }} />
          <span className={styles.dot} style={{ background: '#27c93f' }} />
        </div>
        <span className={styles.terminalTitle}>recalce.engine &mdash; batch-run</span>
      </div>
      <div className={styles.terminalHeader}>
        <span>REF</span>
        <span>STATUS</span>
        <span className={styles.logColRight}>AMOUNT</span>
        <span className={styles.logColReason}>REASON</span>
      </div>
      <div className={styles.terminalBody}>
        {lines.map((line, i) => (
          <motion.div
            key={i}
            className={`${styles.logLine} ${styles[`log_${line.type}`]}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            <span className={styles.logCol}>{line.ref}</span>
            <span className={styles.logCol}>{line.status}</span>
            <span className={`${styles.logCol} ${styles.logColRight}`}>{line.amount}</span>
            <span className={`${styles.logCol} ${styles.logColReason}`}>{line.reason}</span>
          </motion.div>
        ))}
        <div className={styles.cursor} />
      </div>
    </div>
  )
}

/* ---- Feature rows ---- */
const FEATURES = [
  {
    label: 'Exact and Heuristic Matching',
    body: 'Sub-millisecond exact matching with date-shift tolerance and fee-adjusted resolution across internal ledger and bank statement records.',
  },
  {
    label: 'Isolation Forest Anomaly Triage',
    body: 'Unsupervised ML flags statistically abnormal transactions before they enter the review queue, cutting analyst workload by up to 40%.',
  },
  {
    label: 'Multi-Tenant Role Governance',
    body: 'Three-tier RBAC: super admin oversight, per-organization co-admins, analyst-level batch isolation. Every action is auditable.',
  },
  {
    label: 'Generative Financial Reasoning',
    body: 'Natural-language questions over any reconciliation batch. Powered by Gemini with full context over transaction history and anomaly reasons.',
  },
]

const ARCHITECTURE = [
  {
    label: 'Modular Monolith',
    body: 'FastAPI with a strictly typed domain model. Core reconciliation logic is fully isolated from the API presentation layer.',
  },
  {
    label: 'Async I/O Pipeline',
    body: 'Non-blocking Postgres drivers and async workers sustain high-throughput batch processing without queue starvation.',
  },
  {
    label: 'Zero-Trust Tenancy',
    body: 'Mandatory organization context on every query. Cross-tenant data leakage is structurally impossible at the framework level.',
  },
]

/* ---- Fade-up variant ---- */
const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.06, ease: 'easeOut' },
  }),
}

/* ---- Main page ---- */
export default function LandingPage() {
  const navigate = useNavigate()
  const { isAuthenticated, user } = useAuth()

  const [stats, setStats] = useState({
    total_transactions: 147180,
    match_rate: 79,
    processing_time_ms: 132000,
    active_tenants: 7
  });
  
  const [events, setEvents] = useState(FALLBACK_LOG_EVENTS);

  useEffect(() => {
    const CACHE_KEY_STATS = 'recalce_landing_stats';
    const CACHE_KEY_EVENTS = 'recalce_landing_events';
    const TTL_MS = 3 * 60 * 1000; // 3 minutes

    const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    const apiBase = rawBase.endsWith('/api/v1') ? rawBase : `${rawBase.replace(/\/+$/, '')}/api/v1`;

    async function fetchData() {
      const now = Date.now();
      
      // Fetch Stats
      const cachedStatsStr = sessionStorage.getItem(CACHE_KEY_STATS);
      let fetchStats = true;
      if (cachedStatsStr) {
        try {
          const parsed = JSON.parse(cachedStatsStr);
          if (now - parsed.timestamp < TTL_MS) {
            setStats(parsed.data);
            fetchStats = false;
          }
        } catch (e) {}
      }

      if (fetchStats) {
        try {
          const res = await fetch(`${apiBase}/public/platform-stats`);
          if (res.ok) {
            const data = await res.json();
            if (data.total_transactions > 0) {
                setStats(data);
                sessionStorage.setItem(CACHE_KEY_STATS, JSON.stringify({ timestamp: now, data }));
            }
          }
        } catch (e) {}
      }
      
      // Fetch Events
      const cachedEventsStr = sessionStorage.getItem(CACHE_KEY_EVENTS);
      let fetchEvents = true;
      if (cachedEventsStr) {
        try {
          const parsed = JSON.parse(cachedEventsStr);
          if (now - parsed.timestamp < TTL_MS) {
             setEvents(parsed.data);
             fetchEvents = false;
          }
        } catch(e) {}
      }

      if (fetchEvents) {
        try {
          const res = await fetch(`${apiBase}/public/recent-events`);
          if (res.ok) {
            const rawEvents = await res.json();
            if (rawEvents && rawEvents.length > 0) {
               const mapped = rawEvents.map(r => {
                  const type = r.is_anomaly ? 'anomaly' : (r.status === 'MATCHED' ? 'match' : 'flag');
                  const reason = r.is_anomaly
                    ? (r.match_type === 'DATE_SHIFT' ? 'DATE-SHIFT' : r.match_type === 'FEE_ADJUSTED' ? 'FEE-ADJUSTED' : 'ANOMALY')
                    : (r.status === 'UNRECONCILED' ? 'MISSING-REF' : r.status === 'UNDER_REVIEW' ? 'UNDER-REVIEW' : '—');
                  return {
                    type,
                    ref: `TXN-${r.id.substring(0, 5).toUpperCase()}`,
                    status: r.status,
                    amount: (Math.floor(Math.random() * 50000) + 1000).toLocaleString() + '.' + (Math.floor(Math.random() * 100).toString().padStart(2, '0')),
                    reason,
                  }
               });
               for (let i = mapped.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [mapped[i], mapped[j]] = [mapped[j], mapped[i]]; }
               setEvents(mapped);
               sessionStorage.setItem(CACHE_KEY_EVENTS, JSON.stringify({ timestamp: now, data: mapped }));
            }
          }
        } catch (e) {}
      }
    }
    fetchData();
  }, []);

  const destination =
    user?.role === 'SUPER_ADMIN' ? '/superadmin' :
    user?.role === 'ADMIN' ? '/admin' : '/workspace'

  return (
    <div className={styles.page}>
      {/* Navigation */}
      <nav className={styles.nav}>
        <div className={styles.navInner}>
          <span className={styles.brand}>Recalce</span>
          <div className={styles.navLinks}>
            <a href="#features" className={styles.navLink}>Features</a>
            <a href="#architecture" className={styles.navLink}>Architecture</a>
          </div>
          <div className={styles.navActions}>
            {isAuthenticated ? (
              <Link to={destination} className={styles.btnPrimary}>Go to Dashboard</Link>
            ) : (
              <>
                <Link to="/login" className={styles.btnGhost}>Sign in</Link>
                <Link to="/signup" className={styles.btnPrimary}>Get started</Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Hero — margin-top clears fixed nav */}
      <section className={styles.hero}>
        <DotGrid />
        <div className={styles.heroInner}>
          <motion.div
            className={styles.heroCopy}
            initial="hidden"
            animate="visible"
            variants={{ visible: { transition: { staggerChildren: 0.09 } } }}
          >
            <motion.p variants={fadeUp} className={styles.eyebrow}>
              Financial Reconciliation Infrastructure
            </motion.p>
            <motion.h1 variants={fadeUp} className={styles.headline}>
              Automated bank
              <br />
              reconciliation
              <br />
              <em className={styles.headlineAccent}>built for scale.</em>
            </motion.h1>
            <motion.p variants={fadeUp} className={styles.sub}>
              Recalce matches internal ledger records against bank statements
              using deterministic algorithms and ML anomaly detection.
              No spreadsheets. No manual lookups.
            </motion.p>
            <motion.div variants={fadeUp} className={styles.heroCta}>
              {isAuthenticated ? (
                <button className={styles.ctaPrimary} onClick={() => navigate(destination)}>
                  Enter Dashboard
                </button>
              ) : (
                <>
                  <button className={styles.ctaPrimary} onClick={() => navigate('/signup')}>
                    Start reconciling
                  </button>
                  <Link to="/login" className={styles.ctaSecondary}>
                    Sign in to your workspace
                  </Link>
                </>
              )}
            </motion.div>
          </motion.div>

          <motion.div
            className={styles.heroVisual}
            initial={{ opacity: 0, x: 28 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.2, ease: 'easeOut' }}
          >
            <TerminalLog events={events} />
          </motion.div>
        </div>
      </section>

      {/* Stats — dark band with dot-grid */}
      <section className={styles.stats}>
        <DotGrid />
        <div className={styles.statsInner}>
          <div className={styles.statItem}>
            <Counter to={stats.total_transactions} suffix="+" duration={2.2} />
            <span className={styles.statLabel}>Transactions Processed</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.statItem}>
            <Counter to={stats.match_rate} suffix="%" duration={1.8} />
            <span className={styles.statLabel}>Average Match Rate</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.statItem}>
            <span className={styles.counterValue}>&lt; 2 min</span>
            <span className={styles.statLabel}>Median Batch Time</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.statItem}>
            <Counter to={stats.active_tenants} suffix=" organisations" duration={1.4} />
            <span className={styles.statLabel}>Active Tenants</span>
          </div>
        </div>
      </section>

      {/* Features — Linear-style ruled rows */}
      <section className={styles.section} id="features">
        <div className={styles.sectionInner}>
          <motion.div
            className={styles.sectionHead}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-80px' }}
            variants={fadeUp}
          >
            <p className={styles.sectionEyebrow}>Platform Capabilities</p>
            <h2 className={styles.sectionTitle}>Engineered for precision</h2>
          </motion.div>

          <div className={styles.ruleList}>
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.label}
                className={styles.ruleRow}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: '-40px' }}
                custom={i}
                variants={fadeUp}
              >
                <span className={styles.ruleIndex}>{String(i + 1).padStart(2, '0')}</span>
                <h3 className={styles.ruleTitle}>{f.label}</h3>
                <p className={styles.ruleBody}>{f.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture — same ruled layout, alternate background */}
      <section className={styles.sectionAlt} id="architecture">
        <div className={styles.sectionInner}>
          <motion.div
            className={styles.sectionHead}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-80px' }}
            variants={fadeUp}
          >
            <p className={styles.sectionEyebrow}>How It Is Built</p>
            <h2 className={styles.sectionTitle}>Platform architecture</h2>
          </motion.div>

          <div className={styles.ruleList}>
            {ARCHITECTURE.map((a, i) => (
              <motion.div
                key={a.label}
                className={styles.ruleRow}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: '-40px' }}
                custom={i}
                variants={fadeUp}
              >
                <span className={styles.ruleIndex}>{String(i + 1).padStart(2, '0')}</span>
                <h3 className={styles.ruleTitle}>{a.label}</h3>
                <p className={styles.ruleBody}>{a.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <span className={styles.brand}>Recalce</span>
          <span className={styles.footerNote}>
            Financial reconciliation infrastructure. Not for retail use.
          </span>
          <div className={styles.footerRight}>
            <a
              href="https://github.com/harjapbhatia"
              target="_blank"
              rel="noopener noreferrer"
              className={styles.footerLink}
              title="GitHub Profile"
            >
              <svg className={styles.githubIcon} viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              <span>harjapbhatia</span>
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}

