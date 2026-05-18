import { useState } from 'react'
import './index.css'
import { Dashboard } from './pages/Dashboard'
import { Gallery } from './pages/Gallery'
import { Timeline } from './pages/Timeline'
import {
  LayoutDashboard,
  ImageIcon,
  Clock,
  Settings,
  GitCompare,
  Crosshair,
} from 'lucide-react'

type Page = 'dashboard' | 'gallery' | 'timeline' | 'compare' | 'calibration' | 'settings'

const NAV_ITEMS: { id: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'dashboard', label: 'Дашборд', icon: LayoutDashboard },
  { id: 'gallery', label: 'Фотографии', icon: ImageIcon },
  { id: 'timeline', label: 'Хронология', icon: Clock },
  { id: 'compare', label: 'Сравнение', icon: GitCompare },
  { id: 'calibration', label: 'Калибровка', icon: Crosshair },
  { id: 'settings', label: 'Настройки', icon: Settings },
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>DEEPUTIN</h1>
          <span>Forensic SCAP v2.0</span>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => setPage(item.id)}
            >
              <item.icon />
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main-content">
        {page === 'dashboard' && <Dashboard />}
        {page === 'gallery' && <Gallery />}
        {page === 'timeline' && <Timeline />}
        {page === 'compare' && <ComingSoon title="Сравнение" />}
        {page === 'calibration' && <ComingSoon title="Калибровка" />}
        {page === 'settings' && <ComingSoon title="Настройки" />}
      </main>
    </div>
  )
}

function ComingSoon({ title }: { title: string }) {
  return (
    <div>
      <div className="page-header">
        <h2>{title}</h2>
        <p>Этот раздел находится в разработке</p>
      </div>
      <div className="panel">
        <div className="panel-body" style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-muted)' }}>
          <Settings size={48} style={{ marginBottom: 16, opacity: 0.3 }} />
          <p style={{ fontSize: 16 }}>Раздел «{title}» будет доступен в следующей версии</p>
        </div>
      </div>
    </div>
  )
}
