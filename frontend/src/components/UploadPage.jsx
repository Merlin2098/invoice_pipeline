import { useRef, useState } from 'react'
import { AlertTriangle, FileText, Trash2, UploadCloud } from 'lucide-react'
import { requestUploadUrls, uploadFileToS3 } from '../api/client.js'

const MAX_SIZE_BYTES = 20 * 1024 * 1024
const ACCEPTED_EXTS = ['.pdf', '.tif', '.tiff']

function fileKey(file) { return `${file.name}-${file.size}` }

function StatusBadge({ status }) {
  const labels = {
    idle: 'Waiting',
    uploading: 'Uploading',
    done: 'Completed',
    error: 'Failed',
  }
  const cls = {
    idle: 'badge badge--unknown',
    uploading: 'badge badge--processing',
    done: 'badge badge--completed',
    error: 'badge badge--failed',
  }
  return <span className={cls[status] ?? 'badge badge--unknown'}>{labels[status] ?? status}</span>
}

export default function UploadPage() {
  const inputRef = useRef(null)
  const [files, setFiles] = useState([])
  const [uploading, setUploading] = useState(false)

  function addFiles(newFiles) {
    const valid = Array.from(newFiles).filter(f => {
      const ext = f.name.toLowerCase().slice(f.name.lastIndexOf('.'))
      return ACCEPTED_EXTS.includes(ext) && f.size <= MAX_SIZE_BYTES
    })
    setFiles(prev => {
      const existing = new Set(prev.map(e => fileKey(e.file)))
      const deduped = valid.filter(f => !existing.has(fileKey(f)))
      return [...prev, ...deduped.map(f => ({ file: f, status: 'idle', progress: 0, error: null }))]
    })
  }

  function removeFile(key) {
    setFiles(prev => prev.filter(e => fileKey(e.file) !== key))
  }

  function onDrop(e) {
    e.preventDefault()
    addFiles(e.dataTransfer.files)
  }

  async function handleUpload() {
    const pending = files.filter(e => e.status === 'idle')
    if (!pending.length) return
    setUploading(true)

    let urls
    try {
      const data = await requestUploadUrls(pending.map(e => e.file))
      urls = data.uploads
    } catch (err) {
      setFiles(prev => prev.map(e =>
        e.status === 'idle' ? { ...e, status: 'error', error: err.message } : e
      ))
      setUploading(false)
      return
    }

    await Promise.all(pending.map(async (entry, i) => {
      const { upload_url } = urls[i]
      setFiles(prev => prev.map(e => fileKey(e.file) === fileKey(entry.file) ? { ...e, status: 'uploading' } : e))
      try {
        await uploadFileToS3(upload_url, entry.file, pct => {
          setFiles(prev => prev.map(e => fileKey(e.file) === fileKey(entry.file) ? { ...e, progress: pct } : e))
        })
        setFiles(prev => prev.map(e => fileKey(e.file) === fileKey(entry.file) ? { ...e, status: 'done', progress: 100 } : e))
      } catch (err) {
        setFiles(prev => prev.map(e => fileKey(e.file) === fileKey(entry.file) ? { ...e, status: 'error', error: err.message } : e))
      }
    }))

    setUploading(false)
  }

  const pendingCount = files.filter(e => e.status === 'idle').length

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Upload Invoices</h1>
          <p className="page-description">Send source documents into the AWS intake bucket for OCR and routing.</p>
        </div>
      </div>

      <div className="card">
        <div
          role="button"
          tabIndex={0}
          className="dropzone"
          onDrop={onDrop}
          onDragOver={e => e.preventDefault()}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              inputRef.current?.click()
            }
          }}
          onClick={() => inputRef.current?.click()}
        >
          <span className="dropzone-icon"><UploadCloud size={24} /></span>
          <span className="dropzone-text">Drag and drop PDF or TIFF files here, or click to browse</span>
          <span className="dropzone-hint">Max 20 MB per file</span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTS.join(',')}
            style={{ display: 'none' }}
            onChange={e => addFiles(e.target.files)}
          />
        </div>

        {files.length > 0 && (
          <ul className="file-list">
            {files.map(entry => (
              <li key={fileKey(entry.file)} className="file-row">
                <span className="file-name-wrap">
                  <FileText size={17} />
                  <span className="file-name">{entry.file.name}</span>
                </span>
                <span className="file-size">{(entry.file.size / 1024).toFixed(0)} KB</span>

                <div className="progress-bar-wrap" aria-label={`Upload progress ${entry.progress}%`}>
                  <div className="progress-bar" style={{ width: `${entry.progress}%` }} />
                </div>
                <span className="progress-label">{entry.progress}%</span>

                <StatusBadge status={entry.status} />

                {entry.error && <AlertTriangle className="file-error" size={17} aria-label={entry.error} />}

                {entry.status !== 'uploading' && (
                  <button
                    className="icon-button"
                    onClick={() => removeFile(fileKey(entry.file))}
                    aria-label={`Remove ${entry.file.name}`}
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="upload-actions">
          <button
            className="btn-primary btn-with-icon"
            onClick={handleUpload}
            disabled={uploading || pendingCount === 0}
          >
            <UploadCloud size={17} />
            {uploading ? 'Uploading' : `Upload${pendingCount > 0 ? ` (${pendingCount})` : ''}`}
          </button>
          {files.length > 0 && (
            <button
              className="btn-secondary"
              onClick={() => setFiles([])}
              disabled={uploading}
            >
              Clear all
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
