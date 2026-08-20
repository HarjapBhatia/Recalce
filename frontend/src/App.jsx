import { useState, useEffect, useCallback, useRef } from 'react'
import TopNav from './components/TopNav'
import BatchSelector from './components/BatchSelector'
import DataIngestion from './components/DataIngestion'
import SummaryCards from './components/SummaryCards'
import TransactionsTable from './components/TransactionsTable'
import { getResults, listBatches, markMatched } from './api'
import styles from './App.module.css'

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

export default function App() {
  const [selectedBatchId, setSelectedBatchId] = useState(null)
  const [results, setResults]             = useState(null)
  const [summary, setSummary]             = useState(null)
  const [tabCounts, setTabCounts]         = useState({})
  const [loadingResults, setLoadingResults] = useState(false)
  const [resultsError, setResultsError]   = useState(null)

  // Server-side filter/sort/pagination state (lifted here so App controls fetching)
  const [activeTab, setActiveTab]   = useState('all')
  const [page, setPage]             = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortOrder, setSortOrder]   = useState('default')
  const [totalPages, setTotalPages] = useState(1)
  const [totalItems, setTotalItems] = useState(0)

  // Debounce search to avoid hammering the API on every keystroke
  const searchTimer = useRef(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedSearch(searchQuery), 350)
    return () => clearTimeout(searchTimer.current)
  }, [searchQuery])

  // ── Core fetch ──────────────────────────────────────────────────────────────
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
      const data = await getResults(batchId, params)
      setResults(data.results)
      setSummary(data.summary)
      setTabCounts(data.tab_counts ?? {})
      setTotalPages(data.total_pages ?? 1)
      setTotalItems(data.total_items ?? 0)
    } catch (err) {
      setResultsError(err.message)
      setResults(null)
      setSummary(null)
    } finally {
      setLoadingResults(false)
    }
  }, [])

  // Re-fetch whenever any filter parameter changes
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

  // Reset page to 1 when filters/tab change
  useEffect(() => {
    setPage(1)
  }, [activeTab, sortOrder, debouncedSearch])

  // ── Action handlers ─────────────────────────────────────────────────────────
  async function handleMarkMatched(resultId) {
    try {
      await markMatched(resultId)
      // Re-fetch the current view to reflect the status change
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

  // ── After a new reconciliation run ──────────────────────────────────────────
  async function handleBatchComplete() {
    const batches = await listBatches()
    const newest = batches.find(b => b.status === 'COMPLETE')
    if (newest) {
      setSelectedBatchId(newest.batch_id)
      // Reset all filter state for the new batch
      setActiveTab('all')
      setPage(1)
      setSearchQuery('')
      setSortOrder('default')
    }
  }

  return (
    <>
      <TopNav />
      <main className={styles.main}>
        {/* Page header */}
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.pageTitle}>Reconciliation Workspace</h1>
            <p className={styles.pageSubtitle}>Upload and audit financial records.</p>
          </div>
          <BatchSelector
            selectedBatchId={selectedBatchId}
            onSelect={setSelectedBatchId}
          />
        </div>

        {/* Data ingestion */}
        <DataIngestion onBatchComplete={handleBatchComplete} />

        {/* Summary cards */}
        <SummaryCards summary={summary || DEFAULT_SUMMARY} tabCounts={tabCounts} />

        {/* Results error */}
        {resultsError && (
          <div className={styles.errorBanner} role="alert">
            <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>error</span>
            {resultsError}
          </div>
        )}

        {/* Transactions table — now purely a presentation layer */}
        <TransactionsTable
          results={results}
          loading={loadingResults}
          // pagination
          page={page}
          totalPages={totalPages}
          totalItems={totalItems}
          pageSize={PAGE_SIZE}
          onPage={setPage}
          // tabs
          activeTab={activeTab}
          tabCounts={tabCounts}
          onTabChange={(tab) => { setActiveTab(tab); setPage(1) }}
          // search
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          // sort
          sortOrder={sortOrder}
          onSortChange={setSortOrder}
          onExport={handleExport}
          // actions
          onMarkMatched={handleMarkMatched}
        />
      </main>
    </>
  )
}
