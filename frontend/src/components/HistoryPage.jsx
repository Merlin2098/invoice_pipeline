import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { listInvoices } from '../api/client.js'

const STATUS_FILTERS = ['', 'Uploaded', 'Processing', 'Consolidating', 'Completed', 'Failed']

function StatusBadge({ status }) {
  const cls = `badge badge--${(status ?? 'unknown').toLowerCase()}`
  return <span className={cls}>{status ?? '-'}</span>
}

function InvoiceRow({ invoice }) {
  return (
    <tr>
      <td className="td-id">{invoice.invoice_id ?? '-'}</td>
      <td>{invoice.run_id ?? '-'}</td>
      <td><StatusBadge status={invoice.status} /></td>
      <td className="td-date">{invoice.updated_at ? new Date(invoice.updated_at).toLocaleString() : '-'}</td>
    </tr>
  )
}

export default function HistoryPage() {
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [nextToken, setNextToken] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(false)

  const load = useCallback(async (reset = true) => {
    setLoading(true)
    setError(null)
    try {
      const data = await listInvoices({
        status: statusFilter || undefined,
        limit: 20,
        nextToken: reset ? undefined : nextToken,
      })
      setInvoices(prev => reset ? data.invoices : [...prev, ...data.invoices])
      setNextToken(data.next_token ?? null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, nextToken])

  useEffect(() => { load(true) }, [statusFilter])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(() => load(true), 10_000)
    return () => clearInterval(id)
  }, [autoRefresh, load])

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Invoice History</h1>
          <p className="page-description">Inspect workflow status and recent document activity.</p>
        </div>
      </div>

      <div className="card">
        <div className="toolbar">
          <div className="toolbar-group">
            <label className="toolbar-label">
              Status
              <select
                className="select"
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
              >
                {STATUS_FILTERS.map(s => (
                  <option key={s} value={s}>{s || 'All'}</option>
                ))}
              </select>
            </label>

            <label className="toolbar-label toolbar-auto-refresh">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={e => setAutoRefresh(e.target.checked)}
              />
              Auto-refresh
            </label>
          </div>

          <button className="btn-secondary btn-with-icon" onClick={() => load(true)} disabled={loading}>
            <RefreshCw size={16} />
            {loading ? 'Loading' : 'Refresh'}
          </button>
        </div>

        {error && <p className="error-msg">{error}</p>}

        {invoices.length === 0 && !loading && !error && (
          <p className="empty-msg">No invoices found. Upload PDFs or TIFFs to start the pipeline.</p>
        )}

        {invoices.length > 0 && (
          <div className="table-wrap">
            <table className="inv-table">
              <thead>
                <tr>
                  <th>Invoice ID</th>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map(inv => (
                  <InvoiceRow key={`${inv.invoice_id}-${inv.run_id}`} invoice={inv} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {nextToken && (
          <div className="load-more">
            <button className="btn-secondary" onClick={() => load(false)} disabled={loading}>
              Load more
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
