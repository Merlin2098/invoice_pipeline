import { useCallback, useEffect, useState } from 'react'
import { listInvoices } from '../api/client.js'

const STATUS_FILTERS = ['', 'Uploaded', 'Processing', 'Consolidating', 'Completed', 'Failed']

function StatusBadge({ status }) {
  const cls = `badge badge--${(status ?? 'unknown').toLowerCase()}`
  return <span className={cls}>{status ?? '—'}</span>
}

function InvoiceRow({ invoice }) {
  return (
    <tr>
      <td className="td-id">{invoice.invoice_id ?? '—'}</td>
      <td>{invoice.run_id ?? '—'}</td>
      <td><StatusBadge status={invoice.status} /></td>
      <td className="td-date">{invoice.updated_at ? new Date(invoice.updated_at).toLocaleString() : '—'}</td>
    </tr>
  )
}

export default function HistoryPage() {
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [nextToken, setNextToken]       = useState(null)
  const [autoRefresh, setAutoRefresh]   = useState(false)

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
    <div>
      <h2 className="page-title">Invoice History</h2>

      <div className="card">
        <div className="toolbar">
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

          <button className="btn-secondary" onClick={() => load(true)} disabled={loading}>
            {loading ? 'Loading…' : '↺ Refresh'}
          </button>
        </div>

        {error && <p className="error-msg">{error}</p>}

        {invoices.length === 0 && !loading && !error && (
          <p className="empty-msg">No invoices found. Upload some PDFs to get started.</p>
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

      <style>{`
        .toolbar {
          display: flex;
          align-items: center;
          gap: 1rem;
          margin-bottom: 1.25rem;
          flex-wrap: wrap;
        }
        .toolbar-label {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.875rem;
          color: #374151;
        }
        .toolbar-auto-refresh { gap: 0.4rem; }
        .select {
          border: 1px solid #d1d5db;
          border-radius: 6px;
          padding: 0.35rem 0.6rem;
          font-size: 0.875rem;
          background: #fff;
        }
        .error-msg { color: #dc2626; font-size: 0.875rem; margin-bottom: 0.75rem; }
        .empty-msg { color: #6b7280; font-size: 0.875rem; text-align: center; padding: 2rem 0; }

        .table-wrap { overflow-x: auto; }
        .inv-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
        .inv-table th {
          text-align: left;
          padding: 0.6rem 0.75rem;
          background: #f9fafb;
          border-bottom: 2px solid #e5e7eb;
          font-weight: 600;
          color: #374151;
          white-space: nowrap;
        }
        .inv-table td {
          padding: 0.6rem 0.75rem;
          border-bottom: 1px solid #f3f4f6;
          vertical-align: middle;
        }
        .inv-table tr:hover td { background: #fafafa; }
        .td-id { font-family: monospace; font-size: 0.82rem; }
        .td-date { white-space: nowrap; color: #6b7280; }
        .load-more { text-align: center; margin-top: 1rem; }
      `}</style>
    </div>
  )
}
