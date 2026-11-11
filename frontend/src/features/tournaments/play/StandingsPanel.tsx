import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";

import type { PlayModel } from "./model";
import { StandingsNotes } from "./StandingsNotes";
import { StandingsTable } from "./StandingsTable";

type PlayRead = components["schemas"]["PlayRead"];

/** Live group-phase standings with the tie-break note (screens 6, 6b, FR-060). */
export function StandingsPanel({
  model,
  play,
}: {
  model: PlayModel;
  play: PlayRead | undefined;
}) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="standings" className="space-y-2">
      <h2 id="standings" className="font-display text-display-section">
        {t("roundRobin.standings.title")}
      </h2>
      {play === undefined ? (
        <p className="text-body-sm text-muted-foreground">{t("loading")}</p>
      ) : (
        <>
          <StandingsTable
            model={model}
            rows={play.standings}
            caption={t("roundRobin.standings.title")}
          />
          <StandingsNotes model={model} rows={play.standings} firstOnly />
        </>
      )}
    </section>
  );
}
