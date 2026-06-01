import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bot, Send, Sparkles } from 'lucide-react'
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
        <div className="bubble-content btn-with-icon">
          <AlertTriangle size={16} />
          {message.error}
        </div>
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
            {message.execution_time_ms} ms | {(message.athena_scan_mb ?? 0).toFixed(2)} MB scanned
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
              {cols.map(c => <td key={c}>{row[c] ?? '-'}</td>)}
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
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

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
    <div className="page-shell chat-page">
      <div className="page-heading">
        <div>
          <h1 className="page-title">Chat with your invoices</h1>
          <p className="page-description">Ask Bedrock-backed analytics questions over Athena results.</p>
        </div>
      </div>

      <div className="chat-card card">
        {messages.length === 0 && !loading && (
          <div className="chat-empty">
            <span className="chat-empty-icon"><Sparkles size={24} /></span>
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
              placeholder="Ask about spend, suppliers, statuses, or invoice trends"
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
            aria-label="Send question"
          >
            {loading ? <Bot size={18} /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  )
}
