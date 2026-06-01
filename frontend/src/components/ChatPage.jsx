import { useEffect, useRef, useState } from 'react'
import { sendChat } from '../api/client.js'

const MAX_CHARS = 500

function UserBubble({ text }) {
  return (
    <div className="bubble bubble--user">
      <div className="bubble-content">{text}</div>
    </div>
  )
}

function AssistantBubble({ message, loading }) {
  if (loading) {
    return (
      <div className="bubble bubble--assistant">
        <div className="bubble-content bubble-content--loading">
          <span className="dot" /><span className="dot" /><span className="dot" />
        </div>
      </div>
    )
  }

  if (message.error) {
    return (
      <div className="bubble bubble--assistant bubble--error">
        <div className="bubble-content">⚠ {message.error}</div>
      </div>
    )
  }

  return (
    <div className="bubble bubble--assistant">
      <div className="bubble-content">
        <p className="bubble-answer">{message.answer}</p>
        {message.rows?.length > 0 && <ResultTable rows={message.rows} />}
        {message.generated_sql && (
          <details className="sql-details">
            <summary>SQL</summary>
            <pre className="sql-pre">{message.generated_sql}</pre>
          </details>
        )}
        {message.execution_time_ms != null && (
          <p className="bubble-meta">
            {message.execution_time_ms} ms · {(message.athena_scan_mb ?? 0).toFixed(2)} MB scanned
          </p>
        )}
      </div>
    </div>
  )
}

