import { useState } from 'react'
import './index.css'
import { Dashboard } from './pages/Dashboard'
import { Gallery } from './pages/Gallery'
import { Timeline } from './pages/Timeline'
import { ComparePage } from './pages/Compare'
import { SettingsPage } from './pages/Settings'
import { CalibrationPage } from './pages/Calibration'
import { NotificationProvider } from './components/NotificationSystem'
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
    <NotificationProvider>
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
          {page === 'compare' && <ComparePage />}
          {page === 'calibration' && <CalibrationPage />}
          {page === 'settings' && <SettingsPage />}
        </main>
      </div>
    </NotificationProvider>
  )
}
