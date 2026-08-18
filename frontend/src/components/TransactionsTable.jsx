import { useState, Fragment } from 'react'
import styles from './TransactionsTable.module.css'

// ── Tabs config ───────────────────────────────────────────────────────────────
const TABS = [
  { id: 'all',          label: 'All Transactions' },
  { id: 'matched',      label: 'Matched'          },
  { id: 'unreconciled', label: 'Unreconciled'     },
  { id: 'under_review', label: 'Under Review'     },
  { id: 'anomalies',    label: 'Anomalies'        },
]

// ── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status, isAnomaly }) {
  if (isAnomaly) {
    return (
      <span className={`${styles.badge} ${styles.anomalyBadge}`}>
        <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>warning</span>
        Anomaly
      </span>
    )
  }
  switch (status) {
    case 'MATCHED':
      return <span className={`${styles.badge} ${styles.matchedBadge}`}>Matched</span>
    case 'UNRECONCILED':
      return <span className={`${styles.badge} ${styles.unreconciledBadge}`}>Unreconciled</span>
    case 'UNDER_REVIEW':
      return <span className={`${styles.badge} ${styles.reviewBadge}`}>Under Review</span>
    default:
      return <span className={`${styles.badge} ${styles.neutralBadge}`}>{status}</span>
  }
}

// ── Format helpers ────────────────────────────────────────────────────────────
function fmtDate(val) {
  if (!val) return '-'
  const d = new Date(val)
  if (isNaN(d)) return val
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtAmount(val) {
  if (val == null) return '-'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val)
}

function matchTypeLabel(t) {
  switch (t) {
    case 'EXACT':        return 'Exact Match'
    case 'DATE_SHIFT':   return 'Date Shift'
    case 'FEE_ADJUSTED': return 'Fee Adjusted'
    case 'MANY_TO_ONE':  return 'Many to One'
    case 'UNRECONCILED': return 'None'
    default: return t || '-'
  }
}

