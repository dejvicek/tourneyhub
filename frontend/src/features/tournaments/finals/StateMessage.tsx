import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

/** A screen's main data is on its way. */
export function Loading() {
  const { t } = useTranslation();
  return (
    <p role="status" className="text-body-md text-muted-foreground">
      {t("loading")}
    </p>
  );
}

/** A screen's main data failed to load; errors show inline (guide §8.1). */
export function LoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="space-y-3">
      <p className="text-body-md">{t("finals.common.loadFailed")}</p>
      <Button type="button" className="min-h-11" onClick={onRetry}>
        {t("finals.common.retry")}
      </Button>
    </div>
  );
}
