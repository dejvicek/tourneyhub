import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { FieldBadge } from "./FieldBadge";
import type { PlayModel } from "./model";
import { useNames } from "./useNames";

interface FieldsStripProps {
  model: PlayModel;
  /** "Manage fields" (screen 6d). */
  manageHref: string;
}

/** "On the fields": who plays where now (screen 6, FR-091, FR-092). */
export function FieldsStrip({ model, manageHref }: FieldsStripProps) {
  const { t } = useTranslation();
  const names = useNames(model);

  return (
    <section aria-labelledby="on-the-fields" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-x-3">
        <h2 id="on-the-fields" className="font-display text-display-section">
          {t("roundRobin.fields.title")}
        </h2>
        <Link
          to={manageHref}
          className="inline-flex min-h-11 items-center text-body-md font-bold text-secondary-foreground underline underline-offset-4"
        >
          {t("roundRobin.fields.manage")}
        </Link>
      </div>
      <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
        {model.fields.map((field) => {
          const info =
            field.match_id === null
              ? undefined
              : model.matches.get(field.match_id);
          return (
            <li
              key={field.id}
              className="flex items-center gap-3 rounded-lg border border-border-surface bg-card px-3 py-2.5 text-card-foreground"
            >
              <FieldBadge number={field.number} free={info === undefined} />
              <span
                className={
                  info === undefined
                    ? "text-body-sm text-muted-foreground"
                    : "text-body-sm"
                }
              >
                {info === undefined
                  ? model.waiting.length > 0
                    ? t("roundRobin.fields.freeBlocked")
                    : t("roundRobin.fields.freeEmpty")
                  : names.match(info.match.sides)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
