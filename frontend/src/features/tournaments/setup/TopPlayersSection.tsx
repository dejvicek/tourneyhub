import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { setupMutations } from "@/features/tournaments/api";

import { describeError } from "./errors";
import { Notice } from "./Notice";
import type { SetupData } from "./SetupPage";

/** Monster DYP: the organizer may mark the top players, at most one per match (FR-041). */
export function TopPlayersSection({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const { leagueId, tournamentId, setup, ranking } = data;
  const save = useMutation(setupMutations.topPlayers(leagueId, tournamentId));
  const picked = ranking.filter((row) =>
    setup.player_ids.includes(row.player_id),
  );
  const groups = Math.floor(picked.length / 4);
  const marked = save.isPending ? save.variables : setup.top_player_ids;

  return (
    <div className="grid content-start gap-4">
      <div className="grid gap-1">
        <h2 className="font-display text-display-section">
          {t("tournaments.setup.draw.topPlayers", { count: groups })}
        </h2>
        <p className="text-body-sm text-muted-foreground">
          {t("tournaments.setup.draw.topPlayersHint", { count: groups })}
        </p>
      </div>
      <Notice variant="info" title={t("tournaments.setup.draw.noSeeds.title")}>
        {t("tournaments.setup.draw.noSeeds.body")}
      </Notice>
      {save.isError && (
        <p role="alert" className="text-body-md text-destructive">
          {describeError(save.error, t)}
        </p>
      )}
      <ul>
        {picked.map((row) => {
          const checked = marked.includes(row.player_id);
          const id = `top-${row.player_id}`;
          return (
            <li
              key={row.player_id}
              className="flex min-h-14 items-center gap-3 border-t border-border py-1.5 first:border-t-0"
            >
              <span
                aria-hidden="true"
                className="w-7 shrink-0 text-center font-display text-score-m text-muted-foreground"
              >
                {row.rank}
              </span>
              <Label
                htmlFor={id}
                className="min-h-11 flex-1 cursor-pointer text-body-lg"
              >
                {row.name}
              </Label>
              <Checkbox
                id={id}
                checked={checked}
                disabled={!checked && marked.length >= groups}
                onCheckedChange={(next) => {
                  save.mutate(
                    next === true
                      ? [...marked, row.player_id]
                      : marked.filter((other) => other !== row.player_id),
                  );
                }}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
