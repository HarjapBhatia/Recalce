import styles from './SummaryCards.module.css'

function formatCurrency(val) {
  if (val == null) return '$0.00'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val)
}

function formatCount(n) {
  if (n == null) return '0'
  return n.toLocaleString('en-US')
}

export default function SummaryCards({ summary }) {
  if (!summary) {
    // Skeleton state
    return (
      <section className={styles.grid}>
        <div className={`card ${styles.card}`}>
          <div className={styles.skeleton} />
        </div>
        <div className={`card ${styles.card}`}>
          <div className={styles.skeleton} />
        </div>
      </section>
    )
  }

  const {
    total_internal,
    exact_matches,
    date_shift_matches,
    fee_adjusted_matches,
    unreconciled_internal,
    unreconciled_bank,
    anomalies_flagged,
    total_bank,
  } = summary

  const totalMatched = exact_matches + date_shift_matches + fee_adjusted_matches
  const totalUnreconciled = unreconciled_internal + unreconciled_bank
  const totalRecords = total_internal + total_bank

  // Compute totals for reconciliation check card
  // These come from the results if available; we'll compute approximates from summary
  const matchedPct = totalRecords > 0 ? Math.round((totalMatched / total_internal) * 100) : 0

  return (
    <section className={styles.grid}>
      {/* Batch Summary Card */}
      <div className={`card ${styles.card}`}>
        <h3 className={styles.cardTitle}>
          <span className="material-symbols-outlined" style={{ color: 'var(--secondary)', fontSize: '20px' }}>pie_chart</span>
          Batch Summary
        </h3>
        <div className={styles.statsGrid}>
          <div className={styles.statCell}>
            <span className={styles.statLabel}>Total Records</span>
            <span className={styles.statValue}>{formatCount(total_internal)}</span>
          </div>
          <div className={`${styles.statCell} ${styles.borderAccentNeutral}`}>
            <span className={styles.statLabel}>Matched</span>
            <span className={styles.statValue}>{formatCount(totalMatched)}</span>
          </div>
          <div className={`${styles.statCell} ${styles.borderAccentError}`}>
            <span className={styles.statLabel}>Unreconciled</span>
            <span className={`${styles.statValue} ${styles.errorText}`}>{formatCount(totalUnreconciled)}</span>
          </div>
          <div className={`${styles.statCell} ${styles.borderAccentWarning}`}>
            <span className={styles.statLabel}>Anomalies</span>
            <span className={`${styles.statValue} ${styles.warningText}`}>{formatCount(anomalies_flagged)}</span>
          </div>
        </div>
      </div>

      {/* Reconciliation Check Card */}
      <div className={`card ${styles.card} ${styles.checkCard}`}>
        <h3 className={styles.cardTitle}>
          <span className="material-symbols-outlined" style={{ color: 'var(--secondary)', fontSize: '20px' }}>verified</span>
          Reconciliation Check
        </h3>
        <div className={styles.checkRows}>
          <div className={styles.checkRow}>
            <span className={styles.checkLabel}>Ledger Records</span>
            <span className={styles.checkValue}>{formatCount(total_internal)}</span>
          </div>
          <div className={styles.checkRow}>
            <span className={styles.checkLabel}>Bank Records</span>
            <span className={styles.checkValue}>{formatCount(total_bank)}</span>
          </div>
          <div className={`${styles.checkRow} ${styles.checkRowBold}`}>
            <span className={styles.checkLabelBold}>Matched Pairs</span>
            <span className={styles.checkValueBold}>{formatCount(totalMatched)}</span>
          </div>
        </div>
        {totalUnreconciled === 0 ? (
          <div className={styles.balanceBadge}>
            <span className="material-symbols-outlined" style={{ color: '#2e7d32', fontVariationSettings: "'FILL' 1", fontSize: '20px' }}>check_circle</span>
            <span className={styles.balanceText}>Equation Balances Perfectly</span>
          </div>
        ) : (
          <div className={styles.warnBadge}>
            <span className="material-symbols-outlined" style={{ color: '#b45309', fontVariationSettings: "'FILL' 1", fontSize: '20px' }}>warning</span>
            <span className={styles.warnText}>{formatCount(totalUnreconciled)} unreconciled record{totalUnreconciled !== 1 ? 's' : ''} require review</span>
          </div>
        )}
      </div>
    </section>
  )
}
