import { useState, useEffect } from 'react';

function App() {
  const [, setApiStatus] = useState<'checking' | 'connected' | 'error'>('checking');
  const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080/api/v1';

  useEffect(() => {
    // Just a placeholder check to simulate connecting to the backend
    // In reality, you'd hit a health check endpoint here.
    const checkApi = async () => {
      try {
        setApiStatus('error'); // Backend not connected yet as per instructions
      } catch {
        setApiStatus('error');
      }
    };
    checkApi();
  }, []);

  return (
    <div className="min-h-screen bg-bg-base text-fg-base font-body">
      {/* HEADER */}
      <header className="sticky top-0 z-50 bg-bg-base/80 backdrop-blur-md border-b border-border-base px-6 py-4">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2 font-heading font-extrabold text-2xl tracking-tight text-primary">
            <svg viewBox="0 0 24 24" className="w-6 h-6 stroke-current stroke-[2.5px] fill-none" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 6h16M4 6v8a4 4 0 004 4h8a4 4 0 004-4V6M12 18v4M8 22h8" />
            </svg>
            TourneyHub
          </div>
        </div>
      </header>

      {/* MAIN */}
      <main className="max-w-[1200px] mx-auto px-6 py-24">
        <div className="max-w-2xl mx-auto flex flex-col items-center text-center">
          
          <h1 className="font-heading font-bold text-4xl sm:text-5xl tracking-tight mb-4">
            Welcome to TourneyHub
          </h1>
          <p className="text-fg-muted text-lg mb-12">
            The frontend SPA is successfully scaffolded and ready for development.
          </p>

          {/* STATUS CARD */}
          <div className="bg-bg-card border border-border-base rounded-2xl p-8 shadow-sm hover:shadow-md transition-shadow w-full">
            <h2 className="font-heading font-semibold text-xl mb-6">System Status</h2>
            
            <div className="space-y-4 text-left">
              <div className="flex items-center justify-between p-4 bg-bg-surface rounded-xl border border-border-base">
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-fg-muted mb-1">API Base URL</span>
                  <code className="font-mono text-sm text-primary">{apiUrl}</code>
                </div>
                <div className="flex items-center justify-center w-10 h-10 rounded-full bg-primary/10 text-primary">
                  <svg viewBox="0 0 24 24" className="w-5 h-5 fill-none stroke-current stroke-2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                </div>
              </div>

              <div className="flex items-center justify-between p-4 bg-bg-surface rounded-xl border border-border-base">
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-fg-muted mb-1">Backend Connection</span>
                  <span className="font-medium text-accent flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
                    </span>
                    Backend not connected yet
                  </span>
                </div>
                <div className="flex items-center justify-center w-10 h-10 rounded-full bg-accent/10 text-accent">
                  <svg viewBox="0 0 24 24" className="w-5 h-5 fill-none stroke-current stroke-2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                </div>
              </div>
            </div>

          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
