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

export default function DataIngestion({ onBatchComplete }) {
  const [internalFile, setInternalFile] = useState(null)
  const [bankFile, setBankFile] = useState(null)
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
        <button
          className={styles.reconcileBtn}
          onClick={handleReconcile}
          disabled={processing}
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
