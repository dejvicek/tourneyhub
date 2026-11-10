// The VITE_ variables the app reads (docs/frontend-style.md §11). None holds
// a secret: Vite writes them into the bundle.
interface ImportMetaEnv {
  /** "true" turns on demo mode outside production builds (src/lib/demoMode.ts). */
  readonly VITE_DEMO?: string;
}
