import { useState } from 'react'
import { BarChart3, FileText, Home, MessageSquare, Upload } from 'lucide-react'
import HomePage from './components/HomePage.jsx'
import UploadPage from './components/UploadPage.jsx'
import HistoryPage from './components/HistoryPage.jsx'
import ChatPage from './components/ChatPage.jsx'
import robotIcon from '../icon/asistente-de-robot.png'
import './App.css'

const TABS = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'upload', label: 'Upload', icon: Upload },
  { id: 'history', label: 'History', icon: FileText },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
]

export default function App() {
  const [tab, setTab] = useState('home')

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <button className="brand-button" onClick={() => setTab('home')} aria-label="Open home">
            <span className="brand-mark"><BarChart3 size={18} /></span>
            <span className="brand-copy">
              <span className="app-title">Invoice Intelligence</span>
              <span className="app-subtitle">AWS data platform</span>
            </span>
          </button>
          <nav className="app-nav" aria-label="Main navigation">
            {TABS.map(t => {
              const Icon = t.icon
              return (
                <button
                  key={t.id}
                  className={`nav-tab ${tab === t.id ? 'nav-tab--active' : ''}`}
                  onClick={() => setTab(t.id)}
                >
                  <Icon size={16} />
                  {t.label}
                </button>
              )
            })}
          </nav>
        </div>
      </header>

      <main className="app-main">
        {tab === 'home' && <HomePage onNavigate={setTab} />}
        {tab === 'upload' && <UploadPage />}
        {tab === 'history' && <HistoryPage />}
        {tab === 'chat' && <ChatPage />}
      </main>

      <footer className="app-footer">
        <div className="author-widget">
          <img className="author-widget-icon" src={robotIcon} alt="" aria-hidden="true" />
          <div className="author-widget-copy">
            <p>@Junio 2026 - Developed by Ricardo Uculmana Quispe</p>
            <a
              href="https://www.flaticon.es/iconos-gratis/robot"
              title="robot iconos"
              target="_blank"
              rel="noreferrer"
            >
              Robot iconos creados por Flat Icons - Flaticon
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
