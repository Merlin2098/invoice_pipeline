import { useState } from 'react'
import UploadPage from './components/UploadPage.jsx'
import HistoryPage from './components/HistoryPage.jsx'
import ChatPage from './components/ChatPage.jsx'
import './App.css'

const TABS = [
  { id: 'upload',  label: '⬆ Upload' },
  { id: 'history', label: '📋 History' },
  { id: 'chat',    label: '💬 Chat' },
]

export default function App() {
  const [tab, setTab] = useState('upload')

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <h1 className="app-title">Invoice Intelligence</h1>
          <nav className="app-nav">
            {TABS.map(t => (
              <button
                key={t.id}
                className={`nav-tab ${tab === t.id ? 'nav-tab--active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="app-main">
        {tab === 'upload'  && <UploadPage />}
        {tab === 'history' && <HistoryPage />}
        {tab === 'chat'    && <ChatPage />}
      </main>

      <footer className="app-footer">
        Powered by AWS · Textract · Bedrock · Athena
      </footer>
    </div>
  )
}
