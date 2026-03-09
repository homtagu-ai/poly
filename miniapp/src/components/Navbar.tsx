import { useLocation, useNavigate } from 'react-router-dom'

const tabs = [
  { path: '/', label: 'Home', icon: '\u{1F4CA}' },
  { path: '/configs', label: 'Configs', icon: '\u{2699}\u{FE0F}' },
  { path: '/positions', label: 'Positions', icon: '\u{1F4BC}' },
  { path: '/history', label: 'History', icon: '\u{1F4DC}' },
  { path: '/settings', label: 'Settings', icon: '\u{1F527}' },
]

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-bg-secondary border-t border-bg-tertiary">
      <div className="flex justify-around items-center h-16 max-w-lg mx-auto">
        {tabs.map((tab) => {
          const isActive = location.pathname === tab.path ||
            (tab.path !== '/' && location.pathname.startsWith(tab.path))
          return (
            <button
              key={tab.path}
              onClick={() => navigate(tab.path)}
              className={`flex flex-col items-center gap-0.5 py-1 px-3 transition-colors ${
                isActive ? 'text-accent-teal' : 'text-text-secondary'
              }`}
            >
              <span className="text-xl">{tab.icon}</span>
              <span className="text-[10px] font-medium">{tab.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
