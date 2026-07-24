import { Outlet } from 'react-router-dom'

export default function PublicLayout() {
  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <header className="border-b border-border px-6 py-4">
        <div className="max-w-[1200px] mx-auto flex items-center">
          <h1 className="font-heading text-2xl text-primary tracking-wide">
            TourneyHub
          </h1>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border px-6 py-4">
        <div className="max-w-[1200px] mx-auto text-center text-sm text-fg-muted">
          Powered by TourneyHub
        </div>
      </footer>
    </div>
  )
}
