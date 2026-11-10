import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { Player } from "@/demo/contract";

import type { PublicMatch, PublicTournament } from "./api";
import { useNames } from "./useNames";

/**
 * FR-070: which match is on which field and which wait, in the order they
 * get one (FR-092): the design's field cards and waiting list, read-only.
 */
export function LiveFields({
  tournament,
  players,
  headingLevel = 2,
}: {
  tournament: PublicTournament;
  players: Player[];
  headingLevel?: 2 | 3;
}) {
  const { t } = useTranslation();
  const names = useNames(players, tournament);
  const matches = new Map<string, PublicMatch>(
    tournament.rounds.flatMap((round) =>
      round.matches.map((match) => [match.id, match]),
    ),
  );
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const waiting = tournament.waiting.flatMap((id) => matches.get(id) ?? []);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section className="space-y-2">
        <Heading className="text-body-sm font-bold text-muted-foreground">
          {t("publicView.tournament.fieldsHeading")}
        </Heading>
        <ul className="space-y-2">
          {tournament.fields.map((field) => {
            const match =
              field.match_id === null ? undefined : matches.get(field.match_id);
            return (
              <li
                key={field.id}
                className={
                  match === undefined
                    ? "flex items-center gap-3 rounded-lg border-2 border-dashed border-border px-4 py-3"
                    : "flex items-center gap-3 rounded-lg border-2 border-foreground bg-card px-4 py-3 text-card-foreground"
                }
              >
                <Badge variant={match === undefined ? "secondary" : "default"}>
                  {t("publicView.tournament.field", { number: field.number })}
                </Badge>
                <span className="text-body-md font-bold">
                  {match === undefined
                    ? t("publicView.tournament.freeField")
                    : names.ofMatch(match)}
                </span>
              </li>
            );
          })}
        </ul>
      </section>
      <section className="space-y-2">
        <Heading className="text-body-sm font-bold text-muted-foreground">
          {t("publicView.tournament.waitingHeading")}
        </Heading>
        {waiting.length === 0 ? (
          <p className="text-body-md text-muted-foreground">
            {t("publicView.tournament.noWaiting")}
          </p>
        ) : (
          <ol className="space-y-2">
            {waiting.map((match, index) => (
              <li
                key={match.id}
                className="flex items-center gap-3 rounded-lg border border-dashed border-border px-4 py-3"
              >
                <span
                  aria-hidden="true"
                  className="flex size-8 shrink-0 items-center justify-center rounded-full bg-nav-active font-display text-score-s text-nav-active-foreground"
                >
                  {index + 1}
                </span>
                <span className="text-body-md">{names.ofMatch(match)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
