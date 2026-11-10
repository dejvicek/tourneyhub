import { useTranslation } from "react-i18next";

/** Shown while the first lazy area of a page load arrives (HydrateFallback). */
export function PageFallback() {
  const { t } = useTranslation();

  return (
    <p role="status" className="p-6 text-body-md text-muted-foreground">
      {t("loading")}
    </p>
  );
}
