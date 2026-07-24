import { useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'

const navItems = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/tournaments', label: 'Tournaments' },
  { to: '/leagues', label: 'Leagues' },
]

export default function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="min-h-screen bg-bg flex">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-bg-surface border-r border-border flex flex-col transition-transform duration-200 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="p-4 border-b border-border">
          <h2 className="font-heading text-2xl text-primary tracking-wide">
            TourneyHub
          </h2>
          <p className="text-fg-muted text-xs mt-1">My Organization</p>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-bg-subtle text-primary'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-subtle'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-border">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-bg-subtle flex items-center justify-center text-fg-muted text-sm font-medium">
              U
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-fg truncate">User</p>
              <p className="text-xs text-fg-muted truncate">user@example.com</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="sticky top-0 z-30 bg-bg-surface/80 backdrop-blur-md border-b border-border px-6 py-3 flex items-center gap-4">
          <button
            className="lg:hidden text-fg-muted hover:text-fg"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle sidebar"
          >
            <svg viewBox="0 0 24 24" className="w-6 h-6 fill-none stroke-current stroke-2" strokeLinecap="round">
              <path d="M3 12h18M3 6h18M3 18h18" />
            </svg>
          </button>
          <span className="text-sm text-fg-muted">/ Home</span>
          <div className="flex-1" />
          <button className="text-sm text-fg-muted hover:text-fg transition-colors">
            Sign out
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
