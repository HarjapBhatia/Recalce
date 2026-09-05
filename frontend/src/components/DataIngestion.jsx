import { useRef, useState } from 'react'
import styles from './DataIngestion.module.css'
import { uploadFiles, getBatchStatus } from '../api'

function DropZone({ label, icon, file, onFile, id }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) onFile(f)
  }

  function handleChange(e) {
    const f = e.target.files[0]
    if (f) onFile(f)
  }

  return (
    <div
      className={`${styles.dropzone} ${dragging ? styles.dragging : ''} ${file ? styles.hasFile : ''}`}
      onClick={() => inputRef.current.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && inputRef.current.click()}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept=".csv,text/csv,application/vnd.ms-excel"
        style={{ display: 'none' }}
        onChange={handleChange}
      />
      <div className={styles.iconWrap}>
        <span className="material-symbols-outlined" style={{ fontSize: '24px', color: 'var(--on-surface-variant)' }}>
          {icon}
        </span>
      </div>
      <h3 className={styles.dropLabel}>{label}</h3>
      {file ? (
        <p className={styles.fileName}>{file.name}</p>
      ) : (
        <p className={styles.hint}>Accepts .csv (RFC 4180)</p>
      )}
      <div className={styles.selectBtn}>
        {file ? 'Change File' : 'Select File'}
      </div>
    </div>
  )
}

const DATASETS = ['dataset_a', 'dataset_b', 'dataset_c', 'dataset_d', 'dataset_e']

export default function DataIngestion({ onBatchComplete }) {
  const [internalFile, setInternalFile] = useState(null)
  const [bankFile, setBankFile] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [processingStatus, setProcessingStatus] = useState('')
  const [error, setError] = useState(null)

  const STATUS_LABELS = {
    PENDING: 'Queued for processing...',
    INGESTING: 'Ingesting CSV data...',
    MATCHING: 'Running waterfall matching engine...',
    ML_TRIAGE: 'Running ML anomaly triage...',
    COMPLETE: 'Complete',
    FAILED: 'Processing failed',
  }

  async function handleGenerateData() {
    setError(null)
    setGenerating(true)

    try {
      const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
      const baseUrl = rawBase.replace(/\/api\/v1\/?$/, '').replace(/\/+$/, '')
      const dataset = DATASETS[Math.floor(Math.random() * DATASETS.length)]

      const [internalRes, bankRes] = await Promise.all([
        fetch(`${baseUrl}/static/${dataset}/internal_ledger_test.csv`),
        fetch(`${baseUrl}/static/${dataset}/bank_statement_test.csv`),
      ])
      if (!internalRes.ok || !bankRes.ok) throw new Error('Failed to load sample dataset from server.')

      const [internalBlob, bankBlob] = await Promise.all([internalRes.blob(), bankRes.blob()])

      setInternalFile(new File([internalBlob], 'internal_ledger_test.csv', { type: 'text/csv' }))
      setBankFile(new File([bankBlob], 'bank_statement_test.csv', { type: 'text/csv' }))
    } catch (err) {
      setError(err.message || 'An error occurred. Please try again.')
    } finally {
      setGenerating(false)
    }
  }

  async function handleReconcile() {
    if (!internalFile || !bankFile) {
      setError('Please upload both the Internal Ledger and Bank Statement CSV files.')
      return
    }
    setError(null)
    setProcessing(true)
    setProcessingStatus('Uploading files...')

    try {
      const { batch_id } = await uploadFiles(internalFile, bankFile)
      setProcessingStatus(STATUS_LABELS['PENDING'])

      // Poll until complete or failed
      await new Promise((resolve, reject) => {
        const interval = setInterval(async () => {
          try {
            const data = await getBatchStatus(batch_id)
            const label = STATUS_LABELS[data.status] || data.status
            setProcessingStatus(label)

            if (data.status === 'COMPLETE') {
              clearInterval(interval)
              resolve(batch_id)
            } else if (data.status === 'FAILED') {
              clearInterval(interval)
              reject(new Error(data.error_message || 'Processing failed'))
            }
          } catch (err) {
            clearInterval(interval)
            reject(err)
          }
        }, 1500)
      })

      setProcessing(false)
      setProcessingStatus('')
      onBatchComplete()
    } catch (err) {
      setProcessing(false)
      setProcessingStatus('')
      setError(err.message || 'An error occurred. Please try again.')
    }
  }

  return (
    <section className={`card ${styles.section}`}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <span className="material-symbols-outlined" style={{ color: 'var(--primary-container)', fontSize: '22px' }}>upload_file</span>
          Data Ingestion
        </h2>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            className={styles.reconcileBtn}
            onClick={handleGenerateData}
            disabled={generating || processing}
            id="generate-data-btn"
          >
            {generating ? (
              <>
                <span className={styles.spinner} />
                Fetching...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>bolt</span>
                Generate Data
              </>
            )}
          </button>
          <button
            className={styles.reconcileBtn}
            onClick={handleReconcile}
            disabled={generating || processing}
            id="scan-reconcile-btn"
          >
            {processing ? (
              <>
                <span className={styles.spinner} />
                {processingStatus}
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>magic_button</span>
                Scan and Reconcile
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className={styles.errorBanner} role="alert">
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>error</span>
          {error}
        </div>
      )}

      <div className={styles.grid}>
        <DropZone
          id="internal-ledger-input"
          label="Upload Internal Ledger"
          icon="receipt_long"
          file={internalFile}
          onFile={setInternalFile}
        />
        <DropZone
          id="bank-statement-input"
          label="Upload Bank Statement"
          icon="account_balance"
          file={bankFile}
          onFile={setBankFile}
        />
      </div>
    </section>
  )
}
