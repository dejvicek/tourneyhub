import { i18n } from "@/i18n";

// The design writes English dates as "Thu 22 Oct", so the English texts use
// the British order; Czech uses its own (FR-081, docs/frontend-style.md §7).
function locale(): string {
  return i18n.resolvedLanguage === "cs" ? "cs-CZ" : "en-GB";
}

/** An ISO date (YYYY-MM-DD) at noon local time, so no time zone moves its day. */
function atNoon(isoDate: string): Date {
  return new Date(`${isoDate}T12:00:00`);
}

/** "Thu 22 Oct" */
export function shortDate(isoDate: string): string {
  return new Intl.DateTimeFormat(locale(), {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(atNoon(isoDate));
}

/** "Thu 22 October 2026" */
export function longDate(isoDate: string): string {
  return new Intl.DateTimeFormat(locale(), {
    weekday: "short",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(atNoon(isoDate));
}

/** "22 October": the default name's date. */
export function dayAndMonth(isoDate: string): string {
  return new Intl.DateTimeFormat(locale(), {
    day: "numeric",
    month: "long",
  }).format(atNoon(isoDate));
}

/** Today on the organizer's device, as YYYY-MM-DD (DATA-MODEL §4.3). */
export function today(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${String(now.getFullYear())}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