function ResultTable({ rows }) {
  if (!rows.length) return null
  const cols = Object.keys(rows[0])
  return (
    <div className="result-table-wrap">
      <table className="result-table">
        <thead>
          <tr>{cols.map(c => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map(c => <td key={c}>{row[c] ?? '—'}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading]   = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend() {
    const q = question.trim()
    if (!q || loading) return

    setMessages(prev => [...prev, { role: 'user', text: q }])
    setQuestion('')
    setLoading(true)

    try {
      const data = await sendChat(q)
      setMessages(prev => [...prev, { role: 'assistant', ...data }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', error: err.message }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const remaining = MAX_CHARS - question.length

  return (
    <div className="chat-page">
      <h2 className="page-title">Chat with your invoices</h2>

      <div className="chat-card card">
        {messages.length === 0 && !loading && (
          <div className="chat-empty">
            <p className="chat-empty-title">Ask anything about your invoices</p>
            <ul className="chat-suggestions">
              {[
                'How much did we spend in total?',
                'Who are the top 5 suppliers?',
                'Show me invoices from the last month.',
              ].map(s => (
                <li key={s}>
                  <button
                    className="suggestion-btn"
                    onClick={() => { setQuestion(s); inputRef.current?.focus() }}
                  >{s}</button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="chat-messages">
          {messages.map((msg, i) =>
            msg.role === 'user'
              ? <UserBubble key={i} text={msg.text} />
              : <AssistantBubble key={i} message={msg} />
          )}
          {loading && <AssistantBubble loading />}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-row">
          <div className="chat-input-wrap">
            <textarea
              ref={inputRef}
              className="chat-input"
              placeholder="Ask about your invoices…"
              rows={2}
              maxLength={MAX_CHARS}
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            {question.length > 0 && (
              <span className={`char-count ${remaining < 50 ? 'char-count--warn' : ''}`}>
                {remaining}
              </span>
            )}
          </div>
          <button
            className="btn-primary btn-send"
            onClick={handleSend}
            disabled={loading || !question.trim()}
          >
            {loading ? '…' : '→'}
          </button>
        </div>
      </div>

      <style>{`
        .chat-page { display: flex; flex-direction: column; }
        .chat-card { display: flex; flex-direction: column; height: 580px; padding: 0; overflow: hidden; }

        .chat-empty {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 2rem;
          text-align: center;
          color: #6b7280;
        }
        .chat-empty-title { font-size: 1.05rem; font-weight: 600; color: #374151; margin-bottom: 1rem; }
        .chat-suggestions { list-style: none; display: flex; flex-direction: column; gap: 0.5rem; }
        .suggestion-btn {
          background: #f3f4f6;
          border: 1px solid #e5e7eb;
          border-radius: 20px;
          padding: 0.45rem 1rem;
          font-size: 0.875rem;
          color: #374151;
          transition: background 0.15s;
        }
        .suggestion-btn:hover { background: #e5e7eb; }

        .chat-messages {
          flex: 1;
          overflow-y: auto;
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .bubble { display: flex; }
        .bubble--user { justify-content: flex-end; }
        .bubble--assistant { justify-content: flex-start; }

        .bubble-content {
          max-width: 75%;
          padding: 0.65rem 1rem;
          border-radius: 14px;
          font-size: 0.9rem;
          line-height: 1.5;
          word-break: break-word;
        }
        .bubble--user .bubble-content { background: #2563eb; color: #fff; border-radius: 14px 14px 3px 14px; }
        .bubble--assistant .bubble-content { background: #f3f4f6; color: #1a1a2e; border-radius: 14px 14px 14px 3px; }
        .bubble--error .bubble-content { background: #fee2e2; color: #991b1b; }

        .bubble-content--loading {
          display: flex;
          gap: 4px;
          align-items: center;
          padding: 0.65rem 1.25rem;
        }
        .dot {
          width: 7px; height: 7px;
          background: #9ca3af;
          border-radius: 50%;
          animation: bounce 1.2s infinite;
        }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }

        .bubble-answer { margin-bottom: 0.5rem; }
        .bubble-answer:last-child { margin-bottom: 0; }
        .bubble-meta { font-size: 0.72rem; color: #9ca3af; margin-top: 0.5rem; }

        .result-table-wrap { overflow-x: auto; margin: 0.5rem 0; }
        .result-table { border-collapse: collapse; font-size: 0.8rem; width: 100%; }
        .result-table th {
          background: #e5e7eb;
          padding: 0.35rem 0.6rem;
          text-align: left;
          font-weight: 600;
          white-space: nowrap;
          border-bottom: 2px solid #d1d5db;
        }
        .result-table td { padding: 0.3rem 0.6rem; border-bottom: 1px solid #e5e7eb; }

        .sql-details { margin-top: 0.5rem; font-size: 0.8rem; }
        .sql-details summary { cursor: pointer; color: #6b7280; }
        .sql-pre {
          background: #1e293b;
          color: #e2e8f0;
          padding: 0.6rem 0.75rem;
          border-radius: 6px;
          overflow-x: auto;
          margin-top: 0.35rem;
          font-size: 0.78rem;
          line-height: 1.45;
          white-space: pre-wrap;
        }

        .chat-input-row {
          display: flex;
          gap: 0.5rem;
          align-items: flex-end;
          padding: 1rem 1.25rem;
          border-top: 1px solid #f3f4f6;
        }
        .chat-input-wrap { flex: 1; position: relative; }
        .chat-input {
          width: 100%;
          border: 1px solid #d1d5db;
          border-radius: 10px;
          padding: 0.6rem 0.85rem;
          font-size: 0.9rem;
          font-family: inherit;
          resize: none;
          outline: none;
          transition: border-color 0.15s;
          line-height: 1.4;
        }
        .chat-input:focus { border-color: #2563eb; }
        .char-count {
          position: absolute;
          right: 0.6rem;
          bottom: 0.4rem;
          font-size: 0.7rem;
          color: #9ca3af;
        }
        .char-count--warn { color: #f59e0b; }
        .btn-send {
          padding: 0.6rem 1.1rem;
          font-size: 1.1rem;
          border-radius: 10px;
          flex-shrink: 0;
          align-self: flex-end;
        }
      `}</style>
    </div>
  )
}
