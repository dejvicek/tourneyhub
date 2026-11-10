// The viewer's language (ADR-003, FR-081): their own choice, kept in
// localStorage, else the browser's language if it is English or Czech,
// else English. An organizer's language will come from their account.

export const LANGUAGES = ["en", "cs"] as const;
export type Language = (typeof LANGUAGES)[number];

export const DEFAULT_LANGUAGE: Language = "en";
export const LANGUAGE_STORAGE_KEY = "tourneyhub.language";

export function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some((language) => language === value);
}

export function pickLanguage(
  stored: string | null,
  browserLanguage: string | undefined,
): Language {
  if (isLanguage(stored)) {
    return stored;
  }
  const primary = browserLanguage?.split("-")[0]?.toLowerCase();
  return isLanguage(primary) ? primary : DEFAULT_LANGUAGE;
}

export function initialLanguage(): Language {
  return pickLanguage(readStoredLanguage(), navigator.language);
}

export function rememberLanguage(language: Language): void {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Storage can be blocked (private browsing, disabled site data); the
    // choice then lasts until the page is reloaded.
  }
}

function readStoredLanguage(): string | null {
  try {
    return localStorage.getItem(LANGUAGE_STORAGE_KEY);
  } catch {
    return null;
  }
}
