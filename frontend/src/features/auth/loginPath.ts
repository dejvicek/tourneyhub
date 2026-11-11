import { paths } from "@/lib/paths";

/** The login, returning to `next` afterwards. */
export function loginPath(next: string): string {
  return `${paths.login}?${new URLSearchParams({ next }).toString()}`;
}

/**
 * Where to go after logging in: `next` if it is a path of this app, so a
 * crafted link cannot send the organizer to another site.
 */
export function safeNext(next: string | null): string {
  return next?.startsWith("/") === true &&
    !next.startsWith("//") &&
    !next.startsWith("/\\")
    ? next
    : paths.myLeagues;
}
