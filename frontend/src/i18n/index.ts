import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { initialLanguage, LANGUAGES } from "./language";
import { cs } from "./locales/cs";
import { en } from "./locales/en";

export const resources = {
  en: { translation: en },
  cs: { translation: cs },
} as const;

i18n.on("languageChanged", (language) => {
  document.documentElement.lang = language;
  document.title = i18n.t("app.name");
});

// The resources are bundled, so initialisation finishes synchronously.
void i18n.use(initReactI18next).init({
  resources,
  lng: initialLanguage(),
  supportedLngs: LANGUAGES,
  fallbackLng: "en",
  initAsync: false,
  interpolation: {
    escapeValue: false, // React escapes what it renders
  },
});

export { i18n };
