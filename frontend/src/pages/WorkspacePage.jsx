/**
 * src/pages/WorkspacePage.jsx
 *
 * Reconciliation Workspace — the main application view.
 * Migrated from the root App.jsx body. No business logic changes.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import TopNav from '../components/TopNav'
import BatchSelector from '../components/BatchSelector'
import DataIngestion from '../components/DataIngestion'
import SummaryCards from '../components/SummaryCards'
import TransactionsTable from '../components/TransactionsTable'
import AgentPanel from '../components/AgentPanel'
import { getResults, listBatches, markMatched, getBatchReport } from '../api'
import { StaggeredTextReveal } from '../components/ui/StaggeredTextReveal'
import { WarmBeam } from '../components/ui/WarmBeam'
import { useAuth } from '../context/AuthContext'
import styles from './WorkspacePage.module.css'

const DEFAULT_SUMMARY = {
  total_internal: 0,
  exact_matches: 0,
  date_shift_matches: 0,
  fee_adjusted_matches: 0,
  many_to_one_matches: 0,
  under_review_groups: 0,
  unreconciled_internal: 0,
  unreconciled_bank: 0,
  anomalies_flagged: 0,
  total_bank: 0,
}

const PAGE_SIZE = 10

export default function WorkspacePage() {
  const [selectedBatchId, setSelectedBatchId] = useState(null)
  const [results, setResults]             = useState(null)
  const [summary, setSummary]             = useState(null)
  const [tabCounts, setTabCounts]         = useState({})
  const [report, setReport]               = useState(null)
  const [loadingResults, setLoadingResults] = useState(false)
  const [resultsError, setResultsError]   = useState(null)
  const [isAgentOpen, setIsAgentOpen]     = useState(false)

  const [activeTab, setActiveTab]   = useState('all')
  const [page, setPage]             = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortOrder, setSortOrder]   = useState('default')
  const [totalPages, setTotalPages] = useState(1)
  const [totalItems, setTotalItems] = useState(0)

  const searchTimer = useRef(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedSearch(searchQuery), 350)
    return () => clearTimeout(searchTimer.current)
  }, [searchQuery])

  const fetchResults = useCallback(async (batchId, opts = {}) => {
    if (!batchId) return
    setLoadingResults(true)
    setResultsError(null)
    try {
      const params = {
        page:   opts.page   ?? 1,
        limit:  PAGE_SIZE,
        tab:    opts.tab    ?? 'all',
        sort:   opts.sort   !== 'default' ? opts.sort : undefined,
        search: opts.search || undefined,
      }
      const [data, reportData] = await Promise.all([
        getResults(batchId, params),
        getBatchReport(batchId).catch(() => null),
      ])
      setResults(data.results)
      setSummary(data.summary)
      setTabCounts(data.tab_counts ?? {})
      setTotalPages(data.total_pages ?? 1)
      setTotalItems(data.total_items ?? 0)
      setReport(reportData)
    } catch (err) {
      setResultsError(err.message)
      setResults(null)
      setSummary(null)
      setReport(null)
    } finally {
      setLoadingResults(false)
    }
  }, [])

  useEffect(() => {
    if (selectedBatchId) {
      fetchResults(selectedBatchId, {
        page,
        tab:    activeTab,
        sort:   sortOrder,
        search: debouncedSearch,
      })
    }
  }, [selectedBatchId, page, activeTab, sortOrder, debouncedSearch, fetchResults])

  useEffect(() => {
    setPage(1)
  }, [activeTab, sortOrder, debouncedSearch])

  async function handleMarkMatched(resultId) {
    try {
      await markMatched(resultId)
      fetchResults(selectedBatchId, { page, tab: activeTab, sort: sortOrder, search: debouncedSearch })
    } catch (err) {
      alert(`Failed to mark as matched: ${err.message}`)
    }
  }

  async function handleExport() {
    if (!selectedBatchId) return []
    const params = {
      limit: 100,
      tab: activeTab,
      sort: sortOrder !== 'default' ? sortOrder : undefined,
      search: debouncedSearch || undefined,
    }
    const firstPage = await getResults(selectedBatchId, { ...params, page: 1 })
    const exportRows = [...firstPage.results]
    for (let exportPage = 2; exportPage <= firstPage.total_pages; exportPage += 1) {
      const data = await getResults(selectedBatchId, { ...params, page: exportPage })
      exportRows.push(...data.results)
    }
    return exportRows
  }

  async function handleBatchComplete() {
    const batches = await listBatches()
    const newest = batches.find(b => b.status === 'COMPLETE')
    if (newest) {
      setSelectedBatchId(newest.batch_id)
      setActiveTab('all')
      setPage(1)
      setSearchQuery('')
      setSortOrder('default')
    }
  }

  return (
    <div className={styles.pageWrapper}>
      <WarmBeam />
      <TopNav />
      <main className={styles.main}>
        <div className={styles.pageHeader}>
          <div>
            <StaggeredTextReveal text="Reconciliation Workspace" className={styles.pageTitle} />
            <p className={styles.pageSubtitle}>Upload and audit financial records.</p>
          </div>
          <BatchSelector
            selectedBatchId={selectedBatchId}
            onSelect={setSelectedBatchId}
          />
        </div>

        <DataIngestion onBatchComplete={handleBatchComplete} />
        <SummaryCards summary={summary || DEFAULT_SUMMARY} tabCounts={tabCounts} report={report} />

        {resultsError && (
          <div className={styles.errorBanner} role="alert">
            <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>error</span>
            {resultsError}
          </div>
        )}

        <TransactionsTable
          results={results}
          loading={loadingResults}
          page={page}
          totalPages={totalPages}
          totalItems={totalItems}
          pageSize={PAGE_SIZE}
          onPage={setPage}
          activeTab={activeTab}
          tabCounts={tabCounts}
          onTabChange={(tab) => { setActiveTab(tab); setPage(1) }}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          sortOrder={sortOrder}
          onSortChange={setSortOrder}
          onExport={handleExport}
          onMarkMatched={handleMarkMatched}
        />
      </main>
      <AgentPanel
        isOpen={isAgentOpen}
        onClose={() => setIsAgentOpen(false)}
        batchId={selectedBatchId}
      />
      <button
        type="button"
        className={styles.agentFab}
        aria-label={isAgentOpen ? 'Close reconciliation assistant' : 'Ask the reconciliation assistant'}
        aria-expanded={isAgentOpen}
        onClick={() => setIsAgentOpen((isOpen) => !isOpen)}
      >
        <span className={styles.agentFabIcon} aria-hidden="true">
          <span className={`material-symbols-outlined ${styles.forumIcon}`}>forum</span>
          <span className={`material-symbols-outlined ${styles.sparklesIcon}`}>auto_awesome</span>
        </span>
        <span className={styles.agentFabLabel}>Ask agent</span>
      </button>
    </div>
  )
}
