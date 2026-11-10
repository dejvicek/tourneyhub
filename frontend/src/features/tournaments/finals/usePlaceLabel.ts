import { useTranslation } from "react-i18next";

/**
 * A place as the language writes it: "1st" in English, "1." in Czech. The
 * suffixes are texts, chosen by the language's ordinal rule.
 */
export function usePlaceLabel(): (place: number) => string {
  const { t, i18n } = useTranslation();
  return (place) => {
    const category = new Intl.PluralRules(i18n.resolvedLanguage, {
      type: "ordinal",
    }).select(place);
    const suffix = (() => {
      switch (category) {
        case "one":
          return t("finals.place.suffix.one");
        case "two":
          return t("finals.place.suffix.two");
        case "few":
          return t("finals.place.suffix.few");
        case "zero":
        case "many":
        case "other":
          return t("finals.place.suffix.other");
      }
    })();
    return t("finals.place.label", { place, suffix });
  };
}
