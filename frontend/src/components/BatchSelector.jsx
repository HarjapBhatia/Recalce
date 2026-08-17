import { useEffect, useState } from 'react'
import { listBatches } from '../api'
import styles from './BatchSelector.module.css'

function formatBatchLabel(batch) {
  const date = new Date(batch.uploaded_at)
  const month = date.toLocaleString('en-US', { month: 'short' })
  const day = date.getDate()
  const year = date.getFullYear()
  // Use the first 8 chars of the batch ID as a short identifier
  const shortId = batch.batch_id.replace(/-/g, '').substring(0, 6).toUpperCase()
  return `Batch #${shortId} (${month} ${day}, ${year})`
}

export default function BatchSelector({ selectedBatchId, onSelect }) {
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const data = await listBatches()
      setBatches(data)
      // Do not auto-select, let user pick from dropdown
      // if (!selectedBatchId && data.length > 0) {
      //   const completed = data.find(b => b.status === 'COMPLETE')
      //   if (completed) onSelect(completed.batch_id)
      // }
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // Re-fetch when a new batch is selected externally (e.g. after upload completes)
  useEffect(() => {
    if (selectedBatchId) load()
  }, [selectedBatchId])

  function handleChange(e) {
    const val = e.target.value
    if (val) onSelect(val)
  }

  const completedBatches = batches.filter(b => b.status === 'COMPLETE')

  return (
    <div className={styles.wrapper}>
      <label className={styles.label} htmlFor="batch-select">Current Batch</label>
      <div className={styles.selectWrapper}>
        <select
          id="batch-select"
          className={styles.select}
          value={selectedBatchId || ''}
          onChange={handleChange}
          disabled={loading}
        >
          {completedBatches.length === 0 ? (
            <option value="" disabled>No batches yet</option>
          ) : (
            <>
              <option value="" disabled>Select a batch...</option>
              {completedBatches.map(b => (
                <option key={b.batch_id} value={b.batch_id}>
                  {formatBatchLabel(b)}
                </option>
              ))}
            </>
          )}
        </select>
        <span className="material-symbols-outlined" style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--secondary)', pointerEvents: 'none', fontSize: '20px' }}>
          expand_more
        </span>
      </div>
    </div>
  )
}