// ── CSV export helper ─────────────────────────────────────────────────────────
// NOTE: Exports the current page only; full-dataset export would require a
// dedicated backend endpoint.
function exportToCsv(rows, tabLabel) {
  const headers = ['Date', 'Reference', 'Merchant', 'Match Type', 'Status', 'Amount', 'Fee', 'Anomaly', 'Anomaly Reason']
  const csvRows = [headers.join(',')]
  for (const row of rows) {
    const cells = [
      fmtDate(row.internal_timestamp || row.settlement_date),
      row.is_group ? `Group (${row.member_count} items)` : (row.internal_transaction_id || row.bank_reference_id || ''),
      row.merchant_id || '',
      matchTypeLabel(row.match_type),
      row.status,
      row.is_group ? row.deposit_amount : (row.internal_amount || row.deposit_amount || ''),
      row.fee_deducted || '0',
      row.is_anomaly ? 'Yes' : 'No',
      row.anomaly_reason ? `"${row.anomaly_reason.replace(/"/g, '""')}"` : '',
    ]
    csvRows.push(cells.join(','))
  }
  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `recalce_${tabLabel.toLowerCase().replace(/\s+/g, '_')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Pagination ────────────────────────────────────────────────────────────────
function Pagination({ page, totalPages, total, pageSize, onPage }) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end   = Math.min(page * pageSize, total)

  function pages() {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1)
    const result = []
    if (page <= 4) {
      for (let i = 1; i <= 5; i++) result.push(i)
      result.push('...')
      result.push(totalPages)
    } else if (page >= totalPages - 3) {
      result.push(1)
      result.push('...')
      for (let i = totalPages - 4; i <= totalPages; i++) result.push(i)
    } else {
      result.push(1)
      result.push('...')
      for (let i = page - 1; i <= page + 1; i++) result.push(i)
      result.push('...')
      result.push(totalPages)
    }
    return result
  }

  return (
    <div className={styles.pagination}>
      <span className={styles.paginationInfo}>
        {total === 0
          ? 'No entries'
          : `Showing ${start} to ${end} of ${total.toLocaleString()} entries`}
      </span>
      <div className={styles.paginationBtns}>
        <button
          className={styles.pageBtn}
          disabled={page === 1}
          onClick={() => onPage(page - 1)}
          id="pagination-prev"
          aria-label="Previous page"
        >
          <span className="material-symbols-outlined" style={{ fontSize: '20px' }}>chevron_left</span>
        </button>
        {pages().map((p, i) =>
          p === '...' ? (
            <span key={`ellipsis-${i}`} className={styles.ellipsis}>...</span>
          ) : (
            <button
              key={p}
              id={`pagination-page-${p}`}
              className={`${styles.pageBtn} ${p === page ? styles.activePage : ''}`}
              onClick={() => onPage(p)}
            >
              {p}
            </button>
          )
        )}
        <button
          className={styles.pageBtn}
          disabled={page === totalPages || totalPages === 0}
          onClick={() => onPage(page + 1)}
          id="pagination-next"
          aria-label="Next page"
        >
          <span className="material-symbols-outlined" style={{ fontSize: '20px' }}>chevron_right</span>
        </button>
      </div>
    </div>
  )
}

// ── Inline review panel (inside expanded row) ─────────────────────────────────
function SkeletonCell({ className, width, align = 'left' }) {
  return (
    <td className={className}>
      <span
        className={styles.skeletonLine}
        style={{
          width,
          marginLeft: align === 'right' ? 'auto' : undefined,
          marginRight: align === 'center' ? 'auto' : undefined,
        }}
      />
    </td>
  )
}

function SkeletonRow() {
  return (
    <tr className={styles.skeletonRow} aria-hidden="true">
      <SkeletonCell className={styles.td} width="72%" />
      <SkeletonCell className={`${styles.td} ${styles.mono}`} width="48%" />
      <SkeletonCell className={`${styles.td} ${styles.merchant}`} width="66%" />
      <SkeletonCell className={`${styles.td} ${styles.matchType}`} width="58%" />
      <SkeletonCell className={styles.td} width="46%" />
      <SkeletonCell className={`${styles.td} ${styles.tdRight}`} width="60%" align="right" />
      <SkeletonCell className={`${styles.td} ${styles.tdRight} ${styles.feeCell}`} width="42%" align="right" />
      <td className={`${styles.td} ${styles.tdCenter}`}>
        <span className={styles.skeletonButton} />
      </td>
    </tr>
  )
}

function ReviewPanel({ row, onMarkMatched, onClose }) {
  const [marking, setMarking]     = useState(false)
  const [selectedOption, setSelectedOption] = useState(null)

  const anomaly = row.is_anomaly

  async function handleMarkMatched() {
    setMarking(true)
    let selectedTxnIds = null
    if (selectedOption !== null && row.review_metadata) {
      try {
        const combinations = JSON.parse(row.review_metadata)
        selectedTxnIds = combinations[selectedOption]
      } catch {}
    }
    await onMarkMatched(row.id, selectedTxnIds)
    setMarking(false)
    onClose()
  }

  const renderMembers = (members) => (
    <ul className={styles.memberList}>
      {members.map(m => (
        <li key={m.id || m.internal_transaction_id} className={styles.memberItem}>
          ID {m.internal_transaction_id} &bull; {fmtDate(m.internal_timestamp)} &bull; {fmtAmount(m.internal_amount)}
        </li>
      ))}
    </ul>
  )

  const renderReviewMetadata = (meta) => {
    if (!meta) return null
    try {
      const combinations = JSON.parse(meta)
      if (!Array.isArray(combinations)) return null
      return (
        <div className={styles.combinationsContainer}>
          <p className={styles.combinationsHeader}>Ambiguous Combinations Found:</p>
          {combinations.map((comb, i) => (
            <div key={i} className={styles.combinationItem}>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name={`ambiguous_option_${row.id}`}
                  checked={selectedOption === i}
                  onChange={() => setSelectedOption(i)}
                  style={{ marginTop: '4px' }}
                />
                <div>
                  <strong>Option {i + 1}:</strong> {comb.join(', ')}
                </div>
              </label>
            </div>
          ))}
        </div>
      )
    } catch {
      return null
    }
  }

  // Matched non-anomaly -> read-only detail view
  if (row.status === 'MATCHED' && !anomaly) {
    return (
      <div className={styles.detailsContent}>
        <h4>Match Details</h4>
        <div className={styles.detailGrid}>
          {row.is_group ? (
            <div style={{ gridColumn: '1 / -1' }}>
              <span className={styles.detailLabel}>Group Members ({row.member_count}):</span>
              {renderMembers(row.members)}
              <div style={{ marginTop: '12px' }}>
                <span className={styles.detailLabel}>Bank Statement Record:</span>
                <span className={styles.detailValue}>
                  Ref {row.bank_reference_id || '-'} &bull; {fmtDate(row.settlement_date)} &bull; {fmtAmount(row.deposit_amount)} &bull; Fee {fmtAmount(row.fee_deducted)}
                </span>
              </div>
            </div>
          ) : (
            <>
              <div>
                <span className={styles.detailLabel}>Internal Ledger Record:</span>
                <span className={styles.detailValue}>
                  ID {row.internal_transaction_id || '-'} &bull; {fmtDate(row.internal_timestamp)} &bull; {fmtAmount(row.internal_amount)}
                </span>
              </div>
              <div>
                <span className={styles.detailLabel}>Bank Statement Record:</span>
                <span className={styles.detailValue}>
                  Ref {row.bank_reference_id || '-'} &bull; {fmtDate(row.settlement_date)} &bull; {fmtAmount(row.deposit_amount)} &bull; Fee {fmtAmount(row.fee_deducted)}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    )
  }

  // Actionable rows (UNDER_REVIEW / UNRECONCILED / anomaly)
  return (
    <div className={styles.detailsContent}>
      <h4>Review Details</h4>

      {row.anomaly_reason
        ? <p className={styles.reasonText}>{row.anomaly_reason}</p>
        : <p className={styles.reasonText}>Status: {row.status}</p>
      }

      {row.review_metadata && renderReviewMetadata(row.review_metadata)}

      {/* Mark Matched — only for UNDER_REVIEW */}
      {row.status === 'UNDER_REVIEW' && (
        <div className={styles.reviewActions}>
          <button
            className={styles.markMatchedBtn}
            onClick={handleMarkMatched}
            disabled={marking}
          >
            {marking ? 'Saving\u2026' : '\u2713 Mark as Matched'}
          </button>
        </div>
      )}

    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
/**
 * Pure presentation component — all state lives in App.jsx.
 *
 * Props:
 *   results          - current page rows from the server
 *   loading          - show loading state
 *   page             - current page number (1-indexed)
 *   totalPages       - total pages from server
 *   totalItems       - total matching records from server
 *   pageSize         - rows per page
 *   onPage(n)        - navigate to page n
 *   activeTab        - currently selected tab id
 *   tabCounts        - { all, matched, unreconciled, under_review, anomalies }
 *   onTabChange(id)  - switch active tab
 *   searchQuery      - current search string
 *   onSearchChange   - controlled input handler
 *   sortOrder        - 'default' | 'highToLow' | 'lowToHigh'
 *   onSortChange     - handler
 *   onMarkMatched(id)         - marks record as MATCHED
 */
export default function TransactionsTable({
  results,
  loading,
  page,
  totalPages,
  totalItems,
  pageSize,
  onPage,
  activeTab,
  tabCounts,
  onTabChange,
  searchQuery,
  onSearchChange,
  sortOrder,
  onSortChange,
  onMarkMatched,
}) {
  const [expandedRowId, setExpandedRowId]   = useState(null)
  const [showFilterMenu, setShowFilterMenu] = useState(false)

  const currentTab = TABS.find(t => t.id === activeTab) || TABS[0]

  // Aggregate MANY_TO_ONE rows so the parent group is a single row
  const rawRows = results || []
  const aggregatedRows = []
  const groupMap = {}

  for (const r of rawRows) {
    if (r.group_id && r.status === 'MATCHED') {
      if (!groupMap[r.group_id]) {
        // Create the parent row
        const parent = {
          ...r,
          id: r.group_id, // Use group_id as the key
          is_group: true,
          members: [r],
        }
        groupMap[r.group_id] = parent
        aggregatedRows.push(parent)
      } else {
        // Add member to existing parent
        groupMap[r.group_id].members.push(r)
      }
    } else {
      aggregatedRows.push(r)
    }
  }

  const pageRows   = aggregatedRows
  const skeletonRowCount = Math.max(4, Math.min(pageSize || 8, 8))

  function toggleRow(id) {
    setExpandedRowId(prev => prev === id ? null : id)
  }

  function switchTab(tabId) {
    setExpandedRowId(null)
    onTabChange(tabId)
  }

  function handleSortChange(order) {
    setShowFilterMenu(false)
    onSortChange(order)
  }

  function handleExport() {
    exportToCsv(pageRows, currentTab.label)
  }

  return (
    <section className={`card ${styles.section}`}>
      {/* Tabs */}
      <div className={`${styles.tabBar} hide-scrollbar`}>
        {TABS.map(tab => {
          const count          = tabCounts[tab.id] ?? 0
          const isAnomaly      = tab.id === 'anomalies'
          const isUnreconciled = tab.id === 'unreconciled'
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              className={`${styles.tab} ${activeTab === tab.id ? styles.activeTab : ''}`}
              onClick={() => switchTab(tab.id)}
            >
              {tab.label}
              <span className={
                isAnomaly      ? styles.anomalyCount  :
                isUnreconciled ? styles.errorCount    :
                styles.neutralCount
              }>
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Table controls */}
      <div className={styles.controls}>
        <div className={styles.searchWrap}>
          <span
            className="material-symbols-outlined"
            style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--secondary)', fontSize: '18px', pointerEvents: 'none' }}
          >
            search
          </span>
          <input
            id="transaction-search"
            className={styles.searchInput}
            placeholder="Search reference or merchant..."
            type="text"
            value={searchQuery}
            onChange={e => onSearchChange(e.target.value)}
          />
        </div>
        <div className={styles.actionBtns}>
          <div className={styles.filterWrapper}>
            <button
              id="sort-btn"
              className={styles.actionBtn}
              onClick={() => setShowFilterMenu(!showFilterMenu)}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>sort</span>
              Sort
            </button>
            {showFilterMenu && (
              <div className={styles.filterMenu}>
                <div className={styles.filterMenuHeader}>Sort by Amount</div>
                <button
                  className={`${styles.filterOption} ${sortOrder === 'default'   ? styles.activeOption : ''}`}
                  onClick={() => handleSortChange('default')}
                >Default</button>
                <button
                  className={`${styles.filterOption} ${sortOrder === 'highToLow' ? styles.activeOption : ''}`}
                  onClick={() => handleSortChange('highToLow')}
                >High to Low</button>
                <button
                  className={`${styles.filterOption} ${sortOrder === 'lowToHigh' ? styles.activeOption : ''}`}
                  onClick={() => handleSortChange('lowToHigh')}
                >Low to High</button>
              </div>
            )}
          </div>
          <button id="export-btn" className={styles.actionBtn} onClick={handleExport}>
            <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>download</span>
            Export
          </button>
        </div>
      </div>

      {/* Table */}
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr className={styles.thead}>
              <th className={styles.th}>Date</th>
              <th className={styles.th}>Reference</th>
              <th className={styles.th}>Merchant</th>
              <th className={styles.th}>Match Type</th>
              <th className={styles.th}>Status</th>
              <th className={`${styles.th} ${styles.thRight}`}>Amount</th>
              <th className={`${styles.th} ${styles.thRight}`}>Fee</th>
              <th className={`${styles.th} ${styles.thCenter}`}>Action</th>
            </tr>
          </thead>
          <tbody className={styles.tbody}>
            {loading ? (
              Array.from({ length: skeletonRowCount }, (_, idx) => (
                <SkeletonRow key={`skeleton-${idx}`} />
              ))
            ) : pageRows.length === 0 ? (
              <tr>
                <td colSpan={8} className={styles.emptyRow}>
                  {results !== null
                    ? 'No records in this category.'
                    : 'Upload files and run reconciliation to see results.'}
                </td>
              </tr>
            ) : (
              pageRows.map((row, idx) => {
                const anomaly      = row.is_anomaly
                const rowKey       = row.id || idx
                const isActionable = anomaly || row.status === 'UNRECONCILED' || row.status === 'UNDER_REVIEW'

                return (
                  <Fragment key={rowKey}>
                    <tr className={`${styles.tr} ${anomaly ? styles.anomalyRow : ''}`}>
                      <td className={styles.td}>
                        {fmtDate(row.internal_timestamp || row.settlement_date)}
                      </td>
                      <td className={`${styles.td} ${styles.mono}`}>
                        {row.is_group
                          ? <span className={styles.groupBadge}>Group ({row.member_count} items)</span>
                          : (row.internal_transaction_id || row.bank_reference_id || '-')}
                      </td>
                      <td className={`${styles.td} ${styles.merchant}`}>
                        {row.merchant_id || '-'}
                      </td>
                      <td className={`${styles.td} ${styles.matchType}`}>
                        {matchTypeLabel(row.match_type)}
                      </td>
                      <td className={styles.td}>
                        <StatusBadge status={row.status} isAnomaly={row.is_anomaly} />
                      </td>
                      <td className={`${styles.td} ${styles.tdRight} tabular-nums`}>
                        {fmtAmount(row.is_group ? row.deposit_amount : (row.internal_amount ?? row.deposit_amount))}
                      </td>
                      <td className={`${styles.td} ${styles.tdRight} ${styles.feeCell} tabular-nums`}>
                        {row.fee_deducted && Number(row.fee_deducted) !== 0
                          ? `-${fmtAmount(row.fee_deducted)}`
                          : '$0.00'}
                      </td>
                      <td className={`${styles.td} ${styles.tdCenter}`}>
                        <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', alignItems: 'center' }}>
                          <button
                            className={styles.reviewBtn}
                            onClick={() => toggleRow(rowKey)}
                          >
                            {expandedRowId === rowKey
                              ? 'Less'
                              : isActionable ? 'Review' : 'View Details'}
                          </button>
                        </div>
                      </td>
                    </tr>

                    {/* Expanded review / detail panel */}
                    {expandedRowId === rowKey && (
                      <tr className={styles.expandedRow}>
                        <td colSpan={8} className={styles.expandedCell}>
                          <ReviewPanel
                            row={row}
                            onMarkMatched={onMarkMatched}
                            onClose={() => setExpandedRowId(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <Pagination
        page={page}
        totalPages={totalPages}
        total={totalItems}
        pageSize={pageSize}
        onPage={onPage}
      />
    </section>
  )
}
