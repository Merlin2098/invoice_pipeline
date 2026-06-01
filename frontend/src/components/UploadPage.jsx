import { useRef, useState } from 'react'
import { requestUploadUrls, uploadFileToS3 } from '../api/client.js'

const MAX_SIZE_BYTES = 20 * 1024 * 1024
const ACCEPTED_TYPES = ['application/pdf', 'image/tiff']
const ACCEPTED_EXTS  = ['.pdf', '.tif', '.tiff']

function fileKey(file) { return `${file.name}-${file.size}` }

function StatusBadge({ status }) {
  const labels = {
    idle: 'Waiting',
    uploading: 'Uploading…',
    done: 'Uploaded',
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
  const [files, setFiles] = useState([])   // { file, status, progress, error }
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
    <div>
      <h2 className="page-title">Upload Invoices</h2>

      <div className="card">
        {/* Drop zone */}
        <div
          className="dropzone"
          onDrop={onDrop}
          onDragOver={e => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
        >
          <span className="dropzone-icon">📄</span>
          <p className="dropzone-text">Drag & drop PDF / TIF files here, or <strong>click to browse</strong></p>
          <p className="dropzone-hint">Max 20 MB per file</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTS.join(',')}
            style={{ display: 'none' }}
            onChange={e => addFiles(e.target.files)}
          />
        </div>

        {/* File list */}
        {files.length > 0 && (
          <ul className="file-list">
            {files.map(entry => (
              <li key={fileKey(entry.file)} className="file-row">
                <span className="file-name">{entry.file.name}</span>
                <span className="file-size">{(entry.file.size / 1024).toFixed(0)} KB</span>

                {entry.status === 'uploading' && (
                  <div className="progress-bar-wrap">
                    <div className="progress-bar" style={{ width: `${entry.progress}%` }} />
                    <span className="progress-label">{entry.progress}%</span>
                  </div>
                )}

                <StatusBadge status={entry.status} />

                {entry.error && <span className="file-error" title={entry.error}>⚠</span>}

                {entry.status !== 'uploading' && (
                  <button
                    className="btn-remove"
                    onClick={() => removeFile(fileKey(entry.file))}
                    aria-label="Remove"
                  >✕</button>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="upload-actions">
          <button
            className="btn-primary"
            onClick={handleUpload}
            disabled={uploading || pendingCount === 0}
          >
            {uploading ? 'Uploading…' : `Upload ${pendingCount > 0 ? `(${pendingCount})` : ''}`}
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

      <style>{`
        .dropzone {
          border: 2px dashed #d1d5db;
          border-radius: 8px;
          padding: 2.5rem 1.5rem;
          text-align: center;
          cursor: pointer;
          transition: border-color 0.15s, background 0.15s;
          margin-bottom: 1.25rem;
        }
        .dropzone:hover { border-color: #2563eb; background: #f0f7ff; }
        .dropzone-icon { font-size: 2rem; display: block; margin-bottom: 0.5rem; }
        .dropzone-text { font-size: 0.95rem; color: #374151; margin-bottom: 0.25rem; }
        .dropzone-hint { font-size: 0.8rem; color: #9ca3af; }

        .file-list { list-style: none; display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.25rem; }
        .file-row {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.6rem 0.75rem;
          background: #f9fafb;
          border-radius: 6px;
          font-size: 0.875rem;
          flex-wrap: wrap;
        }
        .file-name { flex: 1 1 180px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .file-size { color: #6b7280; white-space: nowrap; }
        .file-error { color: #dc2626; font-size: 1.1rem; }

        .progress-bar-wrap {
          flex: 1 1 100px;
          height: 6px;
          background: #e5e7eb;
          border-radius: 3px;
          position: relative;
          overflow: hidden;
        }
        .progress-bar { height: 100%; background: #2563eb; border-radius: 3px; transition: width 0.1s; }
        .progress-label { position: absolute; right: 0; top: -14px; font-size: 0.7rem; color: #6b7280; }

        .btn-remove {
          background: none;
          border: none;
          color: #9ca3af;
          font-size: 0.9rem;
          padding: 0 0.25rem;
        }
        .btn-remove:hover { color: #dc2626; }

        .upload-actions { display: flex; gap: 0.75rem; align-items: center; }
      `}</style>
    </div>
  )
}
