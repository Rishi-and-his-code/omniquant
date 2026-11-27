import { NavLink, Outlet } from 'react-router-dom'
import {
  CandlestickChart,
  FlaskConical,
  History,
  LineChart,
  Activity,
} from 'lucide-react'
import { useApp } from '../../context/AppContext'
import { clsx } from '../../lib/format'

const nav = [
  { to: '/', label: 'Market Explorer', icon: CandlestickChart, end: true },
  { to: '/strategy', label: 'Strategy Studio', icon: LineChart },
  { to: '/backtest', label: 'Backtest Lab', icon: FlaskConical },
  { to: '/history', label: 'Research History', icon: History },
]

export function AppShell() {
  const { health } = useApp()
  const online = health?.status === 'ok'
  const aiReady = Boolean(health?.ai_configured)

  return (
    <div className="flex h-full min-h-0 bg-oq-bg text-oq-text">
      <aside className="flex w-56 shrink-0 flex-col border-r border-oq-border bg-oq-sidebar">
        <div className="border-b border-oq-border px-4 py-5">
          <div className="text-lg font-semibold tracking-tight text-oq-text">OmniQuant</div>
          <div className="mt-0.5 text-[11px] uppercase tracking-[0.14em] text-oq-muted">
            Quantitative Research Terminal
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-oq-elevated text-oq-text'
                    : 'text-oq-secondary hover:bg-oq-elevated/60 hover:text-oq-text',
                )
              }
            >
              <item.icon size={16} className="opacity-80" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-oq-border p-3 text-[11px] text-oq-muted">
          <div className="mb-2 flex items-center gap-2">
            <span
              className={clsx(
                'inline-block h-1.5 w-1.5 rounded-full',
                online ? 'bg-oq-positive' : 'bg-oq-negative',
              )}
            />
            Backend {online ? 'connected' : 'offline'}
          </div>
          <div className="mb-2 flex items-center gap-2">
            <Activity size={12} />
            AI {aiReady ? 'configured' : 'unavailable'}
          </div>
          <div>MVP v{health?.version || '0.1.0'}</div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-oq-border bg-oq-sidebar/80 px-6 py-3">
          <div className="text-sm text-oq-secondary">
            Historical research · Simulated backtesting · Indian equities (daily)
          </div>
          <div className="text-[11px] text-oq-muted">
            Historical performance does not guarantee future results.
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
