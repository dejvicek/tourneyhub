/** The part of import.meta.env that decides demo mode. */
export interface DemoModeEnv {
  MODE: string;
  VITE_DEMO?: string;
}

/**
 * Demo mode runs the app against the fake API in src/demo, an MSW worker in
 * the browser. `pnpm dev:demo` or VITE_DEMO=true turns it on; a production
 * build never has it, whatever the environment says.
 */
export function isDemoMode(env: DemoModeEnv): boolean {
  return env.MODE !== "production" && env.VITE_DEMO === "true";
}

/**
 * Routes the backend does not serve yet (src/api/provisional.ts) exist only in
 * the demo's fake API. Outside demo mode a query for one stays off, and its
 * screen shows that the data arrives later, instead of a 404.
 */
export function providesProvisionalRoutes(): boolean {
  return isDemoMode(import.meta.env);
}
