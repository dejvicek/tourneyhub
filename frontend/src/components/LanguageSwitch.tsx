import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { isLanguage, LANGUAGES, rememberLanguage } from "@/i18n/language";

export function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  const current = isLanguage(i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : undefined;

  return (
    <div
      role="group"
      aria-label={t("language.switchLabel")}
      className="flex gap-1"
    >
      {LANGUAGES.map((language) => (
        <Button
          key={language}
          type="button"
          size="sm"
          variant={language === current ? "default" : "outline"}
          aria-pressed={language === current}
          aria-label={t(`language.${language}.name`)}
          lang={language}
          className="min-w-11"
          onClick={() => {
            rememberLanguage(language);
            void i18n.changeLanguage(language);
          }}
        >
          {t(`language.${language}.short`)}
        </Button>
      ))}
    </div>
  );
}
