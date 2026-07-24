import { Outlet } from 'react-router-dom'

export default function AuthLayout() {
  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="font-heading text-4xl text-primary tracking-wide">
              TourneyHub
            </h1>
            <p className="text-fg-muted mt-2 text-sm">
              Run leagues and tournaments for any competitive discipline
            </p>
          </div>
          <div className="bg-bg-surface border border-border rounded-lg p-8 shadow-md">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  )
}
